"""The TS: the set you mark when you save a workout. Its e1RM, times the TM percentage, is the movement's TM."""
import csv
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from unittest import mock

import httpx

warnings.filterwarnings("ignore", category=ResourceWarning)

_IMPORT_DIR = tempfile.mkdtemp()
os.environ.setdefault("RACKBOOK_DB_PATH", os.path.join(_IMPORT_DIR, "import.db"))

from fastapi.testclient import TestClient  # noqa: E402

from rackbook import main  # noqa: E402
from rackbook import training_max  # noqa: E402

USER_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "rpe_chart_user.csv")
with open(USER_CSV, newline="", encoding="utf-8") as f:
    _TABLE = {(float(r["rpe"]), int(r["reps"])): float(r["percentage"]) for r in csv.DictReader(f)}


def pct(rpe, reps):
    return _TABLE.get((float(rpe), int(reps)))


def entry(*sets, template="tpl-squat", start="2026-10-09T17:00:00Z"):
    return {
        "title": "Day 3", "start_time": start, "end_time": "2026-10-09T18:00:00Z",
        "exercises": [{"exercise_template_id": template, "title": "Squat, Low Bar w/ Belt", "sets": list(sets)}],
    }


def S(lb, reps, rpe, type="normal", ts=False):
    # the page sends kg; the tests think in the lb the e1RM sheet uses
    return {"type": type, "weight_kg": None if lb is None else lb / 2.20462, "reps": reps, "rpe": rpe, "ts": ts}


class TestTsRowsFromEntry(unittest.TestCase):

    def test_the_marked_set_becomes_the_ts_with_its_e1rm(self):
        rows = training_max.ts_rows_from_entry(entry(S(265, 5, 6), S(292, 5, 8, ts=True)), pct)
        self.assertEqual(1, len(rows))
        self.assertEqual(("tpl-squat", 292, 5, 8.0), (rows[0]["exercise_template_id"], rows[0]["weight_lb"], rows[0]["reps"], rows[0]["rpe"]))
        self.assertEqual(round(292 / 0.826, 1), rows[0]["e1rm_lb"])

    def test_no_marked_set_means_no_ts(self):
        self.assertEqual([], training_max.ts_rows_from_entry(entry(S(265, 5, 6), S(292, 5, 8)), pct))

    def test_each_exercise_can_have_its_own_ts(self):
        e = entry(S(292, 5, 8, ts=True))
        e["exercises"].append({"exercise_template_id": "tpl-bench", "title": "Bench", "sets": [S(200, 5, 8, ts=True)]})
        rows = training_max.ts_rows_from_entry(e, pct)
        self.assertEqual(["tpl-squat", "tpl-bench"], [r["exercise_template_id"] for r in rows])

    def test_two_ts_in_one_exercise_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "one TS"):
            training_max.ts_rows_from_entry(entry(S(265, 5, 6, ts=True), S(292, 5, 8, ts=True)), pct)

    def test_a_ts_needs_weight_reps_and_an_rpe(self):
        for bad in (S(None, 5, 8, ts=True), S(292, None, 8, ts=True), S(292, 0, 8, ts=True), S(292, 5, None, ts=True)):
            with self.assertRaisesRegex(ValueError, "TS"):
                training_max.ts_rows_from_entry(entry(bad), pct)

    def test_a_set_the_rpe_table_cannot_price_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "RPE table"):
            training_max.ts_rows_from_entry(entry(S(100, 28, 5, ts=True)), pct)

    def test_a_warmup_cannot_be_the_ts(self):
        with self.assertRaisesRegex(ValueError, "warm-up"):
            training_max.ts_rows_from_entry(entry(S(135, 5, 6, type="warmup", ts=True)), pct)


class TrainingMaxCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {"RACKBOOK_DB_PATH": os.path.join(self.tmp, "t.db"), "RPE_CHART_PATH": USER_CSV})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        patcher = mock.patch("rackbook.main.hevy_client.HevyClient")
        self.hevy_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.hevy = self.hevy_cls.return_value
        self.hevy.create_workout.side_effect = lambda body: {'id': str(__import__('uuid').uuid4())}

    def _save(self, e):
        return self.client.post("/hevy/workouts", json=e)

    def _tm(self, template="tpl-squat"):
        return self.client.get(f"/training-max/{template}").json()


class TestStoredTs(TrainingMaxCase):

    def test_no_ts_yet(self):
        self.assertEqual({"found": False}, {"found": self._tm()["found"]})
        self.assertIsNone(self._tm()["e1rm_lb"])

    def test_saving_a_workout_stores_its_ts(self):
        self.assertEqual(200, self._save(entry(S(265, 5, 6), S(292, 5, 8, ts=True))).status_code)
        tm = self._tm()
        self.assertTrue(tm["found"])
        self.assertEqual((292, 5, 8.0, "2026-10-09T17:00:00Z"), (tm["weight_lb"], tm["reps"], tm["rpe"], tm["set_at"]))
        self.assertEqual(round(292 / 0.826, 1), tm["e1rm_lb"])

    def test_a_workout_without_a_ts_leaves_the_tm_alone(self):
        self._save(entry(S(292, 5, 8, ts=True)))
        self._save(entry(S(300, 5, 9), start="2026-10-12T17:00:00Z"))
        self.assertEqual(292, self._tm()["weight_lb"])

    def test_a_later_ts_replaces_the_earlier_one_even_when_it_is_lower(self):
        self._save(entry(S(292, 5, 8, ts=True), start="2026-10-02T17:00:00Z"))
        self._save(entry(S(281, 5, 7, ts=True), start="2026-10-09T17:00:00Z"))
        self.assertEqual(281, self._tm()["weight_lb"])

    def test_the_newest_workout_wins_even_if_it_was_saved_first(self):
        self._save(entry(S(281, 5, 7, ts=True), start="2026-10-09T17:00:00Z"))
        self._save(entry(S(292, 5, 8, ts=True), start="2026-10-02T17:00:00Z"))   # an older workout saved late
        self.assertEqual(281, self._tm()["weight_lb"])

    def test_movements_are_kept_apart(self):
        self._save(entry(S(292, 5, 8, ts=True)))
        self.assertFalse(self._tm("tpl-bench")["found"])

    def test_every_ts_is_kept_so_the_trend_can_be_shown_later(self):
        self._save(entry(S(281, 5, 7, ts=True), start="2026-10-02T17:00:00Z"))
        self._save(entry(S(292, 5, 8, ts=True), start="2026-10-09T17:00:00Z"))
        with main.get_db() as conn:
            self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM training_max_history").fetchone()[0])


class TestBadTsStopsTheSave(TrainingMaxCase):

    def test_an_unusable_ts_is_a_422_and_nothing_is_sent_or_stored(self):
        r = self._save(entry(S(292, 5, None, ts=True)))
        self.assertEqual(422, r.status_code)
        self.assertIn("TS", r.json()["detail"])
        self.hevy.create_workout.assert_not_called()
        self.assertFalse(self._tm()["found"])

    def test_if_hevy_fails_the_tm_does_not_change(self):
        self.hevy.create_workout.side_effect = httpx.ConnectError("down")
        self.assertEqual(502, self._save(entry(S(292, 5, 8, ts=True))).status_code)
        self.assertFalse(self._tm()["found"])


if __name__ == "__main__":
    unittest.main()
