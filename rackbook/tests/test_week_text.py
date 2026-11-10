"""Pure week-text reader: notation, callouts, exact movement matching and line-referenced errors."""
import unittest

from rackbook.week_text import parse_week_text, plan_sessions

TITLES = {
    'sq-low': 'squat, low bar w/ belt',
    'sq': 'Squat (Barbell)',
    'bench': 'Bench Press (Barbell)',
    'bench-db': 'Bench Press (Dumbbell)',
    'board': '3-board press',
    'lat': 'Lateral Raise (Dumbbell)',
    'dl': 'Deadlift (Barbell)',
    'dup-a': 'Pull Up',
    'dup-b': 'pull up',
}


def read(text, choices=None):
    return parse_week_text(text, TITLES, choices)


def only_movement(text, choices=None):
    result = read('Week 1 Day 1\n' + text, choices)
    return result, result['weeks'][0]['days'][0]['exercises'][0] if result['weeks'] and result['weeks'][0]['days'][0]['exercises'] else None


def messages(result):
    return [(e['line'], e['message']) for e in result['errors']]


class Notation(unittest.TestCase):
    def test_brians_example_reads_with_exact_names(self):
        result = read('Week 1 Day 1\n#squat, low bar w/ belt 3x3@6,7,8\n#Bench Press (Barbell) 5x4@6 DDP')
        self.assertEqual(result['errors'], [])
        self.assertTrue(result['ready'])
        squat, bench = result['weeks'][0]['days'][0]['exercises']
        self.assertEqual((squat['exercise_template_id'], squat['status']), ('sq-low', 'matched'))
        self.assertEqual([(s['reps'], s['rpe']) for s in squat['sets']], [(3, 6), (3, 7), (3, 8)])
        self.assertEqual(len(bench['sets']), 5)
        self.assertTrue(all(s['ddp'] and s['rpe'] == 6 and s['reps'] == 4 for s in bench['sets']))

    def test_multiplier_spellings_and_spacing(self):
        for spec in ('3x5@7', '3X5@7', '3×5@7', '3 x 5 @ 7'):
            result, movement = only_movement('#Squat (Barbell) ' + spec)
            self.assertEqual(result['errors'], [], spec)
            self.assertEqual([(s['reps'], s['rpe']) for s in movement['sets']], [(5, 7.0)] * 3)

    def test_rpe_is_optional(self):
        _, movement = only_movement('#Squat (Barbell) 3x5')
        self.assertEqual([s['rpe'] for s in movement['sets']], [None] * 3)

    def test_top_set_and_back_off_groups(self):
        result, movement = only_movement('#Squat (Barbell) 1x3@8 TS, 3x5@7 BO')
        self.assertEqual(result['errors'], [])
        self.assertEqual([(s['reps'], s['rpe'], s['ts'], s['backoff']) for s in movement['sets']],
                         [(3, 8, True, False)] + [(5, 7, False, True)] * 3)

    def test_comma_inside_rpe_list_does_not_start_a_group(self):
        _, movement = only_movement('#Squat (Barbell) 3x3@6, 7, 8, 2x5@6')
        self.assertEqual([(s['reps'], s['rpe']) for s in movement['sets']], [(3, 6), (3, 7), (3, 8), (5, 6), (5, 6)])

    def test_amrap_marks_the_last_set_only(self):
        _, movement = only_movement('#Squat (Barbell) 3x5+@8')
        self.assertEqual([s['amrap'] for s in movement['sets']], [False, False, True])

    def test_drop_sets_with_and_without_a_count(self):
        _, open_drops = only_movement('#Bench Press (Barbell) 3x10@9 DS')
        self.assertEqual([(s['drops'], s['drops_open']) for s in open_drops['sets']], [(None, False)] * 2 + [(None, True)])
        _, counted = only_movement('#Bench Press (Barbell) 3x10@9 DS2')
        self.assertEqual((counted['sets'][-1]['drops'], counted['sets'][-1]['drops_open']), (2, False))

    def test_myo_reps_have_a_target_and_rpe_only(self):
        result, movement = only_movement('#Lateral Raise (Dumbbell) myo 15-20@9')
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(movement['sets']), 1)
        one = movement['sets'][0]
        self.assertEqual((one['reps'], one['reps_max'], one['rpe'], one['myo']), (15, 20, 9, True))

    def test_training_max_belongs_to_the_movement(self):
        _, movement = only_movement('#Deadlift (Barbell) 1x3@8 TS, 3x5@7 BO TM90')
        self.assertEqual(movement['tm_pct'], 90)

    def test_effort_labels_are_accepted_and_ignored(self):
        result, movement = only_movement('#Squat (Barbell) ME 3x3@8 RE')
        self.assertEqual(result['errors'], [])
        self.assertEqual(movement['exercise_template_id'], 'sq')
        self.assertEqual(set(movement['sets'][0]), {'reps', 'reps_max', 'rpe', 'ts', 'amrap', 'backoff', 'ddp', 'myo', 'drops', 'drops_open'})

    def test_names_with_numbers_and_commas(self):
        result, movement = only_movement('#3-board press 3x5@8')
        self.assertEqual((result['errors'], movement['exercise_template_id']), ([], 'board'))

    def test_weeks_and_days_are_ordered_by_number(self):
        result = read('Week 2 Day 2\n#Squat (Barbell) 3x5\nWeek 1 Day 1\n#Squat (Barbell) 3x5\nWeek 2 Day 1\n#Deadlift (Barbell) 1x5')
        self.assertEqual([(w['week'], [d['day'] for d in w['days']]) for w in result['weeks']], [(1, [1]), (2, [1, 2])])


