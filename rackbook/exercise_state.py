"""
exercise_state.py — Pure: a movement's current e1RM, worked out from its last session in Hevy.
No DB access, no HTTP calls, no side effects.

Input is Hevy's per-set exercise history (one entry per set, every session, newest first):
    {workout_id, workout_title, workout_start_time, set_type, weight_kg, reps, rpe, ...}
The e1RM of a set follows the user's spreadsheet: weight in lb / RPE-table percentage for (reps, RPE),
with the weight in the lb the user typed (Hevy stores it as kg, so it is converted back and snapped to
the nearest half pound).
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

LB_PER_KG = 2.20462

PctLookup = Callable[[float, int], "float | None"]


def weight_lb(weight_kg: float) -> float:
    """Back to the pounds the user typed: Hevy stores 265 lb as 120.2 kg."""
    return round(weight_kg * LB_PER_KG * 2) / 2


def e1rm_lb(weight_in_lb: float, reps: int, rpe: float, pct: PctLookup) -> float | None:
    p = pct(float(rpe), int(reps))
    return weight_in_lb / p if p else None


def sessions_newest_first(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group per-set entries into sessions (workouts), newest first; set order inside a session is kept."""
    by_workout: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for entry in entries:
        by_workout.setdefault(entry.get("workout_id") or "", []).append(entry)
    return sorted(
        by_workout.values(),
        key=lambda sets: max(s.get("workout_start_time") or "" for s in sets),
        reverse=True,
    )


def reference_set(session: list[dict[str, Any]], pct: PctLookup) -> dict[str, Any] | None:
    """
    The set that stands for a session: the working set with the highest e1RM, among those that have
    reps, an RPE and a table value. The heaviest set is not always the best one (weight can drop while
    the RPE climbs). The result always reports the set it used so the page can show it. A tie goes to
    the later set.
    """
    best = None
    for entry in session:
        if entry.get("set_type") == "warmup":
            continue
        kg, reps, rpe = entry.get("weight_kg"), entry.get("reps"), entry.get("rpe")
        if not kg or not reps or rpe is None:
            continue
        lb = weight_lb(kg)
        e1rm = e1rm_lb(lb, reps, rpe, pct)
        if e1rm is None:
            continue
        if best is None or e1rm >= best["e1rm_lb"]:
            best = {"weight_lb": lb, "reps": int(reps), "rpe": float(rpe), "e1rm_lb": e1rm, "entry": entry}
    return best


def previous_sets(sessions: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The sets of the most recent session, in order, for the Previous column. Sets with nothing logged are skipped."""
    for session in sessions:
        sets = [
            {
                "type": e.get("set_type") or "normal",
                "weight_lb": weight_lb(e["weight_kg"]) if e.get("weight_kg") else None,
                "reps": e.get("reps"),
                "rpe": e.get("rpe"),
            }
            for e in session
            if e.get("weight_kg") or e.get("reps")
        ]
        if sets:
            return sets
    return []


def build_exercise_state(entries: list[dict[str, Any]], pct: PctLookup) -> dict[str, Any]:
    """The movement's e1RM from its most recent session that has a usable set (or found=False), plus the sets
    of the most recent session of any kind."""
    sessions = sessions_newest_first(entries)
    previous = previous_sets(sessions)
    for session in sessions:
        ref = reference_set(session, pct)
        if ref is None:
            continue
        entry = ref["entry"]
        return {
            "previous": previous,
            "found": True,
            "workout_title": entry.get("workout_title"),
            "workout_start_time": entry.get("workout_start_time"),
            "set_weight_lb": ref["weight_lb"],
            "set_reps": ref["reps"],
            "set_rpe": ref["rpe"],
            "e1rm_lb": round(ref["e1rm_lb"], 1),
        }
    return {
        "previous": previous,
        "found": False,
        "workout_title": None,
        "workout_start_time": None,
        "set_weight_lb": None,
        "set_reps": None,
        "set_rpe": None,
        "e1rm_lb": None,
    }
