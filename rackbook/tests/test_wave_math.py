"""Characterisation tests for wave_math — pins current behaviour before the notation refactor."""
import os
import sys
import unittest

from rackbook.wave_math import (
    bbb_weight,
    epley,
    joker_qualifies,
    joker_weight,
    round_weight,
    session_e1rm,
    working_weight,
)


class TestRounding(unittest.TestCase):

    def test_rounds_to_nearest_2_5(self):
        self.assertEqual(102.5, round_weight(101.3))
        self.assertEqual(100.0, round_weight(100.9))

    def test_exact_midpoint_uses_bankers_rounding(self):
        # Python round() rounds halves to even: 101.25/2.5 = 40.5 -> 40 -> 100.0.
        # Quirk of the current implementation; pinned so a change is deliberate.
        self.assertEqual(100.0, round_weight(101.25))
        self.assertEqual(105.0, round_weight(103.75))


class TestEpley(unittest.TestCase):

    def test_single_rep_is_the_weight(self):
        self.assertEqual(100.0, epley(100.0, 1))

    def test_multi_rep(self):
        self.assertAlmostEqual(116.6667, epley(100.0, 5), places=3)
        self.assertAlmostEqual(130.0, epley(100.0, 9), places=6)


class TestJoker(unittest.TestCase):

    def test_band_is_inclusive_at_5_percent(self):
        self.assertTrue(joker_qualifies(105.0, 100.0))
        self.assertTrue(joker_qualifies(95.0, 100.0))
        self.assertFalse(joker_qualifies(105.1, 100.0))

    def test_joker_weight_steps_and_rounds(self):
        self.assertEqual(172.5, joker_weight(157.5, 0.10))
        self.assertEqual(197.5, joker_weight(172.5, 0.15))

    def test_session_e1rm_without_jokers_is_the_amrap(self):
        self.assertEqual(116.0, session_e1rm(116.0, []))

    def test_session_e1rm_averages_qualifying_jokers_only(self):
        # amrap 100; joker 1x102 qualifies (2%); joker 1x120 does not (20%).
        self.assertAlmostEqual(101.0, session_e1rm(100.0, [(102.0, 1), (120.0, 1)]))


class TestWaveWeights(unittest.TestCase):

    def test_working_weight_uses_week_index(self):
        wp = {"percentages": [0.75, 0.80, 0.85]}
        self.assertEqual(135.0, working_weight(180.0, 1, wp))
        self.assertEqual(145.0, working_weight(180.0, 2, wp))
        self.assertEqual(152.5, working_weight(180.0, 3, wp))

    def test_bbb_weight_uses_week_index(self):
        wp = {"bbb_percentages": [0.65, 0.70, 0.75]}
        self.assertEqual(117.5, bbb_weight(180.0, 1, wp))
        self.assertEqual(125.0, bbb_weight(180.0, 2, wp))


if __name__ == "__main__":
    unittest.main()
