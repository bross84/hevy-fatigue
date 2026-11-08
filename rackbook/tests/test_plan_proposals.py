"""AI plan proposals: validation, read-only preview, explicit atomic draft save. Temporary SQLite; Hevy mocked."""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from fastapi.testclient import TestClient
from rackbook import main, plan_proposals
from rackbook.database import get_db


def proposal(**changes):
    body = dict(version='plan-proposal-v1', title='Deload week', rationale='Recent sessions ran above target.',
                sessions=[dict(name='Squat day', exercises=[
                    dict(exercise_template_id='squat', notes='Keep it smooth.',
                         sets=[dict(reps=3, rpe=7, ts=True), dict(reps=5, rpe=7), dict(reps=5, rpe=7)]),
                    dict(exercise_template_id='bench', sets=[dict(reps=8, rpe=8)])])])
    body.update(changes)
    return body


def reply(body=None, before='Here is a week to discuss.\n', after='\nTell me what to change.'):
    return before + '```plan-proposal-v1\n' + json.dumps(proposal() if body is None else body) + '\n```' + after


class ProposalCase(unittest.TestCase):
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
                             [('squat', 'Squat (Barbell)'), ('bench', 'Bench Press (Barbell)'), ('row', 'Row')])

    def count(self, table):
        with get_db() as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def ids(self):
        return uuid4(), uuid4()

    def issues(self, text):
        result = plan_proposals.preview(text)
        self.assertTrue(result['found'])
        self.assertFalse(result['valid'], result)
        return ' '.join(result['issues'])


class PreviewTests(ProposalCase):
    def test_valid_proposal_is_described_with_local_titles_and_no_weights(self):
        result = plan_proposals.preview(reply())
        self.assertTrue(result['valid'], result)
        movements = result['sessions'][0]['exercises']
        self.assertEqual(['Squat (Barbell)', 'Bench Press (Barbell)'], [m['title'] for m in movements])
        self.assertEqual('1×3 @7 TS, 2×5 @7', movements[0]['summary'])
        self.assertEqual('Keep it smooth.', movements[0]['notes'])
        self.assertNotIn('weight_kg', json.dumps(result))
        self.assertEqual(dict(active_plan=None, added=[], removed=[], changed=[]), result['diff'])

    def test_no_block_or_unfinished_block_is_not_a_proposal(self):
        self.assertEqual(dict(found=False), plan_proposals.preview('Just a discussion.'))
        self.assertEqual(dict(found=False), plan_proposals.preview('```plan-proposal-v1\n{"version"'))
        self.assertEqual(dict(found=False), plan_proposals.preview('```json\n' + json.dumps(proposal()) + '\n```'))
        self.assertEqual(dict(found=False), plan_proposals.preview('x' * (plan_proposals.MAX_REPLY_CHARS + 1)))

    def test_invalid_proposals_are_reported_not_repaired(self):
        self.assertIn('Only one proposal', self.issues(reply() + '\n' + reply()))
        self.assertIn('not valid JSON', self.issues('```plan-proposal-v1\n{nope}\n```'))
        self.assertIn('too large', self.issues('```plan-proposal-v1\n' + ' ' * (plan_proposals.MAX_BLOCK_CHARS + 1) + '\n```'))
        bad = {
            'weights': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=5, weight_kg=100)])])]),
            'extra key': dict(proposal(), apply=True),
            'wrong version': proposal(version='plan-proposal-v2'),
            'no sessions': proposal(sessions=[]),
            'long rationale': proposal(rationale='x' * 501),
            'rpe step': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=5, rpe=7.3)])])]),
            'rpe range': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=5, rpe=3)])])]),
            'bool reps': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=True)])])]),
            'zero reps': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=0)])])]),
            'empty movement': proposal(sessions=[dict(name='A', exercises=[])]),
            'too many sessions': proposal(sessions=[dict(name=str(i), exercises=[dict(exercise_template_id='squat', sets=[dict(reps=5)])]) for i in range(15)]),
            'two ts': proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=1, ts=True), dict(reps=1, ts=True)])])]),
        }
        for name, body in bad.items():
            with self.subTest(name):
                self.assertTrue(self.issues(reply(body)))

    def test_unknown_movement_ids_are_rejected_but_history_and_plans_count_as_known(self):
        unknown = proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='made-up', sets=[dict(reps=5)])])])
        self.assertIn('made-up', self.issues(reply(unknown)))
        with get_db() as conn:
            conn.execute("INSERT INTO logged_sets (workout_start, exercise_template_id, exercise_title, set_number, set_type) "
                         "VALUES ('2026-11-01T10:00:00Z', 'logged', 'Logged Lift', 1, 'normal')")
        body = proposal(sessions=[dict(name='A', exercises=[dict(exercise_template_id='logged', sets=[dict(reps=5)])])])
        self.assertEqual('Logged Lift', plan_proposals.preview(reply(body))['sessions'][0]['exercises'][0]['title'])

    def test_preview_compares_with_the_active_plan_and_writes_nothing(self):
        plan = self.client.post('/api/mesocycles', json=dict(name='Current', weeks=[dict(name='Week 1', sessions=[
            dict(id='d1', name='Day 1', exercises=[
                dict(exercise_template_id='squat', title='Squat (Barbell)', sets=[dict(reps=5, rpe=7)] * 3),
                dict(exercise_template_id='row', title='Row', sets=[dict(reps=10, rpe=8)])])])])).json()
        self.assertEqual(200, self.client.post(f"/api/mesocycles/{plan['id']}/activate").status_code)
        before = (self.count('mesocycles'), self.count('plan_proposals'))
        diff = plan_proposals.preview(reply())['diff']
        self.assertEqual('Current', diff['active_plan']['name'])
        self.assertEqual(['Bench Press (Barbell)'], diff['added'])
        self.assertEqual(['Row'], diff['removed'])
        self.assertEqual([dict(title='Squat (Barbell)', was='3×5 @7', now='1×3 @7 TS, 2×5 @7')], diff['changed'])
        self.assertEqual(before, (self.count('mesocycles'), self.count('plan_proposals')))


