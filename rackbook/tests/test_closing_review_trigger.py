"""Which check-in is offered the look-back review of a finished microcycle. Temporary SQLite only."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from rackbook import mesocycles, session_checkins, workout_saves
from rackbook.database import get_db, init_db

NOW = datetime(2026, 11, 5, 18, tzinfo=timezone.utc)


class ClosingTriggerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        previous = os.environ.get('RACKBOOK_DB_PATH')
        os.environ['RACKBOOK_DB_PATH'] = os.path.join(self.tmp, 'test.db')
        self.addCleanup(lambda: os.environ.__setitem__('RACKBOOK_DB_PATH', previous) if previous else os.environ.pop('RACKBOOK_DB_PATH', None))
        init_db()
        workout_saves.initialize()

    def plan(self, name='Push and pull', days=('day1', 'day2')):
        return mesocycles.save_plan(mesocycles.PlanInput(name=name, weeks=[dict(
            name='Microcycle', sessions=[dict(id=d, name=d.title(), exercises=[]) for d in days])]))['id']

    def complete(self, plan_id, *when):
        """Record completions at fixed times: complete(plan, ('day1', start), ...)."""
        with get_db() as conn:
            for session_id, start in when:
                conn.execute('INSERT INTO mesocycle_completions (mesocycle_id,session_id,hevy_workout_id,workout_start) VALUES (?,?,?,?)',
                             (plan_id, session_id, f'h-{session_id}-{plan_id[:4]}', start.isoformat()))

    def finished(self, name='Push and pull', last_ago=timedelta(days=2)):
        plan_id = self.plan(name)
        self.complete(plan_id, ('day1', NOW - last_ago - timedelta(days=1)), ('day2', NOW - last_ago))
        return plan_id

    def checkin(self, at=NOW, *, timing='before_working_sets', identity=None, plan=None, session='day1'):
        link = dict(mesocycle_id=plan, session_id=session) if plan else None
        return session_checkins.record(session_checkins.CheckinInput(
            session_id=identity or uuid4(), workout_start=at, planned_session=link,
            motivation=dict(level=1, note='', recorded_at=at, timing=timing)))

    def count(self, table):
        with get_db() as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_the_first_checkin_after_the_last_day_is_offered_the_review_even_without_a_plan(self):
        plan_id = self.finished()
        result = self.checkin()
        self.assertEqual(dict(plan_id=plan_id, name='Push and pull', completed_on='2026-11-03'), result['closing_review'])
        self.assertFalse(result['weekly_review_eligible'])

    def test_a_planned_day_one_gets_both_the_closing_and_the_opening_offer(self):
        finished = self.finished()
        upcoming = self.plan('Next microcycle')
        result = self.checkin(plan=upcoming)
        self.assertTrue(result['weekly_review_eligible'])
        self.assertEqual(finished, result['closing_review']['plan_id'])

    def test_an_unfinished_microcycle_is_not_reviewed(self):
        plan_id = self.plan()
        self.complete(plan_id, ('day1', NOW - timedelta(days=2)))
        self.assertIsNone(self.checkin()['closing_review'])

    def test_a_microcycle_without_sessions_or_with_unreadable_data_is_ignored(self):
        with get_db() as conn:
            conn.execute("INSERT INTO mesocycles (id, document) VALUES ('bad', 'not json')")
            conn.execute("INSERT INTO mesocycles (id, document) VALUES ('empty', '{\"weeks\": [{\"sessions\": []}]}')")
        self.assertIsNone(self.checkin()['closing_review'])

    def test_the_last_days_own_checkin_is_never_offered_a_review(self):
        plan_id = self.plan()
        self.complete(plan_id, ('day1', NOW - timedelta(days=2)), ('day2', NOW))
        self.assertIsNone(self.checkin(at=NOW)['closing_review'])
        self.assertIsNone(self.checkin(at=NOW - timedelta(hours=1))['closing_review'])

    def test_the_fourteen_day_window_is_inclusive(self):
        self.finished(last_ago=timedelta(days=14))
        self.assertIsNotNone(self.checkin()['closing_review'])
        self.assertIsNone(self.checkin(at=NOW + timedelta(seconds=1))['closing_review'])

    def test_an_old_microcycle_is_not_resurrected(self):
        self.finished(last_ago=timedelta(days=40))
        self.assertIsNone(self.checkin()['closing_review'])

    def test_only_a_checkin_confirmed_before_working_sets_is_offered_it(self):
        self.finished()
        late = self.checkin(timing='after_working_sets')
        self.assertIsNone(late['closing_review'])
        # That workout began without a pre-training check-in, so the pre-training moment has passed.
        self.assertIsNone(self.checkin(at=NOW + timedelta(hours=1))['closing_review'])

    def test_only_the_first_checkin_after_the_last_day_is_offered_it(self):
        self.finished()
        first = uuid4()
        self.assertIsNotNone(self.checkin(at=NOW, identity=first)['closing_review'])
        # Re-posting the same check-in (a reload or a retry) is stable while it is still the latest.
        self.assertIsNotNone(self.checkin(at=NOW, identity=first)['closing_review'])
        self.assertIsNone(self.checkin(at=NOW + timedelta(days=1))['closing_review'])

    def test_an_earlier_checkin_does_not_use_up_the_offer(self):
        self.finished()
        self.checkin(at=NOW - timedelta(days=5))
        self.assertIsNotNone(self.checkin()['closing_review'])

    def test_the_most_recently_finished_microcycle_wins(self):
        self.finished('Older', last_ago=timedelta(days=6))
        newer = self.finished('Newer', last_ago=timedelta(days=1))
        self.assertEqual(newer, self.checkin()['closing_review']['plan_id'])

    def test_an_archived_microcycle_is_still_reviewed(self):
        plan_id = self.finished()
        with get_db() as conn:
            conn.execute('UPDATE mesocycles SET archived = 1 WHERE id = ?', (plan_id,))
        self.assertEqual(plan_id, self.checkin()['closing_review']['plan_id'])

    def test_manually_marked_days_count_as_finished(self):
        plan_id = self.plan()
        mesocycles.mark_completed(plan_id, 'day1')
        mesocycles.mark_completed(plan_id, 'day2')
        later = datetime.now(timezone.utc) + timedelta(hours=1)
        self.assertEqual(plan_id, self.checkin(at=later)['closing_review']['plan_id'])

    def test_a_different_offset_for_the_same_instant_compares_correctly(self):
        self.finished()
        local = NOW.astimezone(timezone(timedelta(hours=-5)))
        self.assertIsNotNone(self.checkin(at=local)['closing_review'])

    def test_the_offer_writes_nothing_beyond_the_checkin(self):
        self.finished()
        before = {t: self.count(t) for t in ('mesocycles', 'mesocycle_completions', 'plan_proposals')}
        self.checkin()
        self.assertEqual(before, {t: self.count(t) for t in before})
        self.assertEqual(1, self.count('session_checkins'))


if __name__ == '__main__':
    unittest.main()
