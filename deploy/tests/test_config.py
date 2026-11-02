"""Regression checks for deployment drift detection; no Docker or app imports."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'check_config.py'
spec = importlib.util.spec_from_file_location('deployment_config', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DriftChecks(unittest.TestCase):
    def test_comparison_detects_changed_flags_pin_and_storage(self):
        expected = {'services': {'app': {'image': 'pinned', 'environment': {'writes': '1'}}},
                    'volumes': {'data': {'name': 'existing', 'external': True}}}
        actual = copy.deepcopy(expected)
        actual['services']['app']['environment']['writes'] = '0'
        actual['services']['app']['image'] = 'latest'
        actual['volumes']['data']['external'] = False
        self.assertEqual(checker.differences(expected, actual), [
            '$.services.app.environment.writes', '$.services.app.image', '$.volumes.data.external'])
        self.assertEqual(checker.differences(expected, json.loads(json.dumps(expected))), [])

    def test_comparison_does_not_ignore_extra_settings_or_missing_metadata(self):
        self.assertEqual(checker.differences({'x-casaos': {'title': 'kept'}}, {}), ['$.x-casaos'])
        self.assertEqual(checker.differences({}, {'unexpected': 'value'}), ['$.unexpected'])
        self.assertEqual(checker.differences({'flag': '1'}, {'flag': 1}), ['$.flag'])
        self.assertEqual(checker.differences({'ports': [1]}, {'ports': [1, 2]}), ['$.ports'])

    def test_cli_reports_only_field_paths_and_never_setting_values(self):
        with tempfile.TemporaryDirectory() as directory:
            expected, actual = Path(directory)/'expected.json', Path(directory)/'actual.json'
            expected.write_text(json.dumps({'resolved_configuration': {'environment': {'key': 'private-before'}}}))
            actual.write_text(json.dumps({'environment': {'key': 'private-after'}}))
            result = subprocess.run([sys.executable, str(SCRIPT), 'compare', str(expected), str(actual)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('$.environment.key', result.stdout)
            self.assertNotIn('private-before', result.stdout+result.stderr)
            self.assertNotIn('private-after', result.stdout+result.stderr)
            result = subprocess.run([sys.executable, str(SCRIPT), 'compare', str(actual), '-'],
                                    input=actual.read_text(), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


class ProductionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Compose rendering is read-only and never creates a container/volume.
        source = SCRIPT.parent/'production.compose.yml'
        cls.config = json.loads(subprocess.check_output(
            ['docker', 'compose', '-f', str(source), 'config', '--format', 'json'], text=True))

    def test_tracked_configuration_satisfies_production_contract(self):
        self.assertEqual(checker.validate(self.config), [])

    def test_mutable_image_and_build_cannot_replace_pinned_release(self):
        changed = copy.deepcopy(self.config)
        changed['services']['hevy-fatigue']['image'] = 'ghcr.io/bross84/hevy-fatigue:latest'
        changed['services']['hevy-fatigue']['build'] = '.'
        errors = checker.validate(changed)
        self.assertIn('$.services.hevy-fatigue.image', errors)
        self.assertIn('$.services.hevy-fatigue.build', errors)

    def test_empty_replacement_volume_and_swapped_database_mount_are_rejected(self):
        changed = copy.deepcopy(self.config)
        changed['volumes']['hevy-data']['external'] = False
        changed['services']['hevy-fatigue']['volumes'][1]['source'] = 'hevy-data'
        errors = checker.validate(changed)
        self.assertIn('$.volumes.hevy-data', errors)
        self.assertIn('$.services.hevy-fatigue.volumes', errors)

    def test_write_flags_and_credential_paths_cannot_drift(self):
        changed = copy.deepcopy(self.config)
        env = changed['services']['hevy-fatigue']['environment']
        env['HEVY_WRITES_ENABLED'] = '0'
        env['RACKBOOK_READ_ONLY_PREVIEW'] = '1'
        env['FERNET_KEY_PATH'] = '/training-data/app.key'
        env['HEVY_API_KEY'] = 'fake-private-value'
        errors = checker.validate(changed)
        for key in ('HEVY_WRITES_ENABLED', 'RACKBOOK_READ_ONLY_PREVIEW', 'FERNET_KEY_PATH', 'HEVY_API_KEY'):
            self.assertIn('$.services.hevy-fatigue.environment.'+key, errors)
        self.assertNotIn('fake-private-value', json.dumps(errors))

    def test_second_writer_and_changed_port_are_rejected(self):
        changed = copy.deepcopy(self.config)
        changed['services']['rackbook'] = {'image': 'old-logger'}
        changed['services']['hevy-fatigue']['ports'][0]['published'] = '8126'
        errors = checker.validate(changed)
        self.assertIn('$.services', errors)
        self.assertIn('$.services.hevy-fatigue.ports', errors)


if __name__ == '__main__':
    unittest.main()
