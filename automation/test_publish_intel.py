import importlib.util
import json
from pathlib import Path
import tempfile
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


if __name__ == '__main__':
    unittest.main()
