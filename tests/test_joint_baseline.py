"""Joint baseline rules (#154) with made-up check-ins; no database for the pure rules."""
from datetime import date, timedelta
import unittest

import joint_baseline as jb

TODAY = date(2026, 11, 26)


def days(ratings, end=TODAY, field='joint_lower'):
    """Consecutive daily check-ins ending on `end`, oldest first."""
    start = end - timedelta(days=len(ratings) - 1)
    return [{'date': start + timedelta(days=i), field: r} for i, r in enumerate(ratings)]


def decision(region, decided_on, outcome, until=None, level=None, ident='d1'):
    return dict(id=ident, region=region, decided_on=decided_on, outcome=outcome, until=until, level=level,
                note='', created_at=f'{decided_on}T12:00:00+00:00')


def lower(checkins, decisions=(), today=TODAY):
    return jb.status(checkins, list(decisions), today)['regions']['lower']


class UsualLevelTests(unittest.TestCase):
    def test_usual_is_the_most_common_prior_rating(self):
        state = lower(days([1] * 20 + [0] * 5 + [1]))
        self.assertEqual((state['usual'], state['baseline_status']), (1, 'tracking'))

    def test_fewer_than_seven_prior_checkins_is_still_collecting(self):
        state = lower(days([1] * 7))   # the last one is compared against six earlier ones
        self.assertEqual((state['usual'], state['baseline_status'], state['level']), (None, 'collecting', 'none'))
        self.assertEqual(lower(days([1] * 8))['usual'], 1)

    def test_a_tie_goes_to_the_lower_rating(self):
        self.assertEqual(lower(days([1, 2] * 5 + [2]))['usual'], 1)

    def test_only_the_last_28_days_count(self):
        old = days([3] * 20, end=TODAY - timedelta(days=40))
        self.assertEqual(lower(old + days([0] * 10))['usual'], 0)

    def test_usual_moves_down_on_its_own(self):
        self.assertEqual(lower(days([1] * 14 + [0] * 20))['usual'], 0)


class WarningCountTests(unittest.TestCase):
    def test_one_or_two_raised_checkins_are_recorded_only(self):
        state = lower(days([1] * 20 + [2, 1, 2]))
        self.assertEqual((state['level'], state['notice_count'], state['call_due']), ('none', 2, False))

    def test_three_of_the_last_seven_is_a_notice_with_a_call_and_hold(self):
        state = lower(days([1] * 20 + [2, 1, 2, 1, 1, 2]))
        self.assertEqual((state['level'], state['call_due'], state['hold']), ('notice', True, True))
        status = jb.status(days([1] * 20 + [2, 1, 2, 1, 1, 2]), [], TODAY)
        self.assertEqual(status['held_patterns'], ['hip', 'knee'])
        self.assertEqual((status['call']['kind'], status['call']['regions']), ('notice', ['lower']))

    def test_five_of_the_last_ten_is_a_review(self):
        state = lower(days([1] * 20 + [2, 1, 2, 2, 1, 2, 2]))
        self.assertEqual(state['level'], 'review')

    def test_raised_checkins_older_than_fourteen_days_drop_out_of_the_notice_count(self):
        checkins = days([1] * 20, end=TODAY - timedelta(days=20)) + days([2, 2], end=TODAY - timedelta(days=15)) + days([1, 2])
        state = lower(checkins)
        self.assertEqual((state['notice_count'], state['level']), (1, 'none'))

    def test_the_notice_clears_once_the_count_drops(self):
        state = lower(days([1] * 20 + [2, 2, 2] + [1] * 7))
        self.assertEqual((state['level'], state['call_due']), ('none', False))

    def test_missing_ratings_are_unknown_not_zero(self):
        checkins = days([1] * 20 + [2, 2, 2])
        checkins[-2]['joint_lower'] = None
        self.assertEqual(lower(checkins)['notice_count'], 2)

    def test_regions_are_counted_separately(self):
        checkins = days([1] * 20 + [2, 2, 2])
        for c in checkins:
            c['joint_upper'] = 0
        status = jb.status(checkins, [], TODAY)
        self.assertEqual((status['regions']['upper']['level'], status['regions']['lower']['level']), ('none', 'notice'))
        self.assertEqual(status['held_patterns'], ['hip', 'knee'])


class FlareDaysNeverBecomeUsualTests(unittest.TestCase):
    def test_three_weeks_of_twos_keep_the_warning_instead_of_becoming_normal(self):
        state = lower(days([1] * 28 + [2] * 21))
        self.assertEqual((state['usual'], state['level'], state['call_due']), (1, 'review', True))

    def test_a_settled_flare_leaves_usual_where_it_was(self):
        state = lower(days([1] * 28 + [2] * 14 + [1] * 10))
        self.assertEqual((state['usual'], state['level']), (1, 'none'))


