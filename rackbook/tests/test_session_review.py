"""Descriptive review evidence, with no network or real databases."""
import copy
import unittest

from rackbook.session_review import build, Prescription


def captured_payload():
    def meta(set_id, minute):
        return dict(set_id=set_id, exercise_id='movement', suggested_weight_kg=100,
                    manual_weight=False, ls_enabled=True, basis='e1rm', rpe_source='entered',
                    actual_percentage=.8, completed_at=f'2026-11-04T10:{minute}:00Z')
    return dict(title='Session', start_time='2026-11-04T10:00:00Z', end_time='2026-11-04T11:00:00Z',
        prescription=dict(version=1, source='plan', name='Original session', plan_revision=3,
            rpe_chart=[dict(rpe=6,reps=5,percentage=.75),dict(rpe=7,reps=5,percentage=.8)],
            exercises=[dict(id='movement',exercise_template_id='sq',title='Squat',sets=[
                dict(id=key,reps=5,rpe=6,weight_kg=None,type='normal',ts=False) for key in ('a','b','c')])]),
        exercises=[dict(exercise_template_id='sq',title='Squat',sets=[
            dict(type='normal',weight_kg=100,reps=5,rpe=7,target_rpe=6,review=meta('a','10')),
            dict(type='normal',weight_kg=95,reps=5,rpe=7,target_rpe=6,review=meta('b','15'))])])


class SessionDescriptionTests(unittest.TestCase):
    def test_original_sets_reps_and_like_for_like_e1rm(self):
        payload=captured_payload()
        before=copy.deepcopy(payload)
        ex=build(payload)['movements'][0]
        self.assertEqual((ex['planned_sets'],ex['completed_sets'],ex['omitted_sets'],ex['added_sets']),(3,2,1,0))
        self.assertEqual((ex['planned_reps'],ex['completed_reps']),(15,10))
        self.assertAlmostEqual(ex['change_pct'],-5)
        self.assertEqual(ex['opening_e1rm_kg'],125)
        self.assertEqual(payload,before,'Review must never alter programming or recorded data')

    def test_changed_reps_and_targets_keep_the_original(self):
        payload=captured_payload()
        payload['exercises'][0]['sets'][1].update(reps=4,target_rpe=7)
        ex=build(payload)['movements'][0]
        self.assertEqual((ex['sets'][1]['planned_reps'],ex['sets'][1]['actual_reps']),(5,4))
        self.assertEqual((ex['sets'][1]['planned_rpe'],ex['sets'][1]['target_rpe']),(6,7))
        self.assertIsNone(ex['change_pct'])

    def test_copied_or_unknown_rpe_is_not_independent_performance_evidence(self):
        for source in ('copied_target','unknown','unrated'):
            payload=captured_payload()
            payload['exercises'][0]['sets'][0]['review']['rpe_source']=source
            ex=build(payload)['movements'][0]
            self.assertIsNone(ex['opening_e1rm_kg'])
            self.assertIsNone(ex['change_pct'])

    def test_removed_and_added_movements_are_counted_separately(self):
        payload=captured_payload()
        payload['exercises'][0]['exercise_template_id']='bench'
        for s in payload['exercises'][0]['sets']:
            s['review']['exercise_id']='added'
            s['review']['set_id']='added-'+s['review']['set_id']
        old,new=build(payload)['movements']
        self.assertEqual((old['completed_sets'],old['omitted_sets']),(0,3))
        self.assertEqual((new['planned_sets'],new['added_sets']),(0,2))

    def test_top_sets_are_not_compared_as_backoffs(self):
        payload=captured_payload()
        payload['exercises'][0]['sets'][0]['ts']=True
        ex=build(payload)['movements'][0]
        self.assertEqual([s['role'] for s in ex['sets']],['top set','back-off'])
        self.assertIsNone(ex['change_pct'])

    def test_actual_completion_time_controls_opening_and_final(self):
        payload=captured_payload()
        payload['exercises'][0]['sets'][1]['review']['completed_at']='2026-11-04T10:05:00Z'
        ex=build(payload)['movements'][0]
        self.assertEqual(ex['opening_e1rm_kg'],95/.8)
        self.assertEqual(ex['last_e1rm_kg'],125)

    def test_missing_reps_are_unknown_not_zero(self):
        payload=captured_payload()
        payload['exercises'][0]['sets'][0]['reps']=None
        ex=build(payload)['movements'][0]
        self.assertIsNone(ex['completed_reps'])
        self.assertIsNone(ex['opening_e1rm_kg'])

    def test_ad_hoc_and_legacy_prescriptions_are_not_invented(self):
        payload=captured_payload()
        payload['prescription'].update(source='ad_hoc',exercises=[])
        ex=build(payload)['movements'][0]
        self.assertIsNone(ex['planned_sets'])
        self.assertIsNone(ex['added_sets'])
        payload.pop('prescription')
        self.assertEqual(build(payload)['prescription_source'],'unavailable')

    def test_snapshot_ids_and_numeric_evidence_are_validated(self):
        from pydantic import ValidationError
        payload=captured_payload()
        payload['prescription']['exercises'][0]['sets'][1]['id']='a'
        with self.assertRaises(ValidationError):Prescription(**payload['prescription'])

    def test_manual_weight_basis_still_records_actual_performance(self):
        from rackbook.session_review import SetEvidence
        payload=captured_payload()
        for s in payload['exercises'][0]['sets']:
            s['review'].update(basis='manual',ls_enabled=False,suggested_weight_kg=None)
            SetEvidence(**s['review'])
        self.assertEqual(build(payload)['movements'][0]['opening_e1rm_kg'],125)
