"""Stress is a separate, descriptive metric. No calls to the real Hevy account."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import unittest

from rackbook import stress_index as stress

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)


def S(w=220, reps=5, rpe=6, **extra):
    return {"weight_kg":w, "reps":reps, "rpe":rpe, "type":"normal", **extra}


def history(days=1, id="one", **set_args):
    return {**S(**set_args), "workout_id":id, "workout_start_time":(NOW-timedelta(days=days)).isoformat()}


class TestSessionStress(unittest.TestCase):
    def test_contributions_share_reference_and_sum_to_session(self):
        sets = [S(231, 3, 7), S(), S(type='warmup'), S(reps=0), S(180, 8, None)]
        total, rows = stress.score_session_sets(sets)
        self.assertEqual(len(sets), len(rows))
        self.assertIsNone(rows[2])
        self.assertIsNone(rows[3])
        self.assertEqual(1, rows[4]['estimated_sets'])
        for key in ('total', 'central', 'peripheral'):
            self.assertAlmostEqual(total[key], sum(row[key] for row in rows if row))
        self.assertNotAlmostEqual(stress.session_score([sets[1]])['total'], rows[1]['total'])
        self.assertEqual(total, stress.session_score(sets))

    def test_unchecked_preview_does_not_enter_rolling_totals(self):
        checked, planned = [S()], [S(), S(231, 3, 7)]
        result = stress.build_summary([], checked, now=NOW, preview_sets=planned)
        self.assertEqual(1, result['session']['sets'])
        self.assertEqual(2, result['preview']['sets'])
        self.assertEqual(2, len(result['preview_set_scores']))
        self.assertEqual(result['session'], result['rolling_7'])
        self.assertEqual(result['session'], result['rolling_28'])
        self.assertEqual('no_baseline', result['preview_status'])
        self.assertEqual(checked + [planned[1]], planned)

    def test_preview_band_colors_use_preview_total_and_existing_thresholds(self):
        for value, expected in [(0.79, 'below_usual'), (.8, 'usual'), (1.2, 'usual'), (1.21, 'elevated'), (1.51, 'much_higher')]:
            self.assertEqual(expected, stress.stress_status(dict(total=value, sets=1), 1))
        self.assertEqual('no_sets', stress.stress_status(dict(total=0, sets=0), 1))
        self.assertEqual('no_baseline', stress.stress_status(dict(total=1, sets=1), None))

    def test_reproduces_controlled_examples_without_using_loading_chart(self):
        cases = [([S()], (.48,.59,.37)),
                 ([S(231,3,7),S()], (1.25,1.20,1.30)),
                 ([S(231,1,10),S(198,5,6)], (2.59,1.20,3.98)),
                 ([S(231,1,9.5),S(209,3,8)], (2.20,1.23,3.18))]
        for sets, expected in cases:
            with self.subTest(sets=sets):
                result = stress.session_score(sets)
                for key, value in zip(("total","peripheral","central"),expected):
                    self.assertAlmostEqual(value,result[key],delta=.03)
                self.assertEqual(result['total'],(result['peripheral']+result['central'])/2)

    def test_uniform_weight_scaling_and_order_do_not_change_score(self):
        sets=[S(231,3,7),S()]
        expected=stress.session_score(sets)
        self.assertEqual(expected,stress.session_score(list(reversed(sets))))
        scaled=[dict(s,weight_kg=s['weight_kg']/2.20462) for s in sets]
        for key in ('total','central','peripheral'):
            self.assertAlmostEqual(expected[key],stress.session_score(scaled)[key])

    def test_missing_rpe_is_flagged_and_does_not_mutate_source(self):
        sets=[S(231,3,7),S(rpe=None)]
        original=deepcopy(sets)
        result=stress.session_score(sets)
        self.assertEqual(1,result['estimated_sets'])
        self.assertEqual(stress.session_score([sets[0],S(rpe=5)])['total'],result['total'])
        self.assertEqual(original,sets)
        self.assertNotEqual(stress.session_score([S(rpe=0)])['total'],stress.session_score([S(rpe=None)])['total'])

    def test_warmups_excluded_and_invalid_or_uncovered_sets_reported(self):
        sets=[S(type='warmup'),S(w=0),S(reps=0),S(reps=100),S(w=float('nan'))]
        result=stress.session_score(sets)
        self.assertEqual((0,4,0),(result['sets'],result['skipped_sets'],result['total']))

    def test_tied_heaviest_sets_have_an_order_independent_reference(self):
        sets=[S(100,3,7),S(100,3,9)]
        self.assertEqual(stress.session_score(sets),stress.session_score(list(reversed(sets))))


class TestHistoryAndWindows(unittest.TestCase):
    def test_local_snapshot_replaces_hevy_and_preserves_low_rpe(self):
        remote=[history(),history(id='other')]
        local=[dict(S(rpe=4.5),hevy_workout_id='one',workout_start=remote[0]['workout_start_time'])]
        merged=stress.merge_history(remote,local)
        self.assertEqual(2,len(merged))
        self.assertEqual(4.5,next(s['rpe'] for s in merged if s['workout_id']=='one'))
        self.assertEqual('other',merged[0]['workout_id'])

    def test_local_only_workout_is_included_once(self):
        local=[dict(S(),hevy_workout_id='local',workout_start=NOW.isoformat())]
        self.assertEqual(1,len(stress.merge_history([],local)))

    def test_cutoffs_future_timezone_and_draft_counted_once(self):
        entries=[history(1,'a'),history(7,'b'),history(8,'c'),history(28,'d'),history(-1,'future')]
        offset=history(2,'offset')
        offset['workout_start_time']=(NOW-timedelta(days=2)).astimezone(timezone(timedelta(hours=-4))).isoformat()
        entries.append(offset)
        result=stress.build_summary(entries,[S()],now=NOW)
        one=stress.session_score([S()])['total']
        self.assertAlmostEqual(3*one,result['rolling_7']['total']) # 1d, 2d, draft
        self.assertAlmostEqual(5*one,result['rolling_28']['total']) # adds 7d and 8d
        self.assertEqual(5,result['window']['sessions']) # includes 28d, not future/draft

    def test_baseline_uses_sessions_not_empty_weeks_and_excludes_draft(self):
        entries=[history(2,'a'),history(20,'b'),history(40,'c'),history(57,'old')]
        result=stress.build_summary(entries,[S(reps=10,rpe=10)],now=NOW)
        self.assertEqual(3,result['window']['sessions'])
        typical=stress.session_score([S()])['total']
        self.assertAlmostEqual(typical,result['window']['median'])
        self.assertAlmostEqual(.8*typical,result['window']['lower'])
        self.assertTrue(result['window']['provisional'])
        self.assertEqual('much_higher',result['status'])

    def test_empty_history_has_no_invented_window(self):
        result=stress.build_summary([],[],now=NOW)
        self.assertIsNone(result['window']['median'])
        self.assertEqual('no_sets',result['status'])
        self.assertEqual('no_baseline',stress.build_summary([],[S()],now=NOW)['status'])

    def test_old_draft_not_added_to_recent_totals(self):
        result=stress.build_summary([], [S()],now=NOW,session_start=NOW-timedelta(days=8))
        self.assertEqual(0,result['rolling_7']['total'])
        self.assertGreater(result['rolling_28']['total'],0)


class TestRetrospectiveDashboard(unittest.TestCase):
    def test_old_sessions_are_recalculated_without_future_data_in_their_windows(self):
        entries=[history(30,'first'),history(20,'second'),history(1,'later',reps=10,rpe=10)]
        result=stress.build_dashboard(entries,now=NOW,days=0)
        first,second,later=result['sessions']
        self.assertEqual('first',first['workout_id'])
        self.assertIsNone(first['window']['median'])
        self.assertEqual(1,second['window']['sessions'])
        self.assertAlmostEqual(first['score']['total'],second['window']['median'])
        self.assertEqual(2,later['window']['sessions'])
        self.assertEqual('much_higher',later['status'])

    def test_display_range_keeps_earlier_baseline_and_rolling_work(self):
        entries=[history(3,'latest'),history(9,'earlier'),history(30,'old')]
        result=stress.build_dashboard(entries,now=NOW,days=7)
        self.assertEqual(1,len(result['sessions']))
        self.assertEqual(3,result['available_sessions'])
        latest=result['sessions'][0]
        self.assertEqual(2,latest['window']['sessions'])
        one=stress.session_score([S()])['total']
        self.assertAlmostEqual(2*one,latest['rolling_7']['total']) # day -9 is 6 days before latest
        self.assertAlmostEqual(3*one,latest['rolling_28']['total'])
        self.assertAlmostEqual(one,result['current']['rolling_7']['total'])

    def test_snapshot_matches_live_history_summary_without_draft(self):
        entries=[history(1,'first'),history(8,'second'),history(40,'third')]
        self.assertEqual(stress.build_summary(entries,[],now=NOW),
                         stress.build_dashboard(entries,now=NOW)['current'])

    def test_estimates_skips_future_and_warmup_only_sessions(self):
        entries=[history(2,'estimated',rpe=None),history(1,'invalid',w=0),
                 history(-1,'future'),history(3,'warm',type='warmup')]
        original=deepcopy(entries)
        result=stress.build_dashboard(entries,now=NOW)
        self.assertEqual(2,result['available_sessions'])
        self.assertEqual(1,result['sessions'][0]['score']['estimated_sets'])
        self.assertEqual(1,result['sessions'][1]['score']['skipped_sets'])
        self.assertEqual(original,entries)

    def test_no_workout_at_identical_timestamp_enters_the_others_baseline(self):
        entries=[history(2,'a'),history(2,'b',rpe=9)]
        result=stress.build_dashboard(entries,now=NOW)
        self.assertTrue(all(s['window']['sessions']==0 for s in result['sessions']))
        self.assertEqual(2,result['current']['window']['sessions'])


def workout(days, id, sets):
    start = (NOW - timedelta(days=days)).isoformat()
    return [{**s, "workout_id": id, "workout_start_time": start} for s in sets]


TOP = S(100, 1, 9)
BACK = [S(80, 5, 8)] * 4


class TestHistoryReference(unittest.TestCase):
    def test_model_version_marks_the_reference_change(self):
        self.assertEqual('rackbook-stress-v2', stress.MODEL_VERSION)
        self.assertEqual('rackbook-stress-v2', stress.build_summary([], [], now=NOW)['model_version'])

    def test_adding_a_top_set_no_longer_lowers_the_session(self):
        alone = stress.session_score(BACK)['total']
        self.assertLess(stress.session_score([TOP] + BACK)['total'], alone)  # the v1 defect, no history
        entries = workout(10, 'top', [TOP])
        without = stress.build_summary(entries, BACK, now=NOW)
        with_top = stress.build_summary(entries, [TOP] + BACK, now=NOW)
        self.assertGreater(with_top['session']['total'], without['session']['total'])
        for before, after in zip(without['set_scores'], with_top['set_scores'][1:]):
            self.assertAlmostEqual(before['total'], after['total'])

    def test_history_reference_is_the_larger_of_history_and_own_session(self):
        history_e1rm = stress.session_e1rm([TOP])
        own = stress.session_score(BACK)
        self.assertEqual(own, stress.session_score(BACK, history_e1rm * .5))   # lower history ignored
        self.assertEqual(own, stress.session_score(BACK, None))
        for bad in (float('nan'), float('inf'), 0, -5, True, 'x'):
            self.assertEqual(own, stress.session_score(BACK, bad))
        self.assertLess(stress.session_score(BACK, history_e1rm)['total'], own['total'])

    def test_a_session_that_beats_its_history_sets_its_own_reference(self):
        entries = workout(10, 'old', [S(60, 5, 8)])
        self.assertEqual(stress.session_score(BACK),
                         stress.build_summary(entries, BACK, now=NOW)['session'])

    def test_blank_rpe_history_never_sets_the_reference(self):
        entries = workout(10, 'imported', [S(100, 5, None)])
        self.assertIsNone(stress.session_e1rm([S(100, 5, None)]))
        self.assertEqual(stress.session_score(BACK),
                         stress.build_summary(entries, BACK, now=NOW)['session'])
        mixed = workout(10, 'mixed', [S(100, 5, None), S(60, 5, 8)])
        self.assertEqual(stress.session_e1rm([S(60, 5, 8)]), stress.session_e1rm(mixed))

    def test_session_anchor_names_the_heaviest_recorded_set_and_its_e1rm(self):
        sets = [S(60, 5, 8), S(100, 5, None), S(90, 3, 9), S(90, 5, 8, type="warmup"), S(90, 4, 9)]
        anchor = stress.session_anchor(sets)
        self.assertEqual((2, 90, 3, 9), (anchor["index"], anchor["weight_kg"], anchor["reps"], anchor["rpe"]))
        self.assertEqual(stress.session_e1rm(sets), anchor["e1rm"])
        self.assertIsNone(stress.session_anchor([S(100, 5, None), S(80, 5, 8, type="warmup")]))
        self.assertIsNone(stress.session_anchor([]))

    def test_reference_window_is_84_days_before_the_session(self):
        base = stress.session_score(BACK)['total']
        for days, applies in ((83, True), (84, False), (120, False)):
            with self.subTest(days=days):
                total = stress.build_summary(workout(days, 'top', [TOP]), BACK, now=NOW)['session']['total']
                self.assertEqual(applies, total < base)

    def test_dashboard_sessions_use_only_earlier_history(self):
        entries = workout(30, 'earlier', BACK) + workout(5, 'later', [TOP])
        earlier, later = stress.build_dashboard(entries, now=NOW, days=0)['sessions']
        self.assertEqual(stress.session_score(BACK), earlier['score'])  # later top set cannot lower it
        entries = workout(30, 'top', [TOP]) + workout(5, 'back', BACK)
        _, back = stress.build_dashboard(entries, now=NOW, days=0)['sessions']
        self.assertEqual(stress.session_score(BACK, stress.session_e1rm([TOP])), back['score'])

    def test_draft_started_earlier_ignores_later_saved_sessions(self):
        entries = workout(2, 'later', [TOP])
        result = stress.build_summary(entries, BACK, now=NOW, session_start=NOW - timedelta(days=5))
        self.assertEqual(stress.session_score(BACK), result['session'])

    def test_identical_timestamps_do_not_set_each_others_reference(self):
        entries = workout(4, 'a', [TOP]) + workout(4, 'b', BACK)
        scores = {s['workout_id']: s['score'] for s in stress.build_dashboard(entries, now=NOW, days=0)['sessions']}
        self.assertEqual(stress.session_score([TOP]), scores['a'])
        self.assertEqual(stress.session_score(BACK), scores['b'])

    def test_history_inputs_and_set_order_are_not_mutated_or_order_dependent(self):
        entries = workout(10, 'top', [TOP]) + workout(3, 'back', BACK)
        original = deepcopy(entries)
        forward = stress.build_dashboard(entries, now=NOW, days=0)
        self.assertEqual(forward, stress.build_dashboard(list(reversed(entries)), now=NOW, days=0))
        self.assertEqual(original, entries)

    def test_single_set_scores_still_match_the_published_table(self):
        for reps, rpe, expected in ((3, 9, 1.23), (12, 10, 1.11), (1, 10, 1.51)):
            with self.subTest(reps=reps, rpe=rpe):
                self.assertAlmostEqual(expected, stress.session_score([S(100, reps, rpe)])['total'], places=2)