class SaveTests(ProposalCase):
    def test_save_creates_one_inactive_plan_with_provenance_and_is_idempotent(self):
        conversation, turn = self.ids()
        first = plan_proposals.save_draft(reply(), conversation, turn)
        again = plan_proposals.save_draft(reply(), conversation, turn)
        self.assertFalse(first['already_saved'])
        self.assertTrue(again['already_saved'])
        self.assertEqual(first['plan']['id'], again['plan']['id'])
        plan = first['plan']
        self.assertFalse(plan['active'])
        self.assertFalse(plan['archived'])
        self.assertEqual('Deload week', plan['name'])
        self.assertIn('not applied', plan['notes'])
        sets = [s for sess in plan['weeks'][0]['sessions'] for ex in sess['exercises'] for s in ex['sets']]
        self.assertTrue(all(s['weight_kg'] is None for s in sets))
        self.assertEqual(1, self.count('mesocycles'))
        with get_db() as conn:
            row = conn.execute('SELECT * FROM plan_proposals').fetchone()
        self.assertEqual((str(conversation), str(turn), plan['id']), (row['conversation_id'], row['turn_id'], row['plan_id']))
        self.assertEqual(first['proposal_id'], row['id'])
        self.assertEqual('Deload week', json.loads(row['proposed'])['title'])

    def test_another_turn_makes_another_draft_and_existing_plans_are_untouched(self):
        existing = self.client.post('/api/mesocycles', json=dict(name='Current', weeks=[dict(name='Week 1', sessions=[
            dict(id='d1', name='Day 1', exercises=[dict(exercise_template_id='squat', title='Squat (Barbell)', sets=[dict(reps=5)])])])])).json()
        self.client.post(f"/api/mesocycles/{existing['id']}/activate")
        before = self.client.get(f"/api/mesocycles/{existing['id']}").json()
        conversation = uuid4()
        a = plan_proposals.save_draft(reply(), conversation, uuid4())['plan']
        b = plan_proposals.save_draft(reply(), conversation, uuid4())['plan']
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(3, self.count('mesocycles'))
        self.assertEqual(before, self.client.get(f"/api/mesocycles/{existing['id']}").json())
        self.assertTrue(self.client.get(f"/api/mesocycles/{existing['id']}").json()['active'])
        self.assertEqual([existing['id']], [p['id'] for p in self.client.get('/api/mesocycles').json() if p['active']])

    def test_invalid_or_missing_proposals_save_nothing(self):
        for text in ('no block', reply(proposal(version='nope')), reply(dict(proposal(), apply=True))):
            with self.assertRaises(plan_proposals.ProposalError):
                plan_proposals.save_draft(text, *self.ids())
        self.assertEqual((0, 0), (self.count('mesocycles'), self.count('plan_proposals')))

    def test_plan_and_provenance_are_atomic(self):
        conversation, turn = self.ids()
        with get_db() as conn:  # a conflicting provenance row makes the second insert fail
            conn.execute("INSERT INTO mesocycles (id, document) VALUES ('seed', '{\"name\":\"s\",\"weeks\":[]}')")
            conn.execute('INSERT INTO plan_proposals (id, conversation_id, turn_id, plan_id, proposed, saved_at) VALUES (?, ?, ?, ?, ?, ?)',
                         ('other-id', str(conversation), str(turn), 'seed', '{}', 'now'))
        with self.assertRaises(sqlite3.IntegrityError):
            plan_proposals.save_draft(reply(), conversation, turn)
        self.assertEqual(1, self.count('mesocycles'))
        self.assertEqual(1, self.count('plan_proposals'))


