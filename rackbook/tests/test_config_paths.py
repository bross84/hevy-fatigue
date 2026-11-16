import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rackbook.config import monitoring_read_path_problem


class MonitoringReadPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.host = Path(self.tmp.name) / 'host.db'

    def test_matching_path_is_fine(self):
        with patch.dict(os.environ, {'HEVY_FATIGUE_DB_PATH': str(self.host)}):
            self.assertIsNone(monitoring_read_path_problem(str(self.host)))

    def test_missing_path_is_reported(self):
        with patch.dict(os.environ, {'HEVY_FATIGUE_DB_PATH': ''}):
            self.assertIn('not set', monitoring_read_path_problem(str(self.host)))

    def test_different_path_is_reported(self):
        other = Path(self.tmp.name) / 'other.db'
        with patch.dict(os.environ, {'HEVY_FATIGUE_DB_PATH': str(other)}):
            self.assertIn('different file', monitoring_read_path_problem(str(self.host)))


if __name__ == '__main__':
    unittest.main()
