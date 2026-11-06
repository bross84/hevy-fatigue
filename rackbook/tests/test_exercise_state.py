"""Tests for exercise_state — a movement's e1RM from its last session, using the user's RPE table."""
import csv
import os
import sys
import unittest

from rackbook.exercise_state import build_exercise_state, e1rm_lb, reference_set, sessions_newest_first, weight_lb

USER_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "rpe_chart_user.csv")
with open(USER_CSV, newline="", encoding="utf-8") as f:
    _TABLE = {(float(r["rpe"]), int(r["reps"])): float(r["percentage"]) for r in csv.DictReader(f)}


def pct(rpe, reps):
    return _TABLE.get((float(rpe), int(reps)))


def S(workout, start, set_type, lb, reps, rpe, title="Day"):
    """One per-set history entry, weight given in lb the way the user typed it (stored as kg by Hevy)."""
    return {
        "workout_id": workout, "workout_title": title, "workout_start_time": start,
        "set_type": set_type, "weight_kg": None if lb is None else lb / 2.20462, "reps": reps, "rpe": rpe,
    }


# The user's real low-bar squat sessions (lb typed), newest first as Hevy returns them.
SQUAT = [
    S("w3", "2026-09-30T17:00:00+00:00", "warmup", 110, 5, None, "BS-Bridge1.3.1"),
    S("w3", "2026-09-30T17:00:00+00:00", "normal", 265, 5, 6, "BS-Bridge1.3.1"),
    S("w3", "2026-09-30T17:00:00+00:00", "normal", 281, 5, 7, "BS-Bridge1.3.1"),
    S("w3", "2026-09-30T17:00:00+00:00", "normal", 292, 5, 8, "BS-Bridge1.3.1"),
    S("w2", "2026-09-19T17:00:00+00:00", "normal", 265, 5, 6, "BS-Bridge1.2.3"),
    S("w2", "2026-09-19T17:00:00+00:00", "normal", 292, 3, 8, "BS-Bridge1.2.3"),
    S("w2", "2026-09-19T17:00:00+00:00", "normal", 198, 8, 6, "BS-Bridge1.2.3"),
]


class TestConversions(unittest.TestCase):

    def test_weight_comes_back_to_the_lb_the_user_typed(self):
        self.assertEqual(265, weight_lb(120.2))
        self.assertEqual(281, weight_lb(127.46))
        self.assertEqual(94, weight_lb(42.64))

    def test_e1rm_is_weight_over_the_table_percentage(self):
        self.assertAlmostEqual(265 / 0.773, e1rm_lb(265, 5, 6, pct), places=6)
        self.assertEqual(343, round(e1rm_lb(265, 5, 6, pct)))   # the user's spreadsheet shows 343 for this set
        self.assertIsNone(e1rm_lb(100, 28, 5, pct))              # outside the table


class TestSessions(unittest.TestCase):

    def test_newest_first_even_if_input_is_shuffled(self):
        shuffled = [SQUAT[5], SQUAT[1], SQUAT[4], SQUAT[2]]
        order = [s[0]["workout_id"] for s in sessions_newest_first(shuffled)]
        self.assertEqual(["w3", "w2"], order)

    def test_set_order_inside_a_session_is_kept(self):
        session = sessions_newest_first(SQUAT)[0]
        self.assertEqual([110, 265, 281, 292], [weight_lb(s["weight_kg"]) for s in session])