class RouteTests(ProposalCase):
    def body(self, text=None, conversation=None, turn=None):
        return dict(text=reply() if text is None else text, conversation_id=str(conversation or uuid4()),
                    turn_id=str(turn or uuid4()))

    def test_preview_route_is_read_only_and_save_route_is_explicit(self):
        preview = self.client.post('/api/plan-proposals/preview', json=self.body())
        self.assertEqual(200, preview.status_code)
        self.assertTrue(preview.json()['valid'])
        self.assertEqual(0, self.count('mesocycles'))
        request = self.body()
        saved = self.client.post('/api/plan-proposals/save', json=request)
        self.assertEqual(200, saved.status_code, saved.text)
        self.assertFalse(saved.json()['plan']['active'])
        self.assertTrue(self.client.post('/api/plan-proposals/save', json=request).json()['already_saved'])
        self.assertEqual(1, self.count('mesocycles'))
        self.hevy.assert_not_called()

    def test_routes_reject_bad_input_with_explicit_errors(self):
        self.assertEqual(422, self.client.post('/api/plan-proposals/preview', json=dict(self.body(), turn_id='nope')).status_code)
        self.assertEqual(422, self.client.post('/api/plan-proposals/save', json=dict(self.body(), text='')).status_code)
        self.assertEqual(422, self.client.post('/api/plan-proposals/save', json=dict(self.body(), text='x' * 80_001)).status_code)
        missing = self.client.post('/api/plan-proposals/save', json=self.body('No proposal here.'))
        self.assertEqual(422, missing.status_code)
        self.assertIn('No plan proposal', missing.json()['detail'])
        invalid = self.client.post('/api/plan-proposals/save', json=self.body(reply(proposal(version='x'))))
        self.assertEqual(422, invalid.status_code)
        self.assertEqual(0, self.count('mesocycles'))

    def test_inputs_are_not_mutated(self):
        body = proposal()
        before = deepcopy(body)
        plan_proposals.preview(reply(body))
        self.assertEqual(before, body)
