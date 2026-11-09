"""Weekly coaching call (ADR 0002): when it is due, Accept as next week, Run it back and Undo.

Temporary SQLite only; the Hevy client is mocked and must never be called."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from fastapi.testclient import TestClient
from rackbook import main, mesocycles, plan_proposals, weekly_call
from rackbook.database import get_db


def week(**changes):
    body = dict(name='ignored', program_name='BS', cycle=2, week=3, weeks=[dict(name='Week 1', sessions=[
        dict(id='d1', name='x', exercises=[dict(exercise_template_id='squat', title='Squat (Barbell)',
                                               sets=[dict(reps=3, rpe=8, ts=True, weight_kg=140), dict(reps=5, rpe=7)])]),
        dict(id='d2', name='y', exercises=[dict(exercise_template_id='rdl', title='Romanian Deadlift', sets=[dict(reps=8, rpe=7)])])])])
    body.update(changes)
    return mesocycles.PlanInput.model_validate(body)


def proposal(title='Same again, less RDL'):
    body = dict(version='plan-proposal-v1', title=title, rationale='Day 2 ran above target.', sessions=[
        dict(name='Squat day', exercises=[dict(exercise_template_id='squat', sets=[dict(reps=3, rpe=8, ts=True), dict(reps=5, rpe=7)])]),
        dict(name='Hinge day', exercises=[dict(exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 2)])])
    return 'Here is next week.\n```plan-proposal-v1\n' + json.dumps(body) + '\n```'


class CallCase(unittest.TestCase):
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
                             [('squat', 'Squat (Barbell)'), ('rdl', 'Romanian Deadlift')])
        self.source = mesocycles.save_plan(week())['id']
        mesocycles.activate(self.source)

    def finish(self, plan_id=None):
        plan_id = plan_id or self.source
        mesocycles.mark_completed(plan_id, mesocycles.get_plan(plan_id)['weeks'][0]['sessions'][0]['id'])
        mesocycles.skip_day(plan_id, mesocycles.get_plan(plan_id)['weeks'][0]['sessions'][1]['id'], 'busy')

    def call(self):
        return UUID(weekly_call.call_identity(self.source))

    def plans(self):
        with get_db() as conn:
            return {r['id']: dict(r) for r in conn.execute('SELECT id, active, archived, revision, document FROM mesocycles')}

    def active(self):
        return [pid for pid, row in self.plans().items() if row['active']]

    def count(self, table):
        with get_db() as conn:
            return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


class RolloverTests(CallCase):
    def test_due_only_once_the_week_is_finished_and_nothing_is_planned_next(self):
        self.assertIsNone(weekly_call.rollover())
        self.finish()
        due = weekly_call.rollover()
        self.assertEqual(dict(id=self.source, name='BS2.3', finished=True), {k: due['source'][k] for k in ('id', 'name', 'finished')})
        self.assertEqual(weekly_call.call_identity(self.source), due['call_id'])
        self.assertIsNone(due['next'])

    def test_not_due_while_another_week_has_days_to_train(self):
        self.finish()
        other = mesocycles.save_plan(week(program_name='', name='Hand built'))['id']
        mesocycles.activate(other)
        self.assertIsNone(weekly_call.rollover())
        mesocycles.deactivate(other)
        self.assertEqual(self.source, weekly_call.rollover()['source']['id'])

    def test_not_due_for_old_or_deleted_weeks(self):
        self.finish()
        later = datetime.now(timezone.utc) + weekly_call.CALL_WINDOW + timedelta(days=1)
        self.assertIsNone(weekly_call.rollover(now=later))
        mesocycles.archive(self.source)
        self.assertIsNone(weekly_call.rollover())

    def test_not_due_once_next_week_exists(self):
        self.finish()
        weekly_call.run_it_back(self.source)
        self.assertIsNone(weekly_call.rollover())


class AcceptTests(CallCase):
    def test_accept_creates_the_next_numbered_week_and_makes_it_active(self):
        self.finish()
        turn = uuid4()
        preview = weekly_call.preview(proposal(), self.call(), turn, self.source)
        self.assertTrue(preview['valid'])
        self.assertTrue(preview['call']['matches'])
        self.assertEqual('BS2.4', preview['call']['next_name'])
        self.assertEqual(0, self.count('microcycle_successors'))
        before = self.plans()[self.source]
        result = weekly_call.accept_next_week(proposal(), self.call(), turn, self.source)
        self.assertFalse(result['already_applied'])
        next_week = result['call']['next']
        self.assertEqual(('BS2.4', 'coach', True), (next_week['name'], next_week['origin'], next_week['can_undo']))
        self.assertEqual([next_week['plan_id']], self.active())
        document = json.loads(self.plans()[next_week['plan_id']]['document'])
        self.assertEqual((2, 4), (document['cycle'], document['week']))
        self.assertEqual(['BS2.4.1', 'BS2.4.2'], [s['name'] for s in document['weeks'][0]['sessions']])
        self.assertTrue(all(s['weight_kg'] is None for d in document['weeks'][0]['sessions'] for e in d['exercises'] for s in e['sets']))
        self.assertIn('Weekly coaching call: Day 2 ran above target.', document['notes'])
        self.assertEqual(before, self.plans()[self.source])
        with get_db() as conn:
            saved = conn.execute('SELECT plan_id FROM plan_proposals WHERE id = ?',
                                 (plan_proposals.proposal_id(self.call(), turn),)).fetchone()
        self.assertEqual(next_week['plan_id'], saved['plan_id'])
        self.assertTrue(weekly_call.accept_next_week(proposal(), self.call(), turn, self.source)['already_applied'])
        self.assertEqual(1, self.count('microcycle_successors'))
        again = weekly_call.preview(proposal(), self.call(), turn, self.source)['call']
        self.assertTrue(again['this_turn'])
        self.assertFalse(weekly_call.preview(proposal(), self.call(), uuid4(), self.source)['call']['this_turn'])

    def test_a_plan_without_a_program_name_keeps_the_proposal_title(self):
        self.source = mesocycles.save_plan(week(program_name='', name='Upper lower'))['id']
        mesocycles.activate(self.source)
        self.finish()
        result = weekly_call.accept_next_week(proposal('Upper lower, week 2'), self.call(), uuid4(), self.source)
        self.assertEqual('Upper lower, week 2', result['call']['next']['name'])

    def test_only_this_weeks_call_can_set_up_its_next_week(self):
        self.finish()
        with self.assertRaises(weekly_call.CallError) as wrong:
            weekly_call.accept_next_week(proposal(), uuid4(), uuid4(), self.source)
        self.assertEqual(422, wrong.exception.status)
        self.assertFalse(weekly_call.preview(proposal(), uuid4(), uuid4(), self.source)['call']['matches'])
        self.assertEqual(0, self.count('microcycle_successors'))

    def test_refusals_change_nothing(self):
        with self.assertRaises(weekly_call.CallError) as unfinished:
            weekly_call.accept_next_week(proposal(), self.call(), uuid4(), self.source)
        self.assertIn('still has days', str(unfinished.exception))
        self.finish()
        with self.assertRaises(weekly_call.CallError) as invalid:
            weekly_call.accept_next_week(proposal().replace('squat', 'ghost'), self.call(), uuid4(), self.source)
        self.assertEqual(422, invalid.exception.status)
        with self.assertRaises(weekly_call.CallError):
            weekly_call.accept_next_week('Keep it the same.', self.call(), uuid4(), self.source)
        draft_turn = uuid4()
        plan_proposals.save_draft(proposal(), self.call(), draft_turn)
        with self.assertRaises(weekly_call.CallError) as drafted:
            weekly_call.accept_next_week(proposal(), self.call(), draft_turn, self.source)
        self.assertIn('already saved as a draft', str(drafted.exception))
        self.assertEqual(0, self.count('microcycle_successors'))
        self.assertEqual([], self.active())
        weekly_call.accept_next_week(proposal(), self.call(), uuid4(), self.source)
        with self.assertRaises(weekly_call.CallError) as twice:
            weekly_call.accept_next_week(proposal(), self.call(), uuid4(), self.source)
        self.assertIn('already set up', str(twice.exception))
        with self.assertRaises(weekly_call.CallError):
            weekly_call.run_it_back(self.source)


class RunItBackTests(CallCase):
    def test_run_it_back_repeats_the_week_with_fresh_days_and_the_athletes_own_weights(self):
        self.finish()
        result = weekly_call.run_it_back(self.source)
        next_week = result['call']['next']
        self.assertEqual(('BS2.4', 'repeat', None), (next_week['name'], next_week['origin'], next_week['proposal_id']))
        self.assertEqual([next_week['plan_id']], self.active())
        source = json.loads(self.plans()[self.source]['document'])['weeks'][0]['sessions']
        copy = json.loads(self.plans()[next_week['plan_id']]['document'])['weeks'][0]['sessions']
        self.assertEqual([s['exercises'] for s in source], [s['exercises'] for s in copy])
        self.assertEqual(140, copy[0]['exercises'][0]['sets'][0]['weight_kg'])
        self.assertFalse({s['id'] for s in source} & {s['id'] for s in copy})
        self.assertEqual([], mesocycles.get_plan(next_week['plan_id'])['completed'])
        self.assertTrue(weekly_call.run_it_back(self.source)['already_applied'])
        self.assertEqual(0, self.count('plan_proposals'))


class UndoTests(CallCase):
    def test_undo_removes_the_untouched_week_and_restores_what_was_active(self):
        self.finish()
        other = mesocycles.save_plan(week(program_name='', name='Side plan'))['id']
        mesocycles.activate(other)
        mesocycles.deactivate(other)
        mesocycles.activate(other)
        turn = uuid4()
        # A hand-built plan with days left blocks the automatic call, but a call held from AI Coach can still accept.
        result = weekly_call.accept_next_week(proposal(), self.call(), turn, self.source)
        created = result['call']['next']['plan_id']
        self.assertEqual([created], self.active())
        undone = weekly_call.undo(self.source)
        self.assertIsNone(undone['call']['next'])
        self.assertEqual([other], self.active())
        self.assertEqual(1, self.plans()[created]['archived'])
        self.assertEqual(0, self.count('plan_proposals'))
        again = weekly_call.accept_next_week(proposal(), self.call(), turn, self.source)
        self.assertFalse(again['already_applied'])

    def test_undo_is_refused_once_the_new_week_is_edited(self):
        self.finish()
        created = weekly_call.run_it_back(self.source)['call']['next']['plan_id']
        current = mesocycles.get_plan(created)
        mesocycles.save_plan(mesocycles.PlanInput.model_validate(dict(current, notes='mine')), created)
        status = weekly_call.status(self.source)['next']
        self.assertFalse(status['can_undo'])
        self.assertIn('edited in the builder', status['undo_problem'])
        with self.assertRaises(weekly_call.CallError):
            weekly_call.undo(self.source)
        self.assertEqual('mine', mesocycles.get_plan(created)['notes'])

    def test_undo_is_refused_once_the_new_week_is_trained(self):
        self.finish()
        created = weekly_call.run_it_back(self.source)['call']['next']['plan_id']
        mesocycles.mark_completed(created, mesocycles.get_plan(created)['weeks'][0]['sessions'][0]['id'])
        with self.assertRaises(weekly_call.CallError) as trained:
            weekly_call.undo(self.source)
        self.assertIn('trained or skipped', str(trained.exception))
        with self.assertRaises(weekly_call.CallError):
            weekly_call.undo(mesocycles.save_plan(week())['id'])


class RouteTests(CallCase):
    def test_routes_never_contact_hevy(self):
        self.assertIsNone(self.client.get('/api/weekly-call').json())
        self.finish()
        due = self.client.get('/api/weekly-call').json()
        self.assertEqual(self.source, due['source']['id'])
        body = dict(text=proposal(), conversation_id=due['call_id'], turn_id=str(uuid4()))
        self.assertTrue(self.client.post(f'/api/weekly-call/{self.source}/preview', json=body).json()['call']['matches'])
        accepted = self.client.post(f'/api/weekly-call/{self.source}/next-week', json=body)
        self.assertEqual(200, accepted.status_code, accepted.text)
        self.assertEqual(409, self.client.post(f'/api/weekly-call/{self.source}/run-it-back').status_code)
        self.assertEqual(200, self.client.post(f'/api/weekly-call/{self.source}/undo').status_code)
        self.assertEqual(200, self.client.post(f'/api/weekly-call/{self.source}/run-it-back').status_code)
        self.assertEqual('repeat', self.client.get(f'/api/weekly-call/{self.source}').json()['next']['origin'])
        self.assertEqual(404, self.client.get('/api/weekly-call/missing').status_code)
        wrong = dict(body, conversation_id=str(uuid4()))
        self.assertEqual(422, self.client.post(f'/api/weekly-call/{self.source}/next-week', json=wrong).status_code)
        self.hevy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
