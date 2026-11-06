"""Tests for body_weight.sync_body_measurements. The Hevy client is a fake: no network."""
import os
import sys
import tempfile
import unittest
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

_DIR = tempfile.mkdtemp()
os.environ["RACKBOOK_DB_PATH"] = os.path.join(_DIR, "rackbook.body_weight.db")

from rackbook import body_weight  # noqa: E402
from rackbook.database import get_db, init_db  # noqa: E402


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def list_body_measurements(self, page=1, page_size=10):
        self.requested.append(page)
        return {"page": page, "page_count": len(self.pages), "body_measurements": self.pages[page - 1]}


class SyncBodyMeasurementsTest(unittest.TestCase):
    def setUp(self):
        init_db()
        with get_db() as conn:
            conn.execute("DELETE FROM body_measurements")

    def test_pages_through_everything_and_stores_by_date(self):
        client = FakeClient([
            [{"date": "2026-10-11", "weight_kg": 76.9}],
            [{"date": "2026-10-10", "weight_kg": 77.5, "lean_mass_kg": 64.1, "fat_percent": 17.3}],
        ])
        self.assertEqual(body_weight.sync_body_measurements(client), 2)
        self.assertEqual(client.requested, [1, 2])
        rows = body_weight.list_body_measurements()
        self.assertEqual([r["date"] for r in rows], ["2026-10-10", "2026-10-11"])  # oldest first
        self.assertEqual(rows[0]["lean_mass_kg"], 64.1)
        self.assertIsNone(rows[1]["lean_mass_kg"])

    def test_resync_updates_a_revised_day_without_duplicating(self):
        body_weight.sync_body_measurements(FakeClient([[{"date": "2026-10-11", "weight_kg": 76.9}]]))
        body_weight.sync_body_measurements(FakeClient([[{"date": "2026-10-11", "weight_kg": 77.2}]]))
        rows = body_weight.list_body_measurements()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["weight_kg"], 77.2)

    def test_days_without_weight_are_skipped(self):
        client = FakeClient([[{"date": "2026-10-11", "fat_percent": 17.0}, {"date": "2026-10-10", "weight_kg": 77.5}]])
        self.assertEqual(body_weight.sync_body_measurements(client), 1)

    def test_empty_account_stores_nothing(self):
        client = FakeClient([[]])
        self.assertEqual(body_weight.sync_body_measurements(client), 0)
        self.assertEqual(body_weight.list_body_measurements(), [])


if __name__ == "__main__":
    unittest.main()
