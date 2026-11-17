"""One local training day: an 11 pm Eastern workout stays on its own day everywhere. Disposable data only."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import os
import sqlite3
import unittest
from unittest.mock import patch

from rackbook import local_day
from rackbook.progress import e1rm_by_session

EASTERN = dict(TZ="America/New_York")
# 11:35 pm Eastern on 15 November 2026, as the logger stores it (UTC).
LATE = "2026-11-16T04:35:00.000Z"
DAY = date(2026, 11, 15)


class FrozenClock(datetime):
    moment = datetime(2026, 11, 16, 4, 35, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.moment.astimezone(tz) if tz else cls.moment.replace(tzinfo=None)


class LocalDayTest(unittest.TestCase):
    def test_late_eastern_workout_is_its_local_day_not_the_utc_date(self):
        with patch.dict(os.environ, EASTERN):
            for value in (LATE, "2026-11-16T04:35:00+00:00", "2026-11-15T23:35:00-05:00",
                          datetime(2026, 11, 16, 4, 35), datetime(2026, 11, 16, 4, 35, tzinfo=timezone.utc)):
                self.assertEqual(local_day.local_day(value), DAY, value)
            self.assertEqual(local_day.local_day("2026-11-16T05:00:00Z"), date(2026, 11, 16))
            # Summer time: 11:30 pm EDT is 03:30 UTC.
            self.assertEqual(local_day.local_day("2026-07-05T03:30:00Z"), date(2026, 7, 4))

    def test_plain_days_and_blanks(self):
        with patch.dict(os.environ, EASTERN):
            self.assertEqual(local_day.local_day("2026-11-16"), date(2026, 11, 16))
            self.assertEqual(local_day.local_day(date(2026, 11, 16)), date(2026, 11, 16))
            for blank in (None, "", "not a date"):
                self.assertIsNone(local_day.local_day(blank))
                self.assertIsNone(local_day.local_day_text(blank))

    def test_utc_zone_and_unrecognized_tz(self):
        with patch.dict(os.environ, TZ="UTC"):
            self.assertEqual(local_day.local_day(LATE), date(2026, 11, 16))
        with patch.dict(os.environ, TZ="Not/AZone"):  # falls back to the server's own zone, never an error
            self.assertIsInstance(local_day.local_day(LATE), date)

    def test_today_follows_the_configured_zone(self):
        with patch.dict(os.environ, EASTERN):
            self.assertEqual(local_day.local_today(now=datetime(2026, 11, 16, 4, 35, tzinfo=timezone.utc)), DAY)
            self.assertEqual(local_day.local_today(now=datetime(2026, 11, 16, 5, 1, tzinfo=timezone.utc)), date(2026, 11, 16))

    def test_sql_filter_by_local_day(self):
        with patch.dict(os.environ, EASTERN), closing(sqlite3.connect(":memory:")) as conn:
            local_day.register(conn)
            conn.execute("CREATE TABLE s(workout_start TEXT)")
            conn.executemany("INSERT INTO s VALUES (?)", [(LATE,), ("2026-11-16T12:00:00Z",), (None,)])
            rows = conn.execute("SELECT workout_start FROM s WHERE local_day(workout_start)>=? AND local_day(workout_start)<=?",
                                (str(DAY), str(DAY))).fetchall()
            self.assertEqual(rows, [(LATE,)])


class ProgressDateTest(unittest.TestCase):
    def test_late_eastern_session_is_plotted_on_its_local_day(self):
        entries = [{"workout_id": "late", "workout_start_time": "2026-11-16T04:35:00+00:00", "set_type": "normal",
                    "weight_kg": 100, "reps": 5, "rpe": 8}]
        with patch.dict(os.environ, EASTERN):
            points = e1rm_by_session(entries, lambda rpe, reps: 0.8)
        self.assertEqual([p["date"] for p in points], [str(DAY)])


class AdviceDayTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from rackbook import main
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.host = Path(self.tmp.name) / "host.db"
        env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.tmp.name) / "logging.db"),
                         HEVY_FATIGUE_DB_PATH=str(self.host), **EASTERN)
        env.start(); self.addCleanup(env.stop); main.initialize()
        with closing(sqlite3.connect(self.host)) as db, db:
            db.executescript('''CREATE TABLE daily_readiness(date TEXT PRIMARY KEY,tiredness INTEGER,perceived_recovery INTEGER,
                sore_quad_dom INTEGER,sore_posterior INTEGER,sore_upper_push INTEGER,sore_upper_pull INTEGER,joint_upper INTEGER,joint_lower INTEGER);
                CREATE TABLE workout_sessions(hevy_workout_id TEXT,start_time TEXT,workout_date TEXT);
                CREATE TABLE workout_logs(id INTEGER PRIMARY KEY,workout_id TEXT,set_number INTEGER,weight_lbs REAL,reps INTEGER,rpe REAL,exercise_id TEXT);''')
            # A check-in already entered for the 16th (for example ahead of time) must not count yet at 11:35 pm on the 15th.
            db.execute("INSERT INTO daily_readiness(date,tiredness,perceived_recovery) VALUES (?,?,?)", ("2026-11-16", 1, 2))

    def test_advice_follow_up_uses_the_local_today_at_11pm_eastern(self):
        from rackbook import session_advice as advice
        from rackbook.database import get_db
        with closing(get_db()) as db, db:
            db.execute("PRAGMA foreign_keys=OFF")  # only the outcome row matters here, not the advisory it follows
            db.execute("INSERT INTO advisory_outcomes VALUES (?,?,?,?)", ("rec", "saved", str(DAY),
                json.dumps(dict(recommendation_id="rec", title="Squat", decision=None, intended=None,
                                actual=dict(working_sets=2), matched_intended_sets=None))))
        with patch.object(local_day, "datetime", FrozenClock):
            self.assertEqual(local_day.local_today(), DAY)
            self.assertIsNone(advice.outcomes("saved")[0]["next_checkin"])
            FrozenClock.moment += timedelta(hours=1)  # 12:35 am on the 16th: the next day has started
            try:
                self.assertEqual(advice.outcomes("saved")[0]["next_checkin"]["date"], "2026-11-16")
            finally:
                FrozenClock.moment -= timedelta(hours=1)


if __name__ == "__main__":
    unittest.main()