class Matching(unittest.TestCase):
    def test_close_names_are_never_guessed(self):
        result, movement = only_movement('#bench press 5x4@6')
        self.assertFalse(result['ready'])
        self.assertEqual((movement['status'], movement['exercise_template_id']), ('unresolved', None))
        self.assertEqual({c['id'] for c in movement['choices']}, {'bench', 'bench-db'})
        self.assertEqual(result['unresolved'], ['bench press'])

    def test_a_choice_resolves_every_use_of_that_name(self):
        result = read('Week 1 Day 1\n#bench press 5x4\nWeek 1 Day 2\n#Bench  PRESS 3x8', {'bench press': 'bench'})
        self.assertTrue(result['ready'], result)
        self.assertEqual([d['exercises'][0]['exercise_template_id'] for d in result['weeks'][0]['days']], ['bench', 'bench'])

    def test_a_choice_of_an_unknown_id_is_ignored(self):
        result, movement = only_movement('#bench press 5x4', {'bench press': 'nope'})
        self.assertEqual(movement['status'], 'unresolved')

    def test_two_movements_with_the_same_name_ask(self):
        _, movement = only_movement('#pull up 3x8')
        self.assertEqual(movement['status'], 'ambiguous')
        self.assertEqual({c['id'] for c in movement['choices']}, {'dup-a', 'dup-b'})

    def test_longest_exact_name_wins(self):
        titles = {'a': 'Squat', 'b': 'Squat 2 count pause'}
        result = parse_week_text('Week 1 Day 1\n#squat 2 count pause 3x3', titles)
        self.assertEqual(result['weeks'][0]['days'][0]['exercises'][0]['exercise_template_id'], 'b')


class Problems(unittest.TestCase):
    def assertProblem(self, text, line, fragment):
        result = read(text)
        self.assertFalse(result['ready'])
        self.assertTrue(any(l == line and fragment in m for l, m in messages(result)), messages(result))

    def test_asterisk_is_reported_not_dropped(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 5x6*', 2, 'The * has no meaning here')

    def test_unknown_callout(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x5 XYZ', 2, 'Unknown callout "XYZ"')

    def test_rep_ranges_wait_for_later(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x5-8', 2, 'Rep ranges')

    def test_rpe_count_must_match_sets(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x3@6,7', 2, '3 sets but 2 RPE values')

    def test_rpe_range_and_steps(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x3@11', 2, 'between 4 and 10')
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x3@7.3', 2, 'half steps')

    def test_ts_must_be_one_set_and_one_per_movement(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x3@8 TS', 2, 'TS marks one set')
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 1x3@8 TS, 1x2@9 TS', 2, 'Only one TS')

    def test_tm_needs_a_sensible_percentage(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x5 TM', 2, 'TM needs a percentage')
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x5 TM120', 2, 'between 50 and 100')
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 1x3 TS TM90, 3x5 BO TM85', 2, 'Two different TM')

    def test_myo_rejects_other_callouts(self):
        self.assertProblem('Week 1 Day 1\n#Lateral Raise (Dumbbell) myo 15-20@9 DDP', 2, 'Myo-reps take only')

    def test_movement_needs_a_day_and_sets(self):
        self.assertProblem('#Squat (Barbell) 3x5', 1, 'Start with a "Week N Day N"')
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell)', 2, 'No sets found')

    def test_other_lines_and_bad_headings(self):
        self.assertProblem('Week 1 Day 1\nSquat 3x5', 2, 'Expected "Week N Day N"')
        self.assertProblem('Week one\n#Squat (Barbell) 3x5', 1, 'Write a day heading')

    def test_repeated_and_empty_days(self):
        self.assertProblem('Week 1 Day 1\n#Squat (Barbell) 3x5\nWeek 1 Day 1\n#Squat (Barbell) 3x5', 3, 'already started on line 1')
        self.assertProblem('Week 1 Day 1\nWeek 1 Day 2\n#Squat (Barbell) 3x5', 1, 'has no movements')

    def test_empty_text(self):
        self.assertProblem('   \n', 0, 'Nothing to read yet')

    def test_every_problem_is_listed_not_just_the_first(self):
        result = read('Week 1 Day 1\n#Squat (Barbell) 5x6*\n#Deadlift (Barbell) 3x5 XYZ\n#Squat (Barbell) 3x5')
        self.assertEqual([line for line, _ in messages(result)], [2, 3])
        self.assertEqual(len(result['weeks'][0]['days'][0]['exercises']), 3)


class Sessions(unittest.TestCase):
    def test_builder_sessions_keep_callouts_and_blank_weights(self):
        result = read('Week 4 Day 1\n#Squat (Barbell) 1x3@8 TS, 2x5@7 BO TM90\nWeek 4 Day 2\n#Lateral Raise (Dumbbell) myo 15-20@9')
        ids = iter(['s1', 's2'])
        sessions = plan_sessions(result['weeks'][0], lambda: next(ids))
        self.assertEqual([(s['id'], s['name']) for s in sessions], [('s1', 'Day 1'), ('s2', 'Day 2')])
        squat = sessions[0]['exercises'][0]
        self.assertEqual((squat['exercise_template_id'], squat['title'], squat['tm_pct']), ('sq', 'Squat (Barbell)', 90))
        self.assertTrue(all(s['weight_kg'] is None and s['type'] == 'normal' for s in squat['sets']))
        self.assertTrue(sessions[1]['exercises'][0]['sets'][0]['myo'])


if __name__ == '__main__':
    unittest.main()
