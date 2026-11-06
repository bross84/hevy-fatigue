"""Tests for program_parser.parse_program() — three-level block.microcycle.day notation."""
import sys
import os
import unittest

from rackbook.program_parser import parse_program


def _first_slot(result):
    return result["blocks"][0]["microcycles"][0]["days"][0]["slots"][0]


class TestHeaderParsing(unittest.TestCase):

    def test_three_level_header_nesting(self):
        result = parse_program("1.1.1 Squat - 3x5")
        self.assertEqual([], result["errors"])
        self.assertEqual(1, len(result["blocks"]))
        block = result["blocks"][0]
        self.assertEqual(1, block["block_number"])
        self.assertEqual(1, len(block["microcycles"]))
        mc = block["microcycles"][0]
        self.assertEqual(1, mc["cycle_number"])
        self.assertEqual(1, len(mc["days"]))
        day = mc["days"][0]
        self.assertEqual(1, day["day_number"])
        self.assertEqual(1, len(day["slots"]))
        self.assertEqual("Squat", day["slots"][0]["exercise_name"])

    def test_continuation_line_inherits_context(self):
        result = parse_program("1.1.1 Squat - 3x5\nBench Press - 3x5")
        self.assertEqual([], result["errors"])
        slots = result["blocks"][0]["microcycles"][0]["days"][0]["slots"]
        self.assertEqual(2, len(slots))
        self.assertEqual("Bench Press", slots[1]["exercise_name"])

    def test_line_without_context_errors(self):
        result = parse_program("Squat - 3x5")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(1, result["errors"][0]["line"])

    def test_missing_separator_errors(self):
        result = parse_program("1.1.1 Squat 3x5")
        self.assertGreater(len(result["errors"]), 0)

    def test_multiple_blocks(self):
        text = "1.1.1 Squat - 3x5\n2.1.1 Deadlift - 3x5"
        result = parse_program(text)
        self.assertEqual([], result["errors"])
        self.assertEqual(2, len(result["blocks"]))
        self.assertEqual(1, result["blocks"][0]["block_number"])
        self.assertEqual(2, result["blocks"][1]["block_number"])

    def test_multiple_microcycles_within_block(self):
        text = "1.1.1 Squat - 3x5\n1.2.1 Deadlift - 3x5"
        result = parse_program(text)
        self.assertEqual([], result["errors"])
        self.assertEqual(1, len(result["blocks"]))
        self.assertEqual(2, len(result["blocks"][0]["microcycles"]))

    def test_multiple_days_within_microcycle(self):
        text = "1.1.1 Squat - 3x5\n1.1.2 Deadlift - 3x5"
        result = parse_program(text)
        self.assertEqual([], result["errors"])
        days = result["blocks"][0]["microcycles"][0]["days"]
        self.assertEqual(2, len(days))
        self.assertEqual(1, days[0]["day_number"])
        self.assertEqual(2, days[1]["day_number"])

    def test_header_only_line_no_error(self):
        # A standalone header line (no exercise) followed by exercises on next lines
        result = parse_program("1.1.1\nSquat - 3x5")
        self.assertEqual([], result["errors"])
        self.assertEqual("Squat", _first_slot(result)["exercise_name"])


