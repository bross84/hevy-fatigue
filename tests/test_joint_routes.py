"""Joint baseline routes, decisions, evidence and the joint coaching call (#154).

Temporary SQLite only; no AI provider is called (calls are prepared, never sent)."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
import database
from database import Base, DailyReadiness, ExerciseMapping, WorkoutLog, WorkoutSession
import main
from rackbook import database as logger

DAY = date(2026, 11, 26)


class JointRouteTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.temp.name) / 'logging.db'))
        self.env.start()
        logger.init_db()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()

        def dependency():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[main.get_db] = dependency
        self.persist = patch.object(main, 'SessionLocal', self.sessions)
        self.persist.start()
        self.today = patch.object(main, 'local_today', return_value=DAY)
        self.today.start()
        self.client = TestClient(main.app)
        # 28 days at a usual of 1, then three raised lower-joint check-ins out of the last four.
        ratings = [1] * 28 + [2, 1, 2, 2]
        for i, rating in enumerate(ratings):
            day = DAY - timedelta(days=len(ratings) - 1 - i)
            self.db.add(DailyReadiness(date=day, joint_lower=rating, joint_upper=0, tiredness=1, perceived_recovery=1))
        self.db.add(ExerciseMapping(exercise_title='Squat (Barbell)', pct_quad_dom=1.0))
        self.db.add(ExerciseMapping(exercise_title='Bench Press (Barbell)', pct_upper_push=1.0))
        for offset in (2, 4, 6):
            day = DAY - timedelta(days=offset)
            key = f'hevy-{offset}'
            self.db.add(WorkoutSession(hevy_workout_id=key, workout_date=day, workout_title='Strength'))
            self.db.add(WorkoutLog(workout_id=key, date=day, exercise_id='sq', exercise_title='Squat (Barbell)',
                                   set_number=1, weight_lbs=225, reps=5, rpe=7))
        self.db.commit()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.persist.stop()
        self.today.stop()
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def status(self):
        response = self.client.get('/api/joint/status')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def decide(self, outcome, until=None, regions=('lower',), ident=None, expect=200):
        body = dict(id=str(ident or uuid4()), regions=list(regions), outcome=outcome, until=until)
        response = self.client.post('/api/joint/decisions', json=body)
        self.assertEqual(response.status_code, expect, response.text)
        return response.json()

    def test_status_reports_the_call_hold_and_held_lifts(self):
        status = self.status()
        lower = status['regions']['lower']
        self.assertEqual((lower['usual'], lower['level'], lower['notice_count'], lower['hold']), (1, 'notice', 3, True))
        self.assertEqual(status['regions']['upper']['level'], 'none')
        self.assertEqual((status['call']['regions'], status['call']['kind']), (['lower'], 'notice'))
        self.assertEqual(status['held_patterns'], ['hip', 'knee'])
        self.assertEqual(status['held_exercises'], ['Squat (Barbell)'])

    def test_carry_on_lifts_the_hold_and_is_idempotent(self):
        ident = uuid4()
        until = str(DAY + timedelta(days=7))
        status = self.decide('carry_on', until, ident=ident)
        self.assertIsNone(status['call'])
        self.assertEqual(status['regions']['lower']['carry_on_until'], until)
        self.assertEqual(status['held_exercises'], [])
        self.decide('carry_on', until, ident=ident)
        self.assertEqual(self.db.query(database.JointCallDecision).count(), 1)
        self.decide('not_now', ident=ident, expect=409)

    def test_new_normal_records_the_accepted_level_and_clears_the_call(self):
        status = self.decide('new_normal')
        self.assertIsNone(status['call'])
        row = self.db.query(database.JointCallDecision).one()
        self.assertEqual((row.region, row.outcome, row.level, row.decided_on), ('lower', 'new_normal', 2, DAY))

    def test_not_now_keeps_the_banner_and_the_hold(self):
        status = self.decide('not_now')
        self.assertEqual(status['call']['regions'], ['lower'])
        self.assertEqual(status['held_exercises'], ['Squat (Barbell)'])

    def test_decisions_need_a_raised_region_and_a_future_carry_on_date(self):
        self.decide('change', regions=('upper',), expect=409)
        self.decide('carry_on', str(DAY), expect=409)
        response = self.client.post('/api/joint/decisions', json=dict(id=str(uuid4()), regions=['lower'], outcome='carry_on'))
        self.assertEqual(response.status_code, 422)

    def test_evidence_merges_imported_and_logger_lifts(self):
        with closing(logger.get_db()) as db, db:
            db.execute('''INSERT INTO logged_sets(hevy_workout_id,workout_start,exercise_template_id,exercise_title,
                set_number,set_type,weight_kg,reps,rpe) VALUES (?,?,?,?,?,?,?,?,?)''',
                ('local-1', datetime(2026, 11, 21, 15, tzinfo=timezone.utc).isoformat(), 'sq', 'Squat (Barbell)', 1, 'normal', 100, 5, 7))
        response = self.client.get('/api/joint/evidence')
        self.assertEqual(response.status_code, 200, response.text)
        lines = response.json()['regions']['lower']['lines']
        squat = next(x for x in lines if x['name'] == 'Squat (Barbell)')
        self.assertEqual((squat['after_count'], squat['status']), (4, 'early'))
        self.assertEqual([x['kind'] for x in lines], ['lift'])
        self.assertEqual(response.json()['regions']['upper']['lines'], [])

    def test_joint_call_prepares_a_frozen_conversation_with_joint_context(self):
        response = self.client.post('/api/ai/joint-calls')
        self.assertEqual(response.status_code, 200, response.text)
        view = response.json()
        context = view['evidence']['joint_context']
        self.assertEqual(view['id'], self.status()['call']['id'])
        self.assertEqual((context['regions'], context['kind']), (['lower'], 'notice'))
        self.assertIn('movement_evidence', context)
        self.assertIn('lower joint rating', view['first_message'])
        self.assertEqual(view['turns'], [])
        again = self.client.post('/api/ai/joint-calls').json()
        self.assertEqual(again['id'], view['id'])
        labels = [r['label'] for r in self.client.get('/api/ai/conversations').json()]
        self.assertIn('Joint coaching call · lower joint', labels)

    def test_no_call_due_is_refused(self):
        self.decide('carry_on', str(DAY + timedelta(days=7)))
        self.assertEqual(self.client.post('/api/ai/joint-calls').status_code, 422)

    def test_daily_context_carries_usual_levels(self):
        import daily_coaching
        summary = daily_coaching.joint_summary(self.db, DAY)
        self.assertEqual((summary['call_due'], summary['regions']['lower']['usual'],
                          summary['regions']['lower']['today_above_usual']), (True, 1, True))

    def test_coach_brief_keeps_a_steady_usual_rating_as_background(self):
        self.assertIn('A steady rating at usual\nis background', coaching.BRIEF)
        self.assertIn('never propose load\nincreases for them', coaching.BRIEF)