class TestReferenceSet(unittest.TestCase):

    def test_the_set_with_the_highest_e1rm(self):
        ref = reference_set(sessions_newest_first(SQUAT)[0], pct)
        self.assertEqual((292, 5, 8.0), (ref["weight_lb"], ref["reps"], ref["rpe"]))

    def test_a_lighter_set_wins_when_its_e1rm_is_higher(self):
        # 292 x 3 @8 is the heaviest set (e1RM 332) but 265 x 5 @6 prices higher (343).
        ref = reference_set(sessions_newest_first(SQUAT)[1], pct)
        self.assertEqual((265, 5, 6.0), (ref["weight_lb"], ref["reps"], ref["rpe"]))

    def test_warmups_and_sets_without_rpe_are_ignored(self):
        session = [S("w", "2026-01-01T00:00:00+00:00", "warmup", 300, 5, 8),
                   S("w", "2026-01-01T00:00:00+00:00", "normal", 250, 5, None),
                   S("w", "2026-01-01T00:00:00+00:00", "normal", 200, 5, 7)]
        self.assertEqual(200, reference_set(session, pct)["weight_lb"])

    def test_a_tie_on_e1rm_goes_to_the_later_set(self):
        session = [S("w", "2026-01-01T00:00:00+00:00", "normal", 200, 5, 7),
                   S("w", "2026-01-01T00:00:00+00:00", "failure", 200, 5, 7)]
        self.assertEqual("failure", reference_set(session, pct)["entry"]["set_type"])

    def test_a_set_the_table_cannot_price_is_skipped(self):
        session = [S("w", "2026-01-01T00:00:00+00:00", "normal", 300, 28, 5),
                   S("w", "2026-01-01T00:00:00+00:00", "normal", 200, 5, 7)]
        self.assertEqual(200, reference_set(session, pct)["weight_lb"])

    def test_no_usable_set(self):
        self.assertIsNone(reference_set([S("w", "2026-01-01T00:00:00+00:00", "warmup", 100, 5, None)], pct))


class TestBuildExerciseState(unittest.TestCase):

    def test_uses_the_newest_session_and_reports_which_set(self):
        state = build_exercise_state(SQUAT, pct)
        self.assertTrue(state["found"])
        self.assertEqual("BS-Bridge1.3.1", state["workout_title"])
        self.assertEqual((292, 5, 8.0), (state["set_weight_lb"], state["set_reps"], state["set_rpe"]))
        self.assertEqual(round(292 / 0.826, 1), state["e1rm_lb"])

    def test_reports_the_best_set_not_the_heaviest(self):
        state = build_exercise_state([s for s in SQUAT if s["workout_id"] == "w2"], pct)
        self.assertEqual((265, 5, 6.0), (state["set_weight_lb"], state["set_reps"], state["set_rpe"]))
        self.assertEqual(round(265 / 0.773, 1), state["e1rm_lb"])

    def test_falls_back_to_an_older_session_when_the_newest_has_no_rpe_sets(self):
        newest = [S("w9", "2026-10-07T00:00:00+00:00", "normal", 100, 10, None, "Accessory day")]
        state = build_exercise_state(newest + SQUAT, pct)
        self.assertEqual("BS-Bridge1.3.1", state["workout_title"])

    def test_no_history(self):
        self.assertEqual({"found": False}, {"found": build_exercise_state([], pct)["found"]})
        self.assertIsNone(build_exercise_state([], pct)["e1rm_lb"])


class TestPreviousSets(unittest.TestCase):
    """The Previous column: what you did on each set the last time you did the movement."""

    def _plain(self, state):
        return [(p["type"], p["weight_lb"], p["reps"], p["rpe"]) for p in state["previous"]]

    def test_the_newest_sessions_sets_in_order_with_their_type(self):
        state = build_exercise_state(SQUAT, pct)
        self.assertEqual(
            [("warmup", 110, 5, None), ("normal", 265, 5, 6.0), ("normal", 281, 5, 7.0), ("normal", 292, 5, 8.0)],
            self._plain(state),
        )

    def test_a_newest_session_without_rpes_is_still_the_previous_one(self):
        newest = [S("w9", "2026-10-07T00:00:00+00:00", "normal", 100, 10, None, "Accessory day")]
        state = build_exercise_state(newest + SQUAT, pct)
        self.assertEqual([("normal", 100, 10, None)], self._plain(state))
        self.assertEqual("BS-Bridge1.3.1", state["workout_title"])   # the e1RM still comes from the session that has RPEs

    def test_no_history_means_nothing_previous(self):
        self.assertEqual([], build_exercise_state([], pct)["previous"])


if __name__ == "__main__":
    unittest.main()
