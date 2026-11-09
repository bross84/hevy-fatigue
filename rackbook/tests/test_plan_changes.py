"""AI coach plan changes (ADR 0002): read-only preview, Accept applies atomically, Undo restores.

Temporary SQLite only; the Hevy client is mocked and must never be called."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault('RACKBOOK_DB_PATH', os.path.join(tempfile.mkdtemp(), 'import.db'))
from fastapi.testclient import TestClient
from rackbook import main, mesocycles, plan_changes
from rackbook.database import get_db


def week(**changes):
    body = dict(name='Block 1', weeks=[dict(name='Week 1', sessions=[
        dict(id='d1', name='Day 1', exercises=[
            dict(exercise_template_id='squat', title='Squat (Barbell)', notes='Brace',
                 sets=[dict(reps=3, rpe=8, ts=True, weight_kg=140), dict(reps=5, rpe=7), dict(reps=5, rpe=7)])]),
        dict(id='d2', name='Day 2', exercises=[
            dict(exercise_template_id='rdl', title='Romanian Deadlift', sets=[dict(reps=8, rpe=7)] * 3),
            dict(exercise_template_id='row', title='Row', notes='Pause', sets=[dict(reps=10, rpe=8, weight_kg=60)] * 3)]),
        dict(id='d3', name='Day 3', exercises=[
            dict(exercise_template_id='bench', title='Bench Press (Barbell)', sets=[dict(reps=5, rpe=8, weight_kg=100)] * 3)])])])
    body.update(changes)
    return mesocycles.PlanInput.model_validate(body)


class ChangeCase(unittest.TestCase):
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
            conn.executemany('INSERT INTO hevy_exercise_cache (id, title) VALUES (?, ?)', [
                ('squat', 'Squat (Barbell)'), ('rdl', 'Romanian Deadlift'), ('row', 'Row'),
                ('bench', 'Bench Press (Barbell)'), ('csr', 'Chest Supported Row'), ('face', 'Face Pull')])
        self.plan = mesocycles.save_plan(week())

    def body(self, changes, **extra):
        body = dict(version='plan-change-v1', plan_id=self.plan['id'], revision=self.plan['revision'],
                    title='Ease day 2', rationale='Day 2 RPE ran above target twice.', changes=changes)
        body.update(extra)
        return body

    def reply(self, changes=None, raw=None, **extra):
        payload = raw if raw is not None else json.dumps(self.body(changes or [
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 2)], **extra))
        return 'Here is what I would change.\n```plan-change-v1\n' + payload + '\n```\nThoughts?'

    def ids(self):
        return uuid4(), uuid4()

    def stored(self):
        with get_db() as conn:
            row = conn.execute('SELECT document, revision, active FROM mesocycles WHERE id = ?', (self.plan['id'],)).fetchone()
            return json.loads(row['document']), row['revision'], row['active']

    def changes_count(self):
        with get_db() as conn:
            return conn.execute('SELECT COUNT(*) FROM plan_changes').fetchone()[0]

    def issues(self, text):
        result = plan_changes.preview(text, *self.ids())
        self.assertTrue(result['found'])
        self.assertFalse(result['valid'], result)
        return ' '.join(result['issues'])

    def finish(self, session_id, outcome='completed'):
        if outcome == 'skipped':
            mesocycles.skip_day(self.plan['id'], session_id, 'travel')
        else:
            mesocycles.mark_completed(self.plan['id'], session_id)


class PreviewTests(ChangeCase):
    def test_preview_describes_each_day_and_writes_nothing(self):
        before = self.stored()
        result = plan_changes.preview(self.reply([
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 2),
            dict(op='replace', day=2, exercise_template_id='row', new_exercise_template_id='csr'),
            dict(op='add', day=3, exercise_template_id='face', sets=[dict(reps=15, rpe=7)] * 2, notes='Light'),
            dict(op='remove', day=1, exercise_template_id='squat')]), *self.ids())
        self.assertTrue(result['valid'], result)
        self.assertEqual('pending', result['status'])
        self.assertEqual(dict(id=self.plan['id'], name='Block 1', active=False, revision=1), result['plan'])
        self.assertEqual([
            dict(day=1, name='Day 1', changes=['Remove Squat (Barbell) (was 1×3 @8 TS, 2×5 @7)']),
            dict(day=2, name='Day 2', changes=['Romanian Deadlift: 3×8 @7 → 2×8 @7',
                 'Swap Row → Chest Supported Row: 3×10 @8 (fixed weights cleared; loads come from automatic planning)']),
            dict(day=3, name='Day 3', changes=['Add Face Pull: 2×15 @7'])], result['days'])
        self.assertEqual(before, self.stored())
        self.assertEqual(0, self.changes_count())

    def test_replies_without_a_block_are_not_changes(self):
        self.assertEqual(dict(found=False), plan_changes.preview('Hold the plan as it is this week.', *self.ids()))
        self.assertEqual(dict(found=False), plan_changes.preview('```plan-proposal-v1\n{}\n```', *self.ids()))

    def test_malformed_blocks_are_reported(self):
        self.assertIn('not valid JSON', self.issues(self.reply(raw='{nope')))
        self.assertIn('Only one plan change', self.issues(self.reply() + self.reply()))
        self.assertIn('changes', self.issues(self.reply(raw=json.dumps(self.body([])))))
        self.assertIn('weight_kg', self.issues(self.reply([
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=8, rpe=7, weight_kg=150)])])))
        self.assertIn('half-point', self.issues(self.reply([
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=8, rpe=7.3)])])))
        self.assertIn('op', self.issues(self.reply([dict(op='activate', day=1, exercise_template_id='squat')])))

    def test_finished_days_are_never_changed(self):
        self.finish('d1')
        self.finish('d2', 'skipped')
        self.plan = mesocycles.get_plan(self.plan['id'])
        text = self.issues(self.reply([
            dict(op='remove', day=1, exercise_template_id='squat'),
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=5)])]))
        self.assertIn('Day 1 (Day 1) is already trained', text)
        self.assertIn('Day 2 (Day 2) is already skipped', text)

    def test_targets_must_exist_and_be_unambiguous(self):
        self.assertIn('Day 9 does not exist', self.issues(self.reply([dict(op='remove', day=9, exercise_template_id='squat')])))
        self.assertIn('does not include movement bench', self.issues(self.reply([dict(op='remove', day=1, exercise_template_id='bench')])))
        self.assertIn('unknown movement id ghost', self.issues(self.reply([
            dict(op='add', day=1, exercise_template_id='ghost', sets=[dict(reps=5)])])))
        self.assertIn('unknown movement id ghost', self.issues(self.reply([
            dict(op='replace', day=2, exercise_template_id='row', new_exercise_template_id='ghost')])))
        self.assertIn('already has Romanian Deadlift', self.issues(self.reply([
            dict(op='add', day=2, exercise_template_id='rdl', sets=[dict(reps=5)])])))
        self.assertIn('already has Romanian Deadlift', self.issues(self.reply([
            dict(op='replace', day=2, exercise_template_id='row', new_exercise_template_id='rdl')])))
        doubled = week()
        doubled.weeks[0].sessions[2].exercises.append(doubled.weeks[0].sessions[2].exercises[0].model_copy())
        self.plan = mesocycles.save_plan(doubled.model_copy(update=dict(revision=1)), self.plan['id'])
        self.assertIn('more than once', self.issues(self.reply([dict(op='remove', day=3, exercise_template_id='bench')])))

    def test_the_whole_plan_must_stay_valid(self):
        self.assertIn('Only one TS', self.issues(self.reply([
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=3, ts=True), dict(reps=3, ts=True)])])))

    def test_a_plan_edited_since_the_reply_is_stale(self):
        result = plan_changes.preview(self.reply(revision=self.plan['revision'] + 1), *self.ids())
        self.assertFalse(result['valid'])
        self.assertTrue(result['stale'])
        self.assertIn('edited since the coach wrote this change', result['issues'][0])

    def test_missing_and_deleted_plans_are_refused(self):
        self.assertIn('no longer exists', self.issues(self.reply(plan_id='nope')))
        mesocycles.archive(self.plan['id'])
        self.assertIn('deleted', self.issues(self.reply()))


class AcceptTests(ChangeCase):
    def test_accept_applies_once_keeps_finished_days_and_records_provenance(self):
        self.finish('d1')
        self.plan = mesocycles.get_plan(self.plan['id'])
        original = self.stored()[0]
        conversation, turn = self.ids()
        text = self.reply([
            dict(op='set_sets', day=2, exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 2),
            dict(op='replace', day=2, exercise_template_id='row', new_exercise_template_id='csr', notes='Chest on pad')])
        result = plan_changes.accept(text, conversation, turn)
        self.assertFalse(result['already_applied'])
        self.assertEqual('applied', result['change']['status'])
        self.assertTrue(result['change']['can_undo'])
        document, revision, active = self.stored()
        self.assertEqual(2, revision)
        self.assertEqual(0, active)
        self.assertEqual(original['weeks'][0]['sessions'][0], document['weeks'][0]['sessions'][0])
        self.assertEqual(original['weeks'][0]['sessions'][2], document['weeks'][0]['sessions'][2])
        day2 = document['weeks'][0]['sessions'][1]['exercises']
        self.assertEqual(2, len(day2[0]['sets']))
        self.assertEqual(dict(exercise_template_id='csr', title='Chest Supported Row', notes='Chest on pad'),
                         {k: day2[1][k] for k in ('exercise_template_id', 'title', 'notes')})
        self.assertTrue(all(s['weight_kg'] is None for s in day2[1]['sets']))
        view = result['plan']
        self.assertEqual(dict(id=result['change']['change_id'], conversation_id=str(conversation), title='Ease day 2'),
                         {k: view['coach_change'][k] for k in ('id', 'conversation_id', 'title')})
        again = plan_changes.accept(text, conversation, turn)
        self.assertTrue(again['already_applied'])
        self.assertEqual(2, self.stored()[1])
        self.assertEqual(1, self.changes_count())
        recorded = plan_changes.preview(text, conversation, turn)
        self.assertEqual(('applied', result['change']['days']), (recorded['status'], recorded['days']))

    def test_changing_sets_keeps_the_athletes_own_fixed_weights_by_position(self):
        plan_changes.accept(self.reply([dict(op='set_sets', day=1, exercise_template_id='squat',
                                             sets=[dict(reps=2, rpe=8.5, ts=True), dict(reps=4, rpe=7)])]), *self.ids())
        sets = self.stored()[0]['weeks'][0]['sessions'][0]['exercises'][0]['sets']
        self.assertEqual([140, None], [s['weight_kg'] for s in sets])
        self.assertEqual([2, 4], [s['reps'] for s in sets])

    def test_accept_never_activates_or_deactivates(self):
        mesocycles.activate(self.plan['id'])
        self.plan = mesocycles.get_plan(self.plan['id'])
        plan_changes.accept(self.reply(), *self.ids())
        self.assertEqual(1, self.stored()[2])

    def test_refused_accepts_change_nothing(self):
        before = self.stored()
        with self.assertRaises(plan_changes.ChangeError) as stale:
            plan_changes.accept(self.reply(revision=5), *self.ids())
        self.assertEqual(409, stale.exception.status)
        with self.assertRaises(plan_changes.ChangeError) as invalid:
            plan_changes.accept(self.reply([dict(op='remove', day=9, exercise_template_id='squat')]), *self.ids())
        self.assertEqual(422, invalid.exception.status)
        with self.assertRaises(plan_changes.ChangeError):
            plan_changes.accept('No change this week.', *self.ids())
        self.assertEqual(before, self.stored())
        self.assertEqual(0, self.changes_count())

    def test_a_second_change_must_be_written_against_the_new_revision(self):
        plan_changes.accept(self.reply(), *self.ids())
        with self.assertRaises(plan_changes.ChangeError):
            plan_changes.accept(self.reply([dict(op='remove', day=3, exercise_template_id='bench')]), *self.ids())
        self.plan = mesocycles.get_plan(self.plan['id'])
        plan_changes.accept(self.reply([dict(op='remove', day=3, exercise_template_id='bench')]), *self.ids())
        self.assertEqual([], self.stored()[0]['weeks'][0]['sessions'][2]['exercises'])


class UndoTests(ChangeCase):
    def accepted(self, changes=None):
        return plan_changes.accept(self.reply(changes), *self.ids())['change']['change_id']

    def test_undo_restores_the_previous_plan_exactly_once(self):
        original = self.stored()[0]
        identifier = self.accepted()
        result = plan_changes.undo(identifier)
        self.assertEqual('undone', result['change']['status'])
        self.assertFalse(result['change']['can_undo'])
        self.assertIsNone(result['plan']['coach_change'])
        document, revision, _ = self.stored()
        self.assertEqual(original, document)
        self.assertEqual(3, revision)
        with self.assertRaises(plan_changes.ChangeError) as again:
            plan_changes.undo(identifier)
        self.assertEqual(409, again.exception.status)
        with self.assertRaises(plan_changes.ChangeError) as missing:
            plan_changes.undo(str(uuid4()))
        self.assertEqual(404, missing.exception.status)

    def test_undo_is_refused_after_the_builder_edits_the_plan(self):
        identifier = self.accepted()
        current = mesocycles.get_plan(self.plan['id'])
        mesocycles.save_plan(mesocycles.PlanInput.model_validate(dict(current, notes='My own edit')), self.plan['id'])
        with self.assertRaises(plan_changes.ChangeError) as refused:
            plan_changes.undo(identifier)
        self.assertIn('edited after this change', str(refused.exception))
        self.assertEqual('My own edit', self.stored()[0]['notes'])

    def test_undo_is_refused_once_a_changed_day_is_trained_but_not_for_other_days(self):
        identifier = self.accepted()
        self.finish('d1')  # day 1 was not part of the change, so undo stays available
        self.assertIsNone(plan_changes.undo(identifier)['change']['undo_problem'])
        self.plan = mesocycles.get_plan(self.plan['id'])
        conversation, turn = self.ids()
        text = self.reply()
        identifier = plan_changes.accept(text, conversation, turn)['change']['change_id']
        self.finish('d2', 'skipped')
        recorded = plan_changes.preview(text, conversation, turn)
        self.assertFalse(recorded['can_undo'])
        self.assertIn('trained or skipped since', recorded['undo_problem'])
        with self.assertRaises(plan_changes.ChangeError):
            plan_changes.undo(identifier)


class RouteTests(ChangeCase):
    def request(self, text, conversation, turn):
        return dict(text=text, conversation_id=str(conversation), turn_id=str(turn))

    def test_preview_accept_and_undo_routes_never_contact_hevy(self):
        conversation, turn = self.ids()
        body = self.request(self.reply(), conversation, turn)
        preview = self.client.post('/api/plan-changes/preview', json=body)
        self.assertEqual(200, preview.status_code)
        self.assertTrue(preview.json()['valid'])
        accepted = self.client.post('/api/plan-changes/accept', json=body)
        self.assertEqual(200, accepted.status_code, accepted.text)
        change = accepted.json()['change']['change_id']
        listed = self.client.get('/api/mesocycles').json()
        self.assertEqual('Ease day 2', listed[0]['coach_change']['title'])
        stale = self.client.post('/api/plan-changes/accept', json=self.request(self.reply(), *self.ids()))
        self.assertEqual(409, stale.status_code)
        self.assertIn('edited since', stale.json()['detail'])
        undone = self.client.post(f'/api/plan-changes/{change}/undo')
        self.assertEqual(200, undone.status_code, undone.text)
        self.assertEqual(409, self.client.post(f'/api/plan-changes/{change}/undo').status_code)
        self.assertEqual(422, self.client.post('/api/plan-changes/not-a-uuid/undo').status_code)
        self.assertEqual(422, self.client.post('/api/plan-changes/accept', json=self.request('Just talk', *self.ids())).status_code)
        self.hevy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
