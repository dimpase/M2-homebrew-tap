#!/usr/bin/env python3
"""Build Intel candidates, stage immutable pins, and promote after clean matrix tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from urllib.parse import unquote

BREW = '/usr/local/Homebrew/bin/brew'
REPOSITORIES = {'core': 'dimpase/homebrew-core', 'm2': 'dimpase/M2-homebrew-tap'}
UPSTREAM = {'core': 'Homebrew/homebrew-core', 'm2': 'Macaulay2/homebrew-tap'}
NODE_NAME = 'node-v26.11.1-darwin-x64'
NODE_SHA = '9a8129bd9ab08039793dd1143a7aedee6b5d60ac06592ad938d8bddf36142f3a'
SCRIPT = Path(__file__).resolve().parent
WORK = Path(os.environ.get('INTEL_WORK', 'intel-work')).resolve()
CACHE = Path('intel-build-cache').resolve()
STATE = WORK/'state.json'
OVERLAY_RE = re.compile(r'^    on_intel do\n      bottle do\n.*?^      end\n    end\n', re.M | re.S)


def run(args, cwd=None, log=None, guard=False, input_text=None):
    env = os.environ.copy()
    env.pop('DISPLAY', None)
    if guard:
        env.pop('GH_TOKEN', None)
        env.pop('GITHUB_TOKEN', None)
    if log is None:
        return subprocess.check_output(args, cwd=cwd, env=env, text=True, input=input_text).strip()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as stream:
        proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if guard and shutil.disk_usage('/usr/local').free < 20 * 1024**3:
                        os.killpg(proc.pid, signal.SIGINT)
                        try:
                            proc.wait(timeout=60)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGTERM)
                        raise RuntimeError('Disk guard stopped the build below 20 GiB free')
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            raise
    if proc.returncode:
        print(log.read_text(errors='replace')[-15000:], flush=True)
        raise RuntimeError(f'Command failed; see {log}')
    return log.read_text()


def git(repo, *args):
    return run(['git', '-C', str(repo), *args])


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def output(name, value):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'{name}={value}\n')


def disposable():
    assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Requires a disposable GitHub-hosted runner'
    assert run(['uname', '-m']) == 'x86_64'
    assert run(['sw_vers', '-productVersion']).split('.')[0] == '15'
    assert run([BREW, '--prefix']) == '/usr/local'


def inventory():
    destination = WORK/'evaluated-inventory.json'
    run([BREW, 'ruby', str(SCRIPT/'inventory-intel.rb'), str(destination)], log=WORK/'inventory.log')
    return json.loads(destination.read_text())


def topological(rows):
    by_name = {r['name']: r for r in rows}
    order, visiting, visited = [], set(), set()
    def visit(name):
        if name in visited:
            return
        if name in visiting:
            raise ValueError('Dependency cycle: ' + name)
        visiting.add(name)
        for dep in by_name[name]['dependencies']:
            visit(dep['name'])
        visiting.remove(name)
        visited.add(name)
        order.append(name)
    for name in by_name:
        visit(name)
    return order


def affected_runtime(rows, runtime_names, baseline):
    previous = {r['name']: r for r in baseline['formulae']}
    runtime = set(runtime_names)
    changed = {r['name'] for r in rows if r['name'] in runtime and
               (r['name'] not in previous or any(r[key] != previous[r['name']][key]
                for key in ('version', 'recipe_sha256')))}
    while True:
        extra = {r['name'] for r in rows if r['name'] in runtime and
                 any(not d['build'] and d['name'] in changed for d in r['dependencies'])}
        if extra <= changed:
            return changed
        changed |= extra


def append_overlay(source, overlay):
    assert not OVERLAY_RE.search(source), 'Private bottle override already present'
    # Separate on_macos blocks are valid formula DSL; avoid altering upstream blocks.
    block = '  on_macos do\n' + overlay + '  end\n\n'
    insertion = re.search(r'^  (?:def |patch |on_linux do|link_overwrite |deny_network_access!|allow_network_access!)', source, re.M)
    if insertion is None:
        insertion = re.search(r'^end\n', source, re.M)
    assert insertion, 'Cannot locate formula insertion point'
    return source[:insertion.start()] + block + source[insertion.start():]


def bottle_overlay(metadata):
    bottle = metadata['bottle_metadata']
    tag = bottle['tags']['sequoia']
    cellar = bottle['cellar']
    ruby_cellar = ':' + cellar if cellar in ('any', 'any_skip_relocation') else json.dumps(cellar)
    lines = ['    on_intel do', '      bottle do', '        root_url ' + json.dumps(bottle['root_url'])]
    if bottle.get('rebuild'):
        lines.append('        rebuild ' + str(bottle['rebuild']))
    lines += [f'        sha256 cellar: {ruby_cellar}, sequoia: "{tag["sha256"]}"', '      end', '    end', '']
    return '\n'.join(lines)


def clone_stable(kind, destination):
    run(['git', 'clone', '--depth=1', '--branch', 'intel-bottles',
         'https://github.com/' + REPOSITORIES[kind] + '.git', str(destination)])
    return git(destination, 'rev-parse', 'HEAD')


def prepare(args):
    disposable()
    WORK.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((SCRIPT/'intel-baseline.json').read_text())
    state = {'tag': 'intel-bottles-' + os.environ['GITHUB_RUN_ID'], 'stable_heads': {}, 'upstream_heads': {}, 'tap_paths': {}}
    for kind, tap in [('core', 'homebrew/core'), ('m2', 'macaulay2/tap')]:
        stable = WORK/('stable-' + kind)
        state['stable_heads'][kind] = clone_stable(kind, stable)
        url = 'https://github.com/' + UPSTREAM[kind] + '.git'
        run([BREW, 'tap', '--custom-remote', '--force', tap, url])
        path = Path(run([BREW, '--repository', tap]))
        wanted = getattr(args, kind + '_commit')
        assert re.fullmatch('[0-9a-f]{40}', wanted), 'Expected exact upstream commit'
        git(path, 'fetch', '--depth=1', url, wanted)
        git(path, 'reset', '--hard', 'FETCH_HEAD')
        git(path, 'clean', '-fdx')
        state['upstream_heads'][kind] = git(path, 'rev-parse', 'HEAD')
        state['tap_paths'][kind] = str(path)
    if subprocess.run([BREW, 'help', 'trust'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        run([BREW, 'trust', '--tap', *['https://github.com/' + UPSTREAM[kind] + '.git' for kind in UPSTREAM]])
    raw = inventory()
    dump(WORK/'upstream-inventory.json', raw)
    affected = affected_runtime(raw['formulae'], raw['runtime_names'], baseline)
    overlays = {}
    for row in raw['formulae']:
        old = WORK/('stable-' + row['repository'])/row['path']
        if old.is_file():
            match = OVERLAY_RE.search(old.read_text())
            if match and row['name'] not in affected and row['name'] in raw['runtime_names']:
                path = Path(state['tap_paths'][row['repository']])/row['path']
                path.write_text(append_overlay(path.read_text(), match.group(0)))
                overlays[row['name']] = match.group(0)
    # Carry the build fix only until upstream includes it; do not add it twice.
    m2_row = next(r for r in raw['formulae'] if r['name'] == 'macaulay2/tap/macaulay2')
    m2_path = Path(state['tap_paths']['m2'])/m2_row['path']
    source = m2_path.read_text()
    if 'ENV.delete("DISPLAY")' not in source:
        source = source.replace('  def install\n', '  def install\n    ENV.delete("DISPLAY")\n', 1)
        m2_path.write_text(source)
    current = inventory()
    state.update(runtime_names=raw['runtime_names'], formulae=current['formulae'], reused_private_bottles=sorted(overlays),
                 affected_runtime=sorted(affected), order=topological(current['formulae']))
    state['build_names'] = [r['name'] for r in current['formulae'] if not r['bottle_url']]
    state['cache_key'] = hashlib.sha256(json.dumps({'formulae': raw, 'node_sha256': NODE_SHA, 'format': 1}, sort_keys=True).encode()).hexdigest()
    dump(STATE, state)
    output('cache_key', state['cache_key'])
    output('tag', state['tag'])
    print(json.dumps({'build_names': state['build_names'], 'reused_private_bottles': state['reused_private_bottles'], 'affected_runtime': state['affected_runtime']}, indent=2), flush=True)


def get_node():
    destination = WORK/NODE_NAME
    archive = WORK/(NODE_NAME + '.tar.xz')
    run(['curl', '-fL', '--retry', '3', 'https://nodejs.org/dist/v26.11.1/' + archive.name, '-o', str(archive)])
    assert digest(archive) == NODE_SHA, 'Node build tool checksum mismatch'
    with tarfile.open(archive) as bundle:
        bundle.extractall(WORK, filter='data')
    os.environ['INTEL_NODE_TOOL'] = str(destination)
    return destination


def set_metadata(row, metadata, state):
    path = Path(state['tap_paths'][row['repository']])/row['path']
    source = path.read_text()
    assert not OVERLAY_RE.search(source), 'New builds must not retain a private override'
    metadata['bottle_metadata']['root_url'] = 'https://github.com/dimpase/M2-homebrew-tap/releases/download/' + state['tag']
    path.write_text(append_overlay(source, bottle_overlay(metadata)))


def audit_x11(state):
    magic = {bytes.fromhex(x) for x in ('feedface','cefaedfe','feedfacf','cffaedfe','cafebabe','bebafeca','cafebabf','bfbafeca')}
    rows = {r['name']: r for r in state['formulae']}
    report = {'files_checked': 0, 'x11_links': []}
    for name in state['runtime_names']:
        row = rows[name]
        keg = Path('/usr/local/Cellar')/row['short_name']/row['version']
        assert keg.is_dir(), 'Missing runtime keg: ' + str(keg)
        for path in keg.rglob('*'):
            if path.is_symlink() or not path.is_file():
                continue
            with path.open('rb') as stream:
                if stream.read(4) not in magic:
                    continue
            report['files_checked'] += 1
            links = run(['/usr/bin/otool', '-L', str(path)])
            for line in links.splitlines()[1:]:
                if re.search(r'/(?:opt/X11|usr/X11|XQuartz)(?:/|\b)|/lib(?:X11|Xext|Xrender|Xrandr|Xfixes|Xcursor|Xi|Xt|xcb)[.\d]', line):
                    report['x11_links'].append({'file': str(path), 'link': line.strip()})
    dump(WORK/'runtime-x11-audit.json', report)
    assert not report['x11_links'], 'Runtime contains X11 linkage'


def build(_args):
    disposable()
    state = json.loads(STATE.read_text())
    by_name = {r['name']: r for r in state['formulae']}
    CACHE.mkdir(exist_ok=True)
    node = get_node()
    os.environ['PATH'] = str(node/'bin') + os.pathsep + os.environ['PATH']
    # This runner is disposable. Remove old runtime kegs before rebuilding or pouring.
    for name in state['runtime_names']:
        versions = subprocess.run([BREW, 'list', '--versions', name], capture_output=True, text=True)
        if versions.stdout.strip():
            run([BREW, 'uninstall', '--force', '--ignore-dependencies', name])
    built = []
    for name in state['order']:
        row = by_name[name]
        print('Preparing ' + name + ' ' + row['version'], flush=True)
        folder = CACHE/name.replace('/', '_')
        if name not in state['build_names']:
            run([BREW, 'install', '--force-bottle', name], log=WORK/'logs'/(row['short_name'] + '-pour.log'), guard=True)
            continue
        if shutil.disk_usage('/usr/local').free < 25 * 1024**3:
            raise RuntimeError('Less than 25 GiB free before source build')
        folder.mkdir(exist_ok=True)
        saved = folder/'manifest.json'
        metadata = None
        if saved.exists():
            metadata = json.loads(saved.read_text())
            archive = folder/metadata['local_filename']
            assert metadata['cache_key'] == state['cache_key'] and digest(archive) == metadata['sha256'], 'Cached bottle mismatch'
            run([BREW, 'install', '--force-bottle', str(archive)], log=WORK/'logs'/(row['short_name'] + '-cache-pour.log'), guard=True)
        else:
            run([BREW, 'ruby', str(SCRIPT/'build-intel.rb'), name], log=folder/'build.log', guard=True)
            run([BREW, 'linkage', '--test', name], log=folder/'linkage.log', guard=True)
            run([BREW, 'test', name], log=folder/'test.log', guard=True)
            run([BREW, 'bottle', '--json', '--root-url=https://github.com/dimpase/M2-homebrew-tap/releases/download/' + state['tag'], name], cwd=folder, log=folder/'bottle.log', guard=True)
            json_files = list(folder.glob('*.bottle.json'))
            assert len(json_files) == 1, 'Expected exactly one bottle metadata file'
            item = next(iter(json.loads(json_files[0].read_text()).values()))['bottle']
            tag = item['tags']['sequoia']
            archive = folder/tag['local_filename']
            assert digest(archive) == tag['sha256'], 'Bottle checksum mismatch'
            receipt = json.loads((Path('/usr/local/Cellar')/row['short_name']/row['version']/'INSTALL_RECEIPT.json').read_text())
            assert receipt['built_as_bottle'] and not receipt['poured_from_bottle'], 'Not a source-built bottle receipt'
            metadata = {'formula': name, 'version': row['version'], 'local_filename': archive.name,
                'filename': unquote(tag['filename']), 'sha256': digest(archive), 'cache_key': state['cache_key'],
                'bottle_metadata': item, 'source_receipt': receipt, 'recipe_sha256': row['recipe_sha256'],
                'linkage_test': 'passed', 'formula_test': 'passed'}
            if name == 'macaulay2/tap/macaulay2':
                metadata['build_tool_override'] = {'node': NODE_NAME, 'sha256': NODE_SHA, 'environment': 'Homebrew std; DISPLAY unset'}
            dump(saved, metadata)
        set_metadata(row, metadata, state)
        built.append(metadata)
    audit_x11(state)
    dump(WORK/'built-bottles.json', built)
    final_inventory = inventory()
    assert all(r['bottle_url'] for r in final_inventory['formulae']), 'Candidate still lacks an Intel bottle'
    dump(WORK/'candidate-inventory.json', final_inventory)
    with tarfile.open(WORK/'candidate-formulae.tar.gz', 'w:gz') as bundle:
        for kind, path in state['tap_paths'].items():
            for directory in ('Formula', 'Aliases'):
                source = Path(path)/directory
                if source.exists():
                    bundle.add(source, arcname=kind + '/' + directory)
    assets = WORK/'assets'
    assets.mkdir(exist_ok=True)
    for entry in built:
        folder = CACHE/entry['formula'].replace('/', '_')
        shutil.copyfile(folder/entry['local_filename'], assets/entry['filename'])
        dump(assets/(entry['formula'].replace('/', '_') + '-manifest.json'), entry)
    with tarfile.open(assets/'build-logs.tar.gz', 'w:gz') as bundle:
        for parent in (WORK/'logs', CACHE):
            for path in parent.rglob('*.log'):
                bundle.add(path, arcname=str(path.relative_to(parent.parent)))
    shutil.copyfile(WORK/'runtime-x11-audit.json', assets/'runtime-x11-audit.json')
    print('Built and validated ' + str(len(built)) + ' bottles; candidate metadata is ready.', flush=True)


def auth_git(repo, *args):
    return git(repo, '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential', *args)


def commit(repo, message):
    git(repo, 'config', 'user.name', 'Dimpase Intel Bottle Publisher')
    git(repo, 'config', 'user.email', 'intel-bottles@users.noreply.github.com')
    git(repo, 'add', '-A')
    if git(repo, 'diff', '--cached', '--name-only'):
        git(repo, 'commit', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


def stage(_args):
    state = json.loads(STATE.read_text())
    unpacked = WORK/'source'
    unpacked.mkdir(exist_ok=True)
    with tarfile.open(WORK/'candidate-formulae.tar.gz') as bundle:
        bundle.extractall(unpacked, filter='data')
    metadata_heads = {}
    branch = 'intel-candidate-' + os.environ['GITHUB_RUN_ID']
    for kind in REPOSITORIES:
        repo = WORK/('publish-' + kind)
        clone_stable(kind, repo)
        assert git(repo, 'rev-parse', 'HEAD') == state['stable_heads'][kind], 'Stable branch advanced during compilation'
        git(repo, 'checkout', '-b', branch)
        for directory in ('Formula', 'Aliases'):
            destination = repo/directory
            if destination.is_dir():
                shutil.rmtree(destination)
            source = unpacked/kind/directory
            if source.exists():
                shutil.copytree(source, destination, symlinks=True)
        metadata_heads[kind] = commit(repo, 'Update Intel bottle candidate [skip ci]')
        auth_git(repo, 'push', 'origin', 'HEAD:refs/heads/' + branch)
    assets = WORK/'assets'
    inventory_data = json.loads((WORK/'candidate-inventory.json').read_text())
    rows = {r['name']: r for r in inventory_data['formulae']}
    index = {'platform': 'sequoia', 'architecture': 'x86_64', 'prefix': '/usr/local', 'cellar': '/usr/local/Cellar',
        'core_repository': 'https://github.com/' + REPOSITORIES['core'] + '.git', 'core_commit': metadata_heads['core'],
        'm2_repository': 'https://github.com/' + REPOSITORIES['m2'] + '.git', 'm2_commit': metadata_heads['m2'],
        'release_url': 'https://github.com/' + REPOSITORIES['m2'] + '/releases/tag/' + state['tag'],
        'upstream_commits': state['upstream_heads'],
        'runtime_formulae': [rows[n] for n in state['runtime_names']],
        'bottles': json.loads((WORK/'built-bottles.json').read_text()),
        'reused_private_bottles': state['reused_private_bottles']}
    dump(assets/'index.json', index)
    template = (SCRIPT/'install-m2-intel.template.sh').read_text()
    for key, value in [('core_commit', metadata_heads['core']), ('m2_commit', metadata_heads['m2']),
                       ('release_root', 'https://github.com/' + REPOSITORIES['m2'] + '/releases/download/' + state['tag'])]:
        template, count = re.subn(r'^' + key + r'=.*$', lambda _m: key + '=' + value, template, count=1, flags=re.M)
        assert count == 1
    template, count = re.subn(r"(?<=printf '%s  %s\\n' )[0-9a-f]{64}", digest(assets/'index.json'), template, count=1)
    assert count == 1, 'Cannot replace installer index checksum'
    (assets/'install-m2-intel.sh').write_text(template)
    run(['bash', '-n', str(assets/'install-m2-intel.sh')])
    raw = json.loads((WORK/'upstream-inventory.json').read_text())
    baseline = {'release': index['release_url'], 'core_commit': metadata_heads['core'], 'm2_commit': metadata_heads['m2'],
        'upstream_core_commit': state['upstream_heads']['core'], 'upstream_m2_commit': state['upstream_heads']['m2'],
        'formulae': [{k: r[k] for k in ('name', 'version', 'recipe_sha256')} for r in raw['formulae'] if r['name'] in raw['runtime_names']]}
    dump(WORK/'next-baseline.json', baseline)
    m2_repo = WORK/'publish-m2'
    shutil.copyfile(assets/'install-m2-intel.sh', m2_repo/'install-m2-intel.sh')
    shutil.copyfile(assets/'index.json', m2_repo/'bottle-index.json')
    shutil.copyfile(SCRIPT.parent/'INTEL-UPDATES.md', m2_repo/'INTEL-UPDATES.md')
    shutil.copyfile(WORK/'next-baseline.json', m2_repo/'automation/intel-baseline.json')
    state['distribution_head'] = commit(m2_repo, 'Pin candidate installer and release index [skip ci]')
    auth_git(m2_repo, 'push', 'origin', 'HEAD:refs/heads/' + branch)
    state.update(metadata_heads=metadata_heads, candidate_branch=branch)
    dump(STATE, state)
    release = subprocess.run(['gh', 'release', 'view', state['tag'], '--repo', REPOSITORIES['m2'], '--json', 'isPrerelease'], capture_output=True, text=True)
    if release.returncode == 0:
        assert json.loads(release.stdout)['isPrerelease'], 'Never replace a verified release'
    else:
        run(['gh', 'release', 'create', state['tag'], '--repo', REPOSITORIES['m2'], '--target', metadata_heads['m2'],
             '--prerelease', '--latest=false', '--title', 'Intel bottle candidate ' + state['tag'],
             '--notes', 'Candidate bottles awaiting clean installation tests on Intel macOS 15 and 26.'])
    run(['gh', 'release', 'upload', state['tag'], '--repo', REPOSITORIES['m2'], '--clobber', *map(str, sorted(assets.iterdir()))])
    output('tag', state['tag'])
    print('Candidate staged at ' + index['release_url'], flush=True)


def verify_reports(index, evidence):
    expected = {r['name']: r['version'] for r in index['runtime_formulae']}
    platforms = set()
    for path in evidence.rglob('m2-intel-pour-report.json'):
        report = json.loads(path.read_text())
        assert report['core_commit'] == index['core_commit'] and report['m2_commit'] == index['m2_commit']
        assert {r['formula']: r['version'] for r in report['formulae']} == expected
        assert all(r['poured_from_bottle'] for r in report['formulae'])
        platforms.add(report['platform'])
    assert platforms == {'sequoia', 'tahoe'}, 'Need successful receipts from both Intel macOS versions'


def checksums(assets):
    (assets/'SHA256SUMS').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in sorted(assets.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))


def promote(_args):
    state = json.loads(STATE.read_text())
    assets = WORK/'assets'
    index = json.loads((assets/'index.json').read_text())
    verify_reports(index, Path('intel-evidence'))
    for kind, expected in state['stable_heads'].items():
        current = run(['gh', 'api', '-X', 'GET', 'repos/' + REPOSITORIES[kind] + '/git/ref/heads/intel-bottles', '--jq', '.object.sha'])
        assert current == expected, 'Stable branch advanced; refuse concurrent promotion'
    for path in Path('intel-evidence').rglob('m2-intel-pour-report.json'):
        report = json.loads(path.read_text())
        platform = report['platform']
        report['verification'] = {'workflow_url': 'https://github.com/' + REPOSITORIES['m2'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'],
            'linkage_test': 'passed', 'formula_test': 'passed', 'runtime_source_builds': 0}
        dump(assets/('clean-install-' + platform + '-report.json'), report)
    with tarfile.open(assets/'clean-install-logs.tar.gz', 'w:gz') as bundle:
        bundle.add('intel-evidence', arcname='clean-install-evidence')
    dump(assets/'publication.json', {'verified': True, 'platforms': ['sequoia', 'tahoe'], 'metadata_heads': state['metadata_heads'],
        'distribution_head': state['distribution_head'], 'previous_stable_heads': state['stable_heads']})
    checksums(assets)
    run(['gh', 'release', 'upload', state['tag'], '--repo', REPOSITORIES['m2'], '--clobber',
         *map(str, sorted(assets.iterdir()))])
    # Verify every server-side digest before advancing any working branch.
    release = json.loads(run(['gh', 'api', '-X', 'GET', 'repos/' + REPOSITORIES['m2'] + '/releases/tags/' + state['tag']]))
    for item in release['assets']:
        assert item['digest'] == 'sha256:' + digest(assets/item['name']), 'Published asset checksum mismatch'
    for kind, head in [('core', state['metadata_heads']['core']), ('m2', state['distribution_head'])]:
        repo = WORK/('promote-' + kind)
        clone_stable(kind, repo)
        git(repo, 'fetch', '--depth=3', 'origin', state['candidate_branch'])
        git(repo, 'checkout', '--detach', head)
        # Fast-forward only. Candidate commits descend from the recorded stable heads.
        auth_git(repo, 'push', 'origin', 'HEAD:refs/heads/intel-bottles')
    run(['gh', 'release', 'edit', state['tag'], '--repo', REPOSITORIES['m2'], '--prerelease=false', '--latest',
         '--title', 'Macaulay2 Intel bottles — ' + state['tag'], '--notes',
         'Verified clean bottle installation on Intel macOS 15 and 26. The installer pins both metadata snapshots. See index.json, SHA256SUMS, and the clean-install evidence.'])
    # The checker lives on main. Update only its data file, leaving workflow code unchanged.
    endpoint = 'repos/' + REPOSITORIES['m2'] + '/contents/automation/intel-baseline.json'
    old = json.loads(run(['gh', 'api', '-X', 'GET', endpoint + '?ref=main']))
    import base64
    payload = {'message': 'Record verified Intel bottle baseline [skip ci]', 'branch': 'main', 'sha': old['sha'],
               'content': base64.b64encode((WORK/'next-baseline.json').read_bytes()).decode()}
    run(['gh', 'api', '-X', 'PUT', endpoint, '--input', '-'], input_text=json.dumps(payload))
    print('Verified release published; both stable branches and monitoring baseline advanced.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--core-commit', required=True)
    prep.add_argument('--m2-commit', required=True)
    for command in ('build', 'stage', 'promote'):
        sub.add_parser(command)
    args = parser.parse_args()
    {'prepare': prepare, 'build': build, 'stage': stage, 'promote': promote}[args.command](args)


if __name__ == '__main__':
    main()