class TestSetPatterns(unittest.TestCase):

    def test_rpe_list_with_amrap(self):
        result = parse_program("1.1.1 Squat - 5@5,6,7+")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(3, len(sets))
        self.assertAlmostEqual(5.0, sets[0]["target_rpe"])
        self.assertAlmostEqual(6.0, sets[1]["target_rpe"])
        self.assertAlmostEqual(7.0, sets[2]["target_rpe"])
        self.assertFalse(sets[0]["is_amrap"])
        self.assertFalse(sets[1]["is_amrap"])
        self.assertTrue(sets[2]["is_amrap"])

    def test_rpe_list_without_amrap(self):
        result = parse_program("1.1.1 Squat - 5@5,6,7")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(3, len(sets))
        self.assertFalse(sets[0]["is_amrap"])
        self.assertFalse(sets[1]["is_amrap"])
        self.assertFalse(sets[2]["is_amrap"])

    def test_joker_sets(self):
        result = parse_program("1.1.1 Squat - 3x1J +10,15,20")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(3, len(sets))
        self.assertTrue(all(s["is_joker"] for s in sets))
        self.assertAlmostEqual(0.10, sets[0]["joker_jump_pct"])
        self.assertAlmostEqual(0.15, sets[1]["joker_jump_pct"])
        self.assertAlmostEqual(0.20, sets[2]["joker_jump_pct"])

    def test_nx_free_with_ddp(self):
        result = parse_program("1.1.1 Bench - 4x10 DDP")
        self.assertEqual([], result["errors"])
        slot = _first_slot(result)
        self.assertEqual(4, len(slot["sets"]))
        self.assertEqual(10, slot["sets"][0]["reps"])
        self.assertIsNone(slot["sets"][0]["target_rpe"])
        self.assertEqual("ddp", slot["source_params"]["source"])
        self.assertAlmostEqual(2.5, slot["source_params"]["increment_kg"])

    def test_nx_free_with_ddp_plus(self):
        result = parse_program("1.1.1 Bench - 4x10 DDP+5")
        self.assertEqual([], result["errors"])
        sp = _first_slot(result)["source_params"]
        self.assertEqual("ddp", sp["source"])
        self.assertAlmostEqual(5.0, sp["increment_kg"])

    def test_bbb(self):
        result = parse_program("1.1.1 Bench - 5x10 @.65 e1RM")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(5, len(sets))
        self.assertAlmostEqual(0.65, sets[0]["bbb_pct"])
        self.assertEqual("e1rm", _first_slot(result)["source_params"]["source"])

    def test_nx_rpe_with_e1rm(self):
        result = parse_program("1.1.1 Deadlift - 4x8 e1RM")
        self.assertEqual([], result["errors"])
        slot = _first_slot(result)
        self.assertEqual(4, len(slot["sets"]))
        self.assertEqual(8, slot["sets"][0]["reps"])
        self.assertEqual("e1rm", slot["source_params"]["source"])

    def test_nx_free_with_tm(self):
        result = parse_program("1.1.1 Squat - 5x10 TM90")
        self.assertEqual([], result["errors"])
        sp = _first_slot(result)["source_params"]
        self.assertEqual("tm", sp["source"])
        self.assertAlmostEqual(0.90, sp["wm_pct"])

    def test_source_free_default(self):
        result = parse_program("1.1.1 Curl - 3x12")
        self.assertEqual([], result["errors"])
        sp = _first_slot(result)["source_params"]
        self.assertEqual("free", sp["source"])

    def test_nx_rpe_last_set_amrap(self):
        result = parse_program("1.1.1 Squat - 3x5@7+")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(3, len(sets))
        self.assertFalse(sets[0]["is_amrap"])
        self.assertFalse(sets[1]["is_amrap"])
        self.assertTrue(sets[2]["is_amrap"])

    def test_nx_rpe_no_amrap(self):
        result = parse_program("1.1.1 Squat - 3x5@7")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertFalse(any(s["is_amrap"] for s in sets))

    def test_slash_groups(self):
        result = parse_program("1.1.1 Squat - 5@5,6,7+ TM90 / 3x1J +10,15,20")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(6, len(sets))
        self.assertFalse(sets[0]["is_joker"])
        self.assertTrue(sets[3]["is_joker"])


class TestSlotTargetRpe(unittest.TestCase):

    def test_slot_target_rpe_is_max_working(self):
        result = parse_program("1.1.1 Squat - 5@5,6,8+")
        slot = _first_slot(result)
        self.assertAlmostEqual(8.0, slot["target_rpe"])

    def test_slot_target_rpe_none_for_free_sets(self):
        result = parse_program("1.1.1 Curl - 4x10")
        slot = _first_slot(result)
        self.assertIsNone(slot["target_rpe"])

    def test_jokers_excluded_from_slot_rpe(self):
        result = parse_program("1.1.1 Squat - 5@7+ / 3x1J +10,15,20")
        slot = _first_slot(result)
        self.assertAlmostEqual(7.0, slot["target_rpe"])


