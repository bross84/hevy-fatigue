"""Tests for workout_view.summarize_workout — raw Hevy workout -> display shape."""
import os
import sys
import unittest

from rackbook.workout_view import summarize_set, summarize_workout


def _workout(**overrides):
    base = {
        "id": "w1",
        "title": "Day 1",
        "description": None,
        "start_time": "2026-09-30T17:00:00+00:00",
        "end_time": "2026-09-30T17:58:00+00:00",
        "exercises": [
            {
                "index": 0,
                "title": "Squat (Barbell)",
                "notes": "",
                "exercise_template_id": "tpl-squat",
                "sets": [
                    {"index": 0, "type": "warmup", "weight_kg": 60, "reps": 5, "rpe": None},
                    {"index": 1, "type": "normal", "weight_kg": 120, "reps": 5, "rpe": 6},
                    {"index": 2, "type": "normal", "weight_kg": 127.5, "reps": 5, "rpe": 7},
                ],
            }
        ],
    }
    base.update(overrides)
    return base


class TestSummarizeSet(unittest.TestCase):

    def test_adds_lb_rounded_to_one_decimal(self):
        s = summarize_set({"index": 1, "type": "normal", "weight_kg": 132.5, "reps": 5, "rpe": 8})
        self.assertEqual(132.5, s["weight_kg"])
        self.assertEqual(292.1, s["weight_lb"])
        self.assertEqual((5, 8.0), (s["reps"], s["rpe"]))

    def test_bodyweight_set_has_no_weight(self):
        s = summarize_set({"type": "normal", "weight_kg": None, "reps": 8})
        self.assertIsNone(s["weight_kg"])
        self.assertIsNone(s["weight_lb"])
        self.assertEqual(8, s["reps"])

    def test_missing_type_defaults_to_normal(self):
        self.assertEqual("normal", summarize_set({"reps": 3})["type"])

    def test_duration_and_distance_pass_through(self):
        s = summarize_set({"type": "normal", "duration_seconds": 1800, "distance_meters": 5000})
        self.assertEqual((1800.0, 5000.0), (s["duration_seconds"], s["distance_meters"]))


class TestSummarizeWorkout(unittest.TestCase):

    def test_duration_in_minutes(self):
        self.assertEqual(58, summarize_workout(_workout())["duration_minutes"])

    def test_z_suffix_timestamps_parse(self):
        w = summarize_workout(_workout(start_time="2026-09-30T17:00:00Z", end_time="2026-09-30T18:30:00Z"))
        self.assertEqual(90, w["duration_minutes"])

    def test_unparseable_or_reversed_times_give_no_duration(self):
        self.assertIsNone(summarize_workout(_workout(start_time="nonsense"))["duration_minutes"])
        self.assertIsNone(
            summarize_workout(
                _workout(start_time="2026-09-30T18:00:00+00:00", end_time="2026-09-30T17:00:00+00:00")
            )["duration_minutes"]
        )

    def test_warmups_excluded_from_working_sets_and_volume(self):
        w = summarize_workout(_workout())
        self.assertEqual(2, w["working_sets"])
        self.assertEqual(120 * 5 + 127.5 * 5, w["volume_kg"])

    def test_exercises_and_sets_are_ordered_by_index(self):
        raw = _workout(
            exercises=[
                {"index": 1, "title": "B", "sets": [{"index": 1, "reps": 2}, {"index": 0, "reps": 1}]},
                {"index": 0, "title": "A", "sets": []},
            ]
        )
        w = summarize_workout(raw)
        self.assertEqual(["A", "B"], [e["title"] for e in w["exercises"]])
        self.assertEqual([1, 2], [s["reps"] for s in w["exercises"][1]["sets"]])

    def test_empty_notes_become_none_and_titles_default(self):
        w = summarize_workout({"id": "x", "exercises": [{"sets": []}]})
        self.assertEqual("Workout", w["title"])
        self.assertEqual("Unknown exercise", w["exercises"][0]["title"])
        self.assertIsNone(w["exercises"][0]["notes"])

    def test_workout_with_no_exercises(self):
        w = summarize_workout({"id": "x", "title": "Empty", "exercises": []})
        self.assertEqual((0, 0.0, []), (w["working_sets"], w["volume_kg"], w["exercises"]))


if __name__ == "__main__":
    unittest.main()
