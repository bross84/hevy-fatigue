"""Lossless encoding, including repeated sets and marker-shaped user data."""
from copy import deepcopy
from unittest import TestCase

import coaching
import coaching_compact


class CompactTests(TestCase):
    def test_short_movement_ids_and_titles_are_shared_without_merging_sets(self):
        rows = [dict(exercise_template_id='sq', title='Squat', reps=5) for _ in range(3)]
        packed = coaching_compact.pack(rows)
        self.assertEqual(packed['shared'].count('sq'), 1)
        self.assertEqual(packed['shared'].count('Squat'), 1)
        self.assertEqual(coaching_compact.unpack(packed), rows)

    def test_round_trip_preserves_values_order_missing_keys_and_literal_markers(self):
        original = dict(plan={'notes': 'Long notes with Unicode — ' * 200}, sets=[
            dict(weight_kg=102.512345, reps=5, rpe=3.5, target_rpe=8, type='warmup'),
            dict(weight_kg=102.512345, reps=5, rpe=3.5, target_rpe=8, type='warmup'),
            dict(weight_kg=None, reps=None, rpe=None),
            {'$ref': 100, '$table': {'columns': ['fake']}, '$literal': 'user note'},
        ])
        original['prescription'] = deepcopy(original['plan'])
        before = deepcopy(original)
        packed = coaching_compact.pack(original)
        self.assertEqual(coaching_compact.unpack(packed), original)
        self.assertEqual(original, before)
        self.assertLess(len(coaching.encode(packed)), len(coaching.encode(original)))

    def test_shared_chart_and_column_tables_preserve_every_cell(self):
        chart = [dict(rpe=rpe / 2, reps=reps, percentage=1 / (1 + reps / 30))
                 for rpe in range(8, 21) for reps in range(1, 61)]
        source = [dict(name=f'Day {day}', chart=chart, sets=[dict(reps=5, rpe=7)] * 5)
                  for day in range(3)]
        packed = coaching_compact.pack(source)
        self.assertEqual(coaching_compact.unpack(packed), source)
        charts = [item for item in packed['shared'] if isinstance(item, dict)
                  and item.get('$table', {}).get('columns') == ['rpe', 'reps', 'percentage']]
        self.assertEqual(len(charts), 1)
        self.assertLess(len(coaching.encode(packed)), len(coaching.encode(source)) / 3)