class TestSlotOrder(unittest.TestCase):

    def test_slot_order_increments(self):
        result = parse_program("1.1.1 Squat - 3x5\nBench - 3x5\nCurl - 3x12")
        slots = result["blocks"][0]["microcycles"][0]["days"][0]["slots"]
        self.assertEqual([0, 1, 2], [s["slot_order"] for s in slots])


class TestIgnoredLines(unittest.TestCase):

    def test_blank_lines_ignored(self):
        result = parse_program("1.1.1 Squat - 3x5\n\n\nBench - 3x5")
        self.assertEqual([], result["errors"])
        slots = result["blocks"][0]["microcycles"][0]["days"][0]["slots"]
        self.assertEqual(2, len(slots))

    def test_comment_lines_ignored(self):
        result = parse_program("# This is a comment\n1.1.1 Squat - 3x5\n# another comment\nBench - 3x5")
        self.assertEqual([], result["errors"])
        slots = result["blocks"][0]["microcycles"][0]["days"][0]["slots"]
        self.assertEqual(2, len(slots))

    def test_empty_text(self):
        result = parse_program("")
        self.assertEqual([], result["errors"])
        self.assertEqual([], result["blocks"])


class TestErrors(unittest.TestCase):

    def test_invalid_line_returns_error_with_line_number(self):
        result = parse_program("1.1.1 Squat - ???")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(1, result["errors"][0]["line"])

    def test_invalid_line_mid_program(self):
        result = parse_program("1.1.1 Squat - 3x5\n1.1.2 Bench - ???")
        self.assertGreater(len(result["errors"]), 0)
        self.assertEqual(2, result["errors"][0]["line"])

    def test_no_context_error(self):
        result = parse_program("Squat - 3x5")
        self.assertGreater(len(result["errors"]), 0)

    def test_case_insensitive_source_tag(self):
        result = parse_program("1.1.1 Squat - 3x5 tm90")
        self.assertEqual([], result["errors"])
        sp = _first_slot(result)["source_params"]
        self.assertEqual("tm", sp["source"])


class TestWaveSets(unittest.TestCase):

    def test_wave_sets_per_set_reps_and_rpe(self):
        result = parse_program("1.1.1 Squat - 5@5,3@6,1@7 TM90")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual([5, 3, 1], [s["reps"] for s in sets])
        self.assertEqual([5.0, 6.0, 7.0], [s["target_rpe"] for s in sets])
        self.assertFalse(any(s["is_amrap"] for s in sets))

    def test_wave_sets_trailing_plus_marks_last_amrap(self):
        result = parse_program("1.1.1 Squat - 5@5,3@6,1@7+ TM90")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual([False, False, True], [s["is_amrap"] for s in sets])
        self.assertEqual("tm", _first_slot(result)["source_params"]["source"])

    def test_wave_sets_do_not_swallow_rpe_list(self):
        # 5@5,6,7+ is the shared-reps RPE list form, not wave sets
        sets = _first_slot(parse_program("1.1.1 Squat - 5@5,6,7+"))["sets"]
        self.assertEqual([5, 5, 5], [s["reps"] for s in sets])
        self.assertEqual([5.0, 6.0, 7.0], [s["target_rpe"] for s in sets])

    def test_wave_sets_mixed_with_other_group(self):
        result = parse_program("1.1.1 Squat - 5@5,3@6,1@7+ / 3x1J +10,15,20 TM90")
        self.assertEqual([], result["errors"])
        sets = _first_slot(result)["sets"]
        self.assertEqual(6, len(sets))
        self.assertTrue(sets[2]["is_amrap"])
        self.assertTrue(all(s["is_joker"] for s in sets[3:]))


class TestExerciseNamesWithSeparator(unittest.TestCase):

    def test_hyphen_spaced_name_splits_on_last_separator(self):
        result = parse_program("1.1.1 Curl - Barbell - 3x10")
        self.assertEqual([], result["errors"])
        slot = _first_slot(result)
        self.assertEqual("Curl - Barbell", slot["exercise_name"])
        self.assertEqual(3, len(slot["sets"]))


if __name__ == "__main__":
    unittest.main()
