"""Pure, fixed-clock coverage; historical evidence is never deleted."""
from datetime import datetime, timedelta, timezone
import unittest
from rackbook.exercise_state import build_exercise_state


class ReferenceRecencyTests(unittest.TestCase):
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)

    def row(self, days, rpe=8):
        return dict(workout_id=str(days), workout_start_time=(self.now-timedelta(days=days)).isoformat(),
                    weight_kg=100, reps=2, rpe=rpe, set_type='normal')

    def state(self, rows):
        return build_exercise_state(rows, lambda rpe, reps: .9, as_of=self.now)

    def test_boundary_and_stale_history_still_visible(self):
        self.assertTrue(self.state([self.row(90)])['found'])
        stale = self.state([self.row(90.0001)])
        self.assertFalse(stale['found'])
        self.assertEqual(stale['previous'][0]['weight_kg'], 100)

    def test_missing_recent_rpe_does_not_revive_stale_reference(self):
        self.assertFalse(self.state([self.row(1, None), self.row(91)])['found'])
        self.assertTrue(self.state([self.row(1, None), self.row(89)])['found'])

    def test_invalid_missing_and_future_dates_are_ineligible(self):
        for stamp in (None, '', 'invalid', (self.now+timedelta(days=1)).isoformat()):
            row = self.row(1)
            row['workout_start_time'] = stamp
            self.assertFalse(self.state([row])['found'])

    def test_analytical_history_without_cutoff_is_preserved(self):
        self.assertTrue(build_exercise_state([self.row(365)], lambda r, n: .9)['found'])
