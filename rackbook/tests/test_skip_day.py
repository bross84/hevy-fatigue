"""Skipping a microcycle day: finished for plan progress, recorded as skipped. Temporary SQLite; Hevy never called."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from fastapi.testclient import TestClient
from unittest.mock import patch
from rackbook import main, mesocycles, session_checkins, workout_saves
from rackbook.database import get_db, init_db


def plan_input(name='Push and pull', days=('day1', 'day2', 'day3')):
    return mesocycles.PlanInput(name=name, weeks=[dict(name='Microcycle', sessions=[
        dict(id=d, name=d.title(), exercises=[]) for d in days])])


class SkipCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        previous = os.environ.get('RACKBOOK_DB_PATH')
        os.environ['RACKBOOK_DB_PATH'] = os.path.join(self.tmp, 'test.db')
        self.addCleanup(lambda: os.environ.__setitem__('RACKBOOK_DB_PATH', previous) if previous else os.environ.pop('RACKBOOK_DB_PATH', None))
        init_db()
        workout_saves.initialize()
        self.plan_id = mesocycles.save_plan(plan_input())['id']

    def rows(self, plan_id=None):
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT session_id, hevy_workout_id, outcome, note FROM mesocycle_completions WHERE mesocycle_id = ? ORDER BY session_id',
                (plan_id or self.plan_id,))]

    def train(self, session_id, plan_id=None, start=None):
        with get_db() as conn:
            conn.execute('INSERT INTO mesocycle_completions (mesocycle_id,session_id,hevy_workout_id,workout_start) VALUES (?,?,?,?)',
                         (plan_id or self.plan_id, session_id, f'h-{session_id}', (start or datetime.now(timezone.utc)).isoformat()))

    def active(self):
        with get_db() as conn:
            return conn.execute('SELECT active FROM mesocycles WHERE id = ?', (self.plan_id,)).fetchone()['active']

    # -- the action ---------------------------------------------------------------------------------

    def test_a_skip_resolves_the_day_but_is_recorded_as_skipped(self):
        view = mesocycles.skip_day(self.plan_id, 'day3', '  Pull-ups after day 1  ')
        done = {c['session_id']: c for c in view['completed']}
        self.assertEqual(('skipped', 'Pull-ups after day 1', None),
                         (done['day3']['outcome'], done['day3']['note'], done['day3']['hevy_workout_id']))
        self.assertEqual([dict(session_id='day3', hevy_workout_id=None, outcome='skipped', note='Pull-ups after day 1')], self.rows())

    def test_a_blank_note_is_stored_as_none_and_a_long_one_is_trimmed(self):
        mesocycles.skip_day(self.plan_id, 'day1', '   ')
        mesocycles.skip_day(self.plan_id, 'day2', 'x' * 500)
        notes = {r['session_id']: r['note'] for r in self.rows()}
        self.assertIsNone(notes['day1'])
        self.assertEqual(mesocycles.SKIP_NOTE_CHARS, len(notes['day2']))

    def test_skipping_the_last_unresolved_day_finishes_and_deactivates_the_plan(self):
        mesocycles.activate(self.plan_id)
        self.train('day1')
        mesocycles.skip_day(self.plan_id, 'day2')
        self.assertEqual(1, self.active(), 'one day is still open')
        mesocycles.skip_day(self.plan_id, 'day3')
        self.assertEqual(0, self.active())

    def test_conflicts_are_explicit_and_change_nothing(self):
        self.train('day1')
        mesocycles.skip_day(self.plan_id, 'day2')
        before = self.rows()
        for session_id, status in (('day1', 409), ('day2', 409), ('missing', 404)):
            with self.assertRaises(mesocycles.PlanError) as caught:
                mesocycles.skip_day(self.plan_id, session_id)
            self.assertEqual(status, caught.exception.status, session_id)
        mesocycles.archive(self.plan_id)
        with self.assertRaises(mesocycles.PlanError):
            mesocycles.skip_day(self.plan_id, 'day3')
        self.assertEqual(before, self.rows())

    def test_undo_restores_only_a_skipped_day(self):
        self.train('day1')
        mesocycles.mark_completed(self.plan_id, 'day2')
        mesocycles.skip_day(self.plan_id, 'day3')
        for session_id in ('day1', 'day2'):
            with self.assertRaises(mesocycles.PlanError):
                mesocycles.undo_skip(self.plan_id, session_id)
        view = mesocycles.undo_skip(self.plan_id, 'day3')
        self.assertEqual({'day1', 'day2'}, {c['session_id'] for c in view['completed']})
        self.assertEqual(['day1', 'day2'], [r['session_id'] for r in self.rows()])

    def test_the_manual_completion_actions_never_touch_a_skip(self):
        mesocycles.skip_day(self.plan_id, 'day1', 'keep me')
        with self.assertRaises(mesocycles.PlanError) as caught:
            mesocycles.mark_completed(self.plan_id, 'day1')
        self.assertIn('Undo the skip', str(caught.exception))
        with self.assertRaises(mesocycles.PlanError):
            mesocycles.undo_manual_completion(self.plan_id, 'day1')
        self.assertEqual([dict(session_id='day1', hevy_workout_id=None, outcome='skipped', note='keep me')], self.rows())

    def test_a_skipped_day_cannot_be_trained_until_the_skip_is_undone(self):
        link = mesocycles.PlanLink(mesocycle_id=self.plan_id, session_id='day1')
        mesocycles.skip_day(self.plan_id, 'day1')
        with self.assertRaises(mesocycles.PlanError):
            mesocycles.validate_save(link, datetime.now(timezone.utc).isoformat())
        mesocycles.undo_skip(self.plan_id, 'day1')
        self.assertIsNone(mesocycles.validate_save(link, datetime.now(timezone.utc).isoformat()))

    def test_a_skip_writes_nothing_but_its_own_row(self):
        with get_db() as conn:
            before = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                      for t in ('mesocycles', 'logged_sets', 'workout_saves', 'session_checkins')}
        mesocycles.skip_day(self.plan_id, 'day2', 'rest')
        with get_db() as conn:
            after = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in before}
            self.assertEqual(before, after)
            self.assertEqual(1, conn.execute('SELECT COUNT(*) FROM mesocycle_completions').fetchone()[0])

    # -- the upgrade --------------------------------------------------------------------------------

    def test_an_older_database_gains_the_columns_and_keeps_its_completions(self):
        path = os.path.join(self.tmp, 'older.db')
        with closing(sqlite3.connect(path)) as conn:
            conn.executescript("""
                CREATE TABLE mesocycles (id TEXT PRIMARY KEY, document TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                    active INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE mesocycle_completions (mesocycle_id TEXT NOT NULL, session_id TEXT NOT NULL, hevy_workout_id TEXT,
                    workout_start TEXT NOT NULL, completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (mesocycle_id, session_id));
                INSERT INTO mesocycle_completions (mesocycle_id, session_id, hevy_workout_id, workout_start) VALUES ('p', 'd', 'h', '2026-11-01T10:00:00+00:00');
            """)
            conn.commit()
        os.environ['RACKBOOK_DB_PATH'] = path
        init_db()
        init_db()  # idempotent
        with closing(sqlite3.connect(path)) as conn:
            columns = {r[1] for r in conn.execute('PRAGMA table_info(mesocycle_completions)')}
            self.assertTrue({'outcome', 'note'} <= columns)
            self.assertEqual(('completed', None), conn.execute('SELECT outcome, note FROM mesocycle_completions').fetchone())
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO mesocycle_completions (mesocycle_id, session_id, workout_start, outcome) VALUES ('p','x','t','bogus')")

    # -- the routes ---------------------------------------------------------------------------------

    def test_routes_skip_and_undo_and_validate_the_note(self):
        with patch('rackbook.main.hevy_client.HevyClient') as hevy, TestClient(main.app) as client:
            base = f'/api/mesocycles/{self.plan_id}/sessions'
            posted = client.post(f'{base}/day1/skip', json=dict(note='Doing pull-ups after day 2'))
            self.assertEqual(200, posted.status_code, posted.text)
            first = next(c for c in posted.json()['completed'] if c['session_id'] == 'day1')
            self.assertEqual(('skipped', 'Doing pull-ups after day 2'), (first['outcome'], first['note']))
            self.assertEqual(200, client.post(f'{base}/day2/skip').status_code, 'the note is optional')
            self.assertEqual(409, client.post(f'{base}/day1/skip').status_code)
            self.assertEqual(404, client.post(f'{base}/nope/skip').status_code)
            self.assertEqual(422, client.post(f'{base}/day3/skip', json=dict(note='x' * 201)).status_code)
            self.assertEqual(409, client.post(f'{base}/day1/complete').status_code)
            self.assertEqual(409, client.delete(f'{base}/day1/complete').status_code)
            undone = client.delete(f'{base}/day1/skip')
            self.assertEqual(200, undone.status_code)
            self.assertEqual(['day2'], [c['session_id'] for c in undone.json()['completed']])
            hevy.assert_not_called()

    # -- the next check-in --------------------------------------------------------------------------

    def checkin(self, start, *, confirmed_at=None):
        with get_db() as conn:
            return session_checkins.closing_candidate(conn, start, str(uuid4()), confirmed_at)

    def test_a_skip_finishes_the_microcycle_for_the_next_checkin(self):
        now = datetime.now(timezone.utc)
        self.train('day1', start=now - timedelta(days=3))
        self.train('day2', start=now - timedelta(days=2))
        mesocycles.skip_day(self.plan_id, 'day3', 'Pull-ups after day 1 of the next microcycle')
        offer = self.checkin(now + timedelta(minutes=1), confirmed_at=now + timedelta(minutes=1))
        self.assertEqual(self.plan_id, offer['plan_id'])

    def test_a_draft_started_before_the_skip_still_gets_the_review(self):
        now = datetime.now(timezone.utc)
        self.train('day1', start=now - timedelta(days=3))
        self.train('day2', start=now - timedelta(days=2))
        started = now - timedelta(hours=1)  # the workout was opened, then the day was skipped, then it was confirmed
        mesocycles.skip_day(self.plan_id, 'day3')
        self.assertIsNotNone(self.checkin(started, confirmed_at=now + timedelta(minutes=5)))
        self.assertIsNone(self.checkin(started, confirmed_at=now - timedelta(minutes=5)),
                          'a confirmation before the skip cannot be a check-in after it')

    def test_a_skip_does_not_relax_the_rule_for_real_workouts(self):
        now = datetime.now(timezone.utc)
        self.train('day1', start=now - timedelta(days=2))
        self.train('day2', start=now + timedelta(hours=2))  # trained later than this check-in began
        mesocycles.skip_day(self.plan_id, 'day3')
        self.assertIsNone(self.checkin(now, confirmed_at=now + timedelta(days=1)))

    def test_a_microcycle_of_only_skips_is_finished(self):
        for session_id in ('day1', 'day2', 'day3'):
            mesocycles.skip_day(self.plan_id, session_id)
        now = datetime.now(timezone.utc)
        self.assertEqual(self.plan_id, self.checkin(now + timedelta(minutes=1), confirmed_at=now + timedelta(minutes=1))['plan_id'])

    def test_the_checkin_response_offers_the_review_after_a_skip(self):
        now = datetime.now(timezone.utc)
        self.train('day1', start=now - timedelta(days=3))
        self.train('day2', start=now - timedelta(days=2))
        mesocycles.skip_day(self.plan_id, 'day3')
        result = session_checkins.record(session_checkins.CheckinInput(
            session_id=uuid4(), workout_start=now - timedelta(minutes=30),
            motivation=dict(level=1, note='', recorded_at=now, timing='before_working_sets')))
        self.assertEqual(self.plan_id, result['closing_review']['plan_id'])


if __name__ == '__main__':
    unittest.main()
