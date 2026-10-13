import importlib.util
import json
from pathlib import Path
import tempfile
import os
import subprocess
import tarfile
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).with_name('publish-intel.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def row(name, dependencies=(), version='1', sha='same'):
    return {'name': name, 'version': version, 'recipe_sha256': sha,
            'dependencies': [{'name': n, 'build': build} for n, build in dependencies]}


class PublisherTests(unittest.TestCase):
    def test_runtime_change_rebuilds_dependents(self):
        old = [row('lib'), row('app', [('lib', False)]), row('tool')]
        new = [row('lib', version='2'), row('app', [('lib', False)]), row('tool')]
        self.assertEqual(publisher.affected_runtime(new, ['lib', 'app'], {'formulae': old}), {'lib', 'app'})

    def test_same_version_recipe_change_is_not_reused(self):
        self.assertEqual(publisher.affected_runtime([row('lib', sha='new')], ['lib'], {'formulae': [row('lib')]}), {'lib'})

    def test_build_only_tool_is_not_a_runtime_abi_change(self):
        rows = [row('tool', version='2'), row('app', [('tool', True)])]
        self.assertEqual(publisher.affected_runtime(rows, ['app'], {'formulae': [row('app', [('tool', True)])]}), set())

    def test_dependency_order_and_cycle(self):
        self.assertEqual(publisher.topological([row('app', [('lib', False)]), row('lib')]), ['lib', 'app'])
        with self.assertRaises(ValueError):
            publisher.topological([row('app', [('app', False)])])

    def test_overlay_preserves_other_platforms(self):
        source = 'class Example < Formula\n  bottle do\n    sha256 arm64_sequoia: "arm"\n  end\n\n  def install\n  end\nend\n'
        metadata = {'bottle_metadata': {'root_url': 'https://example.com', 'cellar': 'any', 'rebuild': 2,
                    'tags': {'sequoia': {'sha256': 'intel'}}}}
        result = publisher.append_overlay(source, publisher.bottle_overlay(metadata))
        self.assertIn('sha256 arm64_sequoia: "arm"', result)
        self.assertIn('sha256 cellar: :any, sequoia: "intel"', result)
        self.assertEqual(len(publisher.OVERLAY_RE.findall(result)), 1)
        with self.assertRaises(AssertionError):
            publisher.append_overlay(result, publisher.bottle_overlay(metadata))

    def test_installer_checksum_replacement(self):
        import re
        template = Path(__file__).with_name('install-m2-intel.template.sh').read_text()
        updated, count = re.subn(r"(?<=printf '%s  %s\\n' )[0-9a-f]{64}", 'a' * 64, template, count=1)
        self.assertEqual(count, 1)
        self.assertIn('a' * 64, updated)

    def test_both_clean_receipts_required(self):
        index = {'core_commit': 'core', 'm2_commit': 'm2', 'runtime_formulae': [{'name': 'app', 'version': '1'}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for platform in ['sequoia', 'tahoe']:
                path = root/platform
                path.mkdir()
                report = {'core_commit': 'core', 'm2_commit': 'm2', 'platform': platform,
                          'formulae': [{'formula': 'app', 'version': '1', 'poured_from_bottle': True}]}
                (path/'m2-intel-pour-report.json').write_text(json.dumps(report))
            publisher.verify_reports(index, root)
            bad = json.loads((root/'tahoe/m2-intel-pour-report.json').read_text())
            bad['formulae'][0]['poured_from_bottle'] = False
            (root/'tahoe/m2-intel-pour-report.json').write_text(json.dumps(bad))
            with self.assertRaises(AssertionError):
                publisher.verify_reports(index, root)


    def test_stage_pins_metadata_before_installer_commit(self):
        # Exercise real local Git commits and asset generation, with all GitHub calls disabled.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root/"work"
            work.mkdir()
            assets = work/"assets"
            assets.mkdir()
            (assets/"example.bottle.tar.gz").write_bytes(b"fixture")
            stable = {}
            heads = {}
            for kind in ("core", "m2"):
                repo = root/("stable-"+kind)
                repo.mkdir()
                subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
                (repo/"Formula").mkdir()
                (repo/"Formula/example.rb").write_text("old recipe\n")
                (repo/"automation").mkdir()
                (repo/"automation/intel-baseline.json").write_text("{}\n")
                (repo/".github/workflows").mkdir(parents=True)
                (repo/".github/workflows/retained.yml").write_text("preserve this workflow\n")
                heads[kind] = publisher.commit(repo, "Fixture stable")
                stable[kind] = repo
            source = root/"source"
            for kind in ("core", "m2"):
                (source/kind/"Formula").mkdir(parents=True)
                (source/kind/"Formula/example.rb").write_text("new recipe\n")
            with tarfile.open(work/"candidate-formulae.tar.gz", "w:gz") as bundle:
                for kind in ("core", "m2"):
                    bundle.add(source/kind/"Formula", arcname=kind+"/Formula")
            inventory = {"runtime_names": ["macaulay2/tap/macaulay2"], "formulae": [row("macaulay2/tap/macaulay2")]}
            publisher.dump(work/"candidate-inventory.json", inventory)
            publisher.dump(work/"upstream-inventory.json", inventory)
            publisher.dump(work/"built-bottles.json", [])
            publisher.dump(work/"state.json", {"tag":"intel-bottles-1234", "stable_heads":heads,
                "upstream_heads":{"core":"1"*40,"m2":"2"*40}, "runtime_names":inventory["runtime_names"],
                "reused_private_bottles":[]})
            actual_run = publisher.run
            actual_subprocess_run = subprocess.run
            calls = []
            def clone(kind, destination):
                actual_run(["git", "clone", "-q", str(stable[kind]), str(destination)])
                return publisher.git(destination,"rev-parse","HEAD")
            def external(args, **kwargs):
                if args[0] == "gh":
                    self.assertEqual(args[1:3] in [["release","create"],["release","upload"]], True)
                    calls.append(args)
                    return ""
                return actual_run(args, **kwargs)
            def direct(args, **kwargs):
                if args[0] == "gh":
                    self.assertEqual(args[1:3],["release","view"])
                    return subprocess.CompletedProcess(args,1,"","")
                return actual_subprocess_run(args, **kwargs)
            with patch.object(publisher,"WORK",work), patch.object(publisher,"STATE",work/"state.json"), \
                 patch.object(publisher,"clone_stable",clone), patch.object(publisher,"auth_git",lambda *args: None), \
                 patch.object(publisher,"run",external), patch.object(publisher.subprocess,"run",direct), \
                 patch.dict(os.environ,{"GITHUB_RUN_ID":"1234"}):
                publisher.stage(None)
            state = json.loads((work/"state.json").read_text())
            index = json.loads((assets/"index.json").read_text())
            self.assertEqual(index["m2_commit"],state["metadata_heads"]["m2"])
            self.assertNotEqual(index["m2_commit"],state["distribution_head"])
            script = (assets/"install-m2-intel.sh").read_text()
            self.assertIn("m2_commit="+index["m2_commit"],script)
            self.assertIn(publisher.digest(assets/"index.json"),script)
            for kind in ("core", "m2"):
                self.assertEqual((work/("publish-"+kind)/".github/workflows/retained.yml").read_text(),"preserve this workflow\n")
                self.assertEqual(publisher.git(stable[kind],"rev-parse","HEAD"),heads[kind])
            self.assertEqual(len(calls),2)


if __name__ == '__main__':
    unittest.main()
