"""Week text routes: read-only preview, all-or-none draft save, and callouts kept by the plan model.
Temporary SQLite; Hevy mocked below the routes."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rackbook import main, mesocycles
from rackbook.database import get_db

WEEK = 'Week 3 Day 1\n#Squat (Barbell) 1x3@8 TS, 3x5@7 BO TM90\nWeek 3 Day 2\n#Bench Press (Barbell) 5x4@6 DDP\n#Row myo 15-20@9'


class WeekEntryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ['RACKBOOK_DB_PATH'] = os.path.join(self.tmp, 'test.db')
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.hevy_patch = patch('rackbook.main.hevy_client.HevyClient')
        self.hevy = self.hevy_patch.start()
        self.addCleanup(self.hevy_patch.stop)
        with get_db() as conn:
            conn.executemany('INSERT INTO hevy_exercise_cache (id, title) VALUES (?, ?)',
                             [('squat', 'Squat (Barbell)'), ('bench', 'Bench Press (Barbell)'),
                              ('bench-db', 'Bench Press (Dumbbell)'), ('row', 'Row')])

    def plans(self):
        with get_db() as conn:
            return conn.execute('SELECT COUNT(*) FROM mesocycles').fetchone()[0]

    def test_preview_returns_builder_sessions_and_writes_nothing(self):
        response = self.client.post('/api/week-text/preview', json=dict(text=WEEK))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body['ready'], body)
        sessions = body['weeks'][0]['sessions']
        self.assertEqual([s['name'] for s in sessions], ['Day 1', 'Day 2'])
        self.assertEqual(sessions[0]['exercises'][0]['tm_pct'], 90)
        self.assertEqual(self.plans(), 0)
        self.hevy.assert_not_called()

    def test_preview_lists_problems_and_unmatched_names(self):
        body = self.client.post('/api/week-text/preview',
                                json=dict(text='Week 1 Day 1\n#bench press 5x4\n#Squat (Barbell) 5x6*')).json()
        self.assertFalse(body['ready'])
        self.assertEqual(body['unresolved'], ['bench press'])
        self.assertEqual([e['line'] for e in body['errors']], [3])
        self.assertEqual(body['weeks'][0]['sessions'], [])
        bench = body['weeks'][0]['days'][0]['exercises'][0]
        self.assertEqual({c['id'] for c in bench['choices']}, {'bench', 'bench-db'})

    def test_choice_resolves_name(self):
        body = self.client.post('/api/week-text/preview',
                                json=dict(text='Week 1 Day 1\n#bench press 5x4', choices={'bench press': 'bench'})).json()
        self.assertTrue(body['ready'])
        self.assertEqual(body['weeks'][0]['sessions'][0]['exercises'][0]['title'], 'Bench Press (Barbell)')

    def test_several_weeks_save_as_inactive_drafts_with_program_names(self):
        text = WEEK + '\nWeek 4 Day 1\n#Squat (Barbell) 3x5@8'
        response = self.client.post('/api/week-text/drafts', json=dict(text=text, program_name='BS-Bridge', cycle=2))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([s['name'] for s in response.json()['saved']], ['BS-Bridge2.3', 'BS-Bridge2.4'])
        plans = self.client.get('/api/mesocycles').json()
        self.assertEqual(len(plans), 2)
        self.assertFalse(any(p['active'] for p in plans))
        week3 = next(p for p in plans if p['week'] == 3)
        squat_sets = week3['weeks'][0]['sessions'][0]['exercises'][0]['sets']
        self.assertEqual([(s['ts'], s['backoff']) for s in squat_sets], [(True, False)] + [(False, True)] * 3)
        self.assertEqual(week3['weeks'][0]['sessions'][1]['name'], 'BS-Bridge2.3.2')
        self.hevy.assert_not_called()

    def test_drafts_refuse_text_with_problems_and_save_nothing(self):
        response = self.client.post('/api/week-text/drafts',
                                    json=dict(text=WEEK + '\nWeek 4 Day 1\n#bench press 3x5'))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.plans(), 0)

    def test_request_limits(self):
        too_long = self.client.post('/api/week-text/preview', json=dict(text='x' * 20_001))
        self.assertEqual(too_long.status_code, 422)
        bad_cycle = self.client.post('/api/week-text/drafts', json=dict(text=WEEK, cycle=0))
        self.assertEqual(bad_cycle.status_code, 422)

    def test_callouts_round_trip_through_plan_save(self):
        sessions = self.client.post('/api/week-text/preview', json=dict(text=WEEK)).json()['weeks'][0]['sessions']
        body = dict(name='Week 3', week=3, weeks=[dict(name='Week 3', sessions=sessions)])
        saved = self.client.post('/api/mesocycles', json=body).json()
        bench, row = saved['weeks'][0]['sessions'][1]['exercises']
        self.assertTrue(all(s['ddp'] for s in bench['sets']))
        self.assertEqual((row['sets'][0]['myo'], row['sets'][0]['reps'], row['sets'][0]['reps_max']), (True, 15, 20))


class PlanModelCallouts(unittest.TestCase):
    def test_incoherent_callouts_are_rejected(self):
        for bad in (dict(reps=5, reps_max=8), dict(reps=15, reps_max=12, myo=True), dict(reps=5, drops=2, drops_open=True),
                    dict(reps=5, ts=True, backoff=True), dict(reps=15, myo=True, amrap=True)):
            with self.assertRaises(ValidationError, msg=bad):
                mesocycles.PlannedSet(**bad)
        with self.assertRaises(ValidationError):
            mesocycles.PlannedMovement(exercise_template_id='a', title='A', tm_pct=40, sets=[dict(reps=5)])


class OlderDocuments(WeekEntryCase):
    def test_completed_day_saved_before_callouts_still_allows_editing_other_days(self):
        old_session = dict(id='done', name='Day 1', exercises=[dict(exercise_template_id='squat', title='Squat (Barbell)', notes='',
                           sets=[dict(reps=5, rpe=7, weight_kg=None, type='normal', ts=False)])])
        document = dict(name='Old', program_name='', cycle=1, week=1, notes='',
                        weeks=[dict(name='Week 1', sessions=[old_session, dict(old_session, id='next', name='Day 2')])])
        with get_db() as conn:
            conn.execute('INSERT INTO mesocycles (id, document) VALUES (?, ?)', ('old', json.dumps(document)))
            conn.execute("INSERT INTO mesocycle_completions (mesocycle_id, session_id, hevy_workout_id, workout_start) VALUES ('old', 'done', NULL, '2026-11-01T10:00:00Z')")
        edited = json.loads(json.dumps(document))
        edited['weeks'][0]['sessions'][1]['exercises'][0]['sets'][0]['reps'] = 3
        response = self.client.put('/api/mesocycles/old', json=dict(edited, revision=self.client.get('/api/mesocycles/old').json()['revision']))
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == '__main__':
    unittest.main()
