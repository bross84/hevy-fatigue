"""Tests for strength_score: DOTS multiplier, bodyweight smoothing, weight lookup."""
import os
import sys
import unittest

from rackbook.strength_score import dots_coefficient, dots_score, smooth_body_weight, weight_on  # noqa: E402


class DotsTest(unittest.TestCase):
    def test_known_values(self):
        # Hand-computed from the formula: 500 / 725.11 at 80 kg male, 500 / 451.04 at 60 kg female.
        self.assertAlmostEqual(dots_coefficient(80, "male"), 0.6895, places=3)
        self.assertAlmostEqual(dots_coefficient(60, "female"), 1.1085, places=3)

    def test_lighter_lifter_gets_a_bigger_multiplier(self):
        self.assertGreater(dots_coefficient(76.9), dots_coefficient(90.7))

    def test_the_cut_example(self):
        # 315x5 at 200 lb vs 225x5 at 169 lb, Epley e1RM, in kg.
        old = dots_score(315 * (1 + 5 / 30) * 0.45359237, 200 * 0.45359237)
        new = dots_score(225 * (1 + 5 / 30) * 0.45359237, 169 * 0.45359237)
        self.assertGreater(old, new)  # still weaker in absolute terms and in score...
        self.assertGreater(new / old, 262.5 / 367.5)  # ...but the score gap is smaller than the raw-load gap

    def test_score_is_lift_times_coefficient(self):
        self.assertAlmostEqual(dots_score(100, 80), 100 * dots_coefficient(80))

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            dots_coefficient(0)
        with self.assertRaises(ValueError):
            dots_coefficient(-5)
        with self.assertRaises(ValueError):
            dots_coefficient(80, "other")


class SmoothBodyWeightTest(unittest.TestCase):
    def test_trailing_average_over_seven_days(self):
        rows = [{"date": f"2026-10-{d:02d}", "weight_kg": float(w)} for d, w in zip(range(1, 9), [80, 80, 80, 80, 80, 80, 80, 87])]
        out = smooth_body_weight(rows)
        self.assertEqual(out[0]["weight_kg"], 80)  # first day: only itself
        # Oct 8 window is Oct 2..8: six 80s and one 87.
        self.assertAlmostEqual(out[7]["weight_kg"], (6 * 80 + 87) / 7)

    def test_gaps_are_not_counted_as_zero(self):
        rows = [{"date": "2026-10-01", "weight_kg": 80.0}, {"date": "2026-10-05", "weight_kg": 78.0}]
        out = smooth_body_weight(rows)
        self.assertAlmostEqual(out[1]["weight_kg"], 79.0)

    def test_old_readings_fall_out_of_the_window(self):
        rows = [{"date": "2026-10-01", "weight_kg": 90.0}, {"date": "2026-10-20", "weight_kg": 80.0}]
        self.assertEqual(smooth_body_weight(rows)[1]["weight_kg"], 80.0)

    def test_unsorted_input_comes_back_oldest_first(self):
        rows = [{"date": "2026-10-02", "weight_kg": 78.0}, {"date": "2026-10-01", "weight_kg": 80.0}]
        self.assertEqual([r["date"] for r in smooth_body_weight(rows)], ["2026-10-01", "2026-10-02"])

    def test_empty(self):
        self.assertEqual(smooth_body_weight([]), [])


class WeightOnTest(unittest.TestCase):
    SMOOTHED = [{"date": "2026-10-01", "weight_kg": 80.0}, {"date": "2026-10-05", "weight_kg": 78.0}]

    def test_exact_day(self):
        self.assertEqual(weight_on(self.SMOOTHED, "2026-10-05"), 78.0)

    def test_falls_back_to_latest_earlier_reading(self):
        self.assertEqual(weight_on(self.SMOOTHED, "2026-10-03"), 80.0)
        self.assertEqual(weight_on(self.SMOOTHED, "2026-10-19"), 78.0)  # 14 days after the last reading

    def test_a_stale_reading_is_not_used(self):
        self.assertIsNone(weight_on(self.SMOOTHED, "2026-10-20"))  # 15 days after the last reading
        self.assertEqual(weight_on(self.SMOOTHED, "2026-10-20", max_age_days=30), 78.0)

    def test_none_before_first_reading(self):
        self.assertIsNone(weight_on(self.SMOOTHED, "2026-09-30"))


if __name__ == "__main__":
    unittest.main()
