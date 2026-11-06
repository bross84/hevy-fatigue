"""
The user's own RPE table (data/rpe_chart_user.csv): how it is built, how the app loads it, and that it
reproduces every e1RM in the user's spreadsheet.
"""
import csv
import math
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from rackbook import database  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
USER_CSV = os.path.join(DATA, "rpe_chart_user.csv")
BUILTIN_CSV = os.path.join(DATA, "rpe_chart.csv")

# The user's RPE 10 row (reps 1..30) in percent; every other row is derived from it (see test below).
BASE_PCT = [100.0, 96.0, 93.3, 90.6, 87.9, 85.3, 82.6, 79.9, 77.3, 74.6, 71.9, 69.2, 66.6, 63.9, 61.2,
            58.6, 55.9, 53.2, 50.5, 47.9, 45.2, 42.5, 39.9, 37.2, 34.5, 31.8, 29.2, 26.5, 23.8, 21.2]

# (weight in lb as typed, reps, RPE, e1RM in lb shown by the user's spreadsheet)
SHEET_ROWS = [
    (265, 5, 6, 343), (281, 5, 7, 352), (292, 5, 8, 354),
    (193, 5, 6, 250), (220, 5, 7.5, 271), (231, 5, 8.5, 275),
    (209, 8, 5, 314), (215, 8, 6, 311), (226, 8, 7, 314),
    (83, 8, 5, 125), (88, 8, 6, 127), (94, 8, 7, 131),
    (198, 8, 5, 297), (204, 8, 6, 295), (209, 8, 7, 291),
    (314, 5, 6, 406), (347, 3, 7, 407), (380, 1, 8, 407),
    (215, 5, 6, 278), (220, 5, 7, 275), (243, 3, 8, 276), (193, 8, 6, 279),
    (276, 5, 6, 357), (287, 5, 7, 359), (314, 3, 8, 357), (215, 8, 5, 323),
]


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {(float(r["rpe"]), int(r["reps"])): float(r["percentage"]) for r in csv.DictReader(f)}


def _expected(rpe, reps):
    """The sheet's formulas: RIR = 10 - RPE; a whole RIR shifts the RPE 10 row, a half RIR averages two rows."""
    rir = 10 - rpe
    lo, hi = math.floor(rir), math.ceil(rir)
    if reps + hi > 30:
        return None
    return (BASE_PCT[reps + lo - 1] + BASE_PCT[reps + hi - 1]) / 200


class TestUserTableFile(unittest.TestCase):

    def setUp(self):
        self.table = _read(USER_CSV)

    def test_every_cell_follows_the_sheets_formulas_from_the_rpe_10_row(self):
        for (rpe, reps), pct in self.table.items():
            self.assertAlmostEqual(_expected(rpe, reps), pct, places=4, msg=f"RPE {rpe} x {reps}")

    def test_covers_rpe_0_to_10_in_half_steps(self):
        self.assertEqual({10 - i / 2 for i in range(21)}, {rpe for rpe, _ in self.table})

    def test_cells_the_base_row_cannot_reach_are_absent(self):
        # reps + RIR > 30 is outside the 30-value base row the user supplied.
        self.assertNotIn((5.0, 26), self.table)
        self.assertIn((5.0, 25), self.table)

    def test_known_cells(self):
        self.assertEqual(1.0, self.table[(10.0, 1)])
        self.assertAlmostEqual(0.826, self.table[(8.0, 5)], places=4)    # displays as 83%
        self.assertAlmostEqual(0.773, self.table[(6.0, 5)], places=4)    # displays as 77%
        self.assertAlmostEqual(0.933, self.table[(9.0, 2)], places=4)    # RIR 1 shifts the RPE 10 row by one rep
        self.assertAlmostEqual((0.96 + 0.933) / 2, self.table[(9.5, 2)], places=4)  # half step is an average

    def test_reproduces_every_e1rm_in_the_users_sheet(self):
        # The sheet computes e1RM = weight in lb / table percentage, using the lb as typed.
        for lb, reps, rpe, sheet in SHEET_ROWS:
            self.assertEqual(sheet, round(lb / self.table[(float(rpe), reps)]), f"{lb} x {reps} @{rpe}")


class TestLoadingIntoTheDatabase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = mock.patch.dict(os.environ, {"RACKBOOK_DB_PATH": os.path.join(self.tmp, "t.db")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("RPE_CHART_PATH", None)

    def _chart(self):
        conn = sqlite3.connect(os.environ["RACKBOOK_DB_PATH"])
        try:
            return {(r[0], r[1]): r[2] for r in conn.execute("SELECT rpe, reps, percentage FROM rpe_chart")}
        finally:
            conn.close()

    def test_a_fresh_database_gets_the_users_table_by_default(self):
        database.init_db()
        self.assertEqual(_read(USER_CSV), self._chart())
        self.assertAlmostEqual(0.826, database.get_rpe_percentage(8.0, 5), places=4)

    def test_an_existing_database_with_the_old_table_is_switched_to_the_users_table(self):
        os.environ["RPE_CHART_PATH"] = BUILTIN_CSV
        database.init_db()
        self.assertEqual(0.83, database.get_rpe_percentage(8.0, 5))
        os.environ.pop("RPE_CHART_PATH")
        database.init_db()
        self.assertEqual(_read(USER_CSV), self._chart())

    def test_restart_with_the_same_file_does_not_reload(self):
        database.init_db()
        conn = sqlite3.connect(os.environ["RACKBOOK_DB_PATH"])
        conn.execute("UPDATE rpe_chart SET percentage = 0.5 WHERE rpe = 10.0 AND reps = 1")
        conn.commit()
        conn.close()
        database.init_db()  # same file hash: leaves the table alone
        self.assertEqual(0.5, database.get_rpe_percentage(10.0, 1))

    def test_missing_pair_returns_none(self):
        database.init_db()
        self.assertIsNone(database.get_rpe_percentage(5.0, 26))
        self.assertIsNone(database.get_rpe_percentage(8.25, 5))


if __name__ == "__main__":
    unittest.main()