class DecisionTests(unittest.TestCase):
    checkins = days([1] * 28 + [2] * 6)
    decided = TODAY - timedelta(days=1)

    def test_new_normal_raises_usual_and_restarts_the_count(self):
        made = [decision('lower', self.decided, 'new_normal', level=2)]
        state = lower(self.checkins, made)
        self.assertEqual((state['usual'], state['level'], state['call_due']), (2, 'none', False))

    def test_after_a_new_normal_usual_can_still_move_down(self):
        made = [decision('lower', TODAY - timedelta(days=30), 'new_normal', level=2)]
        checkins = days([1] * 28 + [2] * 6, end=TODAY - timedelta(days=29)) + days([1] * 28)
        self.assertEqual(lower(checkins, made)['usual'], 1)

    def test_carry_on_covers_the_call_until_its_date_without_moving_usual(self):
        made = [decision('lower', self.decided, 'carry_on', until=TODAY + timedelta(days=6))]
        state = lower(self.checkins, made)
        self.assertEqual((state['usual'], state['level'], state['call_due'], state['hold']), (1, 'review', False, False))
        self.assertEqual(state['carry_on_until'], str(TODAY + timedelta(days=6)))

    def test_carry_on_ends_at_its_date(self):
        made = [decision('lower', TODAY - timedelta(days=8), 'carry_on', until=TODAY)]
        self.assertTrue(lower(self.checkins, made)['call_due'])

    def test_a_rating_of_three_brings_the_call_back_early(self):
        made = [decision('lower', self.decided, 'carry_on', until=TODAY + timedelta(days=6))]
        checkins = days([1] * 28 + [2] * 5 + [3])
        self.assertTrue(lower(checkins, made)['call_due'])

    def test_a_change_restarts_the_count(self):
        made = [decision('lower', self.decided, 'change')]
        state = lower(self.checkins, made)
        self.assertEqual((state['usual'], state['level'], state['call_due']), (1, 'none', False))
        later = days([1] * 28 + [2] * 6 + [2, 2, 2], end=TODAY + timedelta(days=3))
        self.assertTrue(lower(later, made, TODAY + timedelta(days=3))['call_due'])

    def test_not_now_keeps_the_call_and_the_hold(self):
        made = [decision('lower', self.decided, 'not_now')]
        state = lower(self.checkins, made)
        self.assertEqual((state['call_due'], state['hold']), (True, True))

    def test_each_decision_gives_a_returning_call_a_new_conversation(self):
        first = jb.status(self.checkins, [], TODAY)['call']['id']
        again = jb.status(self.checkins, [decision('lower', self.decided, 'not_now')], TODAY)['call']['id']
        self.assertNotEqual(first, again)

    def test_accepted_level_is_the_most_common_raised_rating(self):
        state = lower(days([1] * 28 + [2, 3, 2, 2]))
        self.assertEqual(jb.accepted_level(state), 2)


class MovementEvidenceTests(unittest.TestCase):
    def evidence(self, training, patterns, ratings):
        return jb.movement_evidence(days(ratings), training, patterns, TODAY)['regions']['lower']

    def test_compares_the_checkin_after_lift_days_with_other_checkins(self):
        ratings = [1] * 20 + [2, 1, 2, 1, 2, 1]
        squat_days = {TODAY - timedelta(days=6), TODAY - timedelta(days=4), TODAY - timedelta(days=2)}
        training = {'Squat (Barbell)': squat_days, 'Box Squat': {TODAY - timedelta(days=9)}}
        result = self.evidence(training, {'Squat (Barbell)': 'knee', 'Box Squat': 'knee'}, ratings)
        lift, _box, pattern = result['lines']
        self.assertEqual((lift['name'], lift['after_count'], lift['after_average'], lift['status']),
                         ('Squat (Barbell)', 3, 2.0, 'early'))
        self.assertEqual((lift['other_count'], lift['other_average']), (23, 1.0))
        self.assertEqual((pattern['kind'], pattern['name'], pattern['after_count']), ('pattern', 'Knee pattern overall', 4))

    def test_a_pattern_with_one_lift_has_no_repeated_pattern_line(self):
        result = self.evidence({'Squat': {TODAY - timedelta(days=2)}}, {'Squat': 'knee'}, [1] * 20)
        self.assertEqual([x['kind'] for x in result['lines']], ['lift'])

    def test_too_few_after_lift_checkins_are_collecting(self):
        result = self.evidence({'Front Squat': {TODAY - timedelta(days=2)}}, {'Front Squat': 'knee'}, [1] * 20)
        self.assertEqual((result['lines'][0]['status'], result['lines'][0]['after_average']), ('collecting', None))

    def test_same_day_training_belongs_to_the_next_checkin(self):
        result = self.evidence({'Squat': {TODAY}}, {'Squat': 'knee'}, [1] * 20)
        self.assertEqual(result['lines'], [])

    def test_upper_lifts_are_not_in_the_lower_report(self):
        result = self.evidence({'Bench Press': {TODAY - timedelta(days=2)}}, {'Bench Press': 'push'}, [1] * 20)
        self.assertEqual(result['lines'], [])

    def test_primary_pattern_uses_the_largest_share(self):
        self.assertEqual(jb.primary_pattern({'pct_quad_dom': 0.35, 'pct_posterior': 0.65}), 'hip')
        self.assertIsNone(jb.primary_pattern({}))


class DecisionInputTests(unittest.TestCase):
    def test_carry_on_needs_a_date_and_others_must_not_have_one(self):
        from uuid import uuid4
        with self.assertRaises(ValueError):
            jb.DecisionInput(id=uuid4(), regions=['lower'], outcome='carry_on')
        with self.assertRaises(ValueError):
            jb.DecisionInput(id=uuid4(), regions=['lower'], outcome='change', until=TODAY)
        jb.DecisionInput(id=uuid4(), regions=['lower'], outcome='carry_on', until=TODAY + timedelta(days=7))


if __name__ == '__main__':
    unittest.main()
