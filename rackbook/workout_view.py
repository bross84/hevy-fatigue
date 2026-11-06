"""
workout_view.py — Pure conversion of a raw Hevy workout into the shape the Recent page displays.
No DB access, no HTTP calls, no side effects.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

KG_TO_LB = 2.20462


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _order(item: dict[str, Any]) -> float:
    return _num(item.get("index")) or 0.0


def summarize_set(raw: dict[str, Any]) -> dict[str, Any]:
    kg = _num(raw.get("weight_kg"))
    return {
        "index": _int(raw.get("index")),
        "type": raw.get("type") or "normal",
        "weight_kg": kg,
        "weight_lb": round(kg * KG_TO_LB, 1) if kg is not None else None,
        "reps": _int(raw.get("reps")),
        "rpe": _num(raw.get("rpe")),
        "distance_meters": _num(raw.get("distance_meters")),
        "duration_seconds": _num(raw.get("duration_seconds")),
    }


def summarize_workout(raw: dict[str, Any]) -> dict[str, Any]:
    start = _parse_time(raw.get("start_time"))
    end = _parse_time(raw.get("end_time"))
    duration_minutes = None
    if start is not None and end is not None and end >= start:
        duration_minutes = round((end - start).total_seconds() / 60)

    exercises = []
    working_sets = 0
    volume_kg = 0.0
    for raw_exercise in sorted(raw.get("exercises") or [], key=_order):
        sets = [summarize_set(s) for s in sorted(raw_exercise.get("sets") or [], key=_order)]
        for s in sets:
            if s["type"] == "warmup":
                continue
            working_sets += 1
            if s["weight_kg"] is not None and s["reps"] is not None:
                volume_kg += s["weight_kg"] * s["reps"]
        exercises.append(
            {
                "title": raw_exercise.get("title") or "Unknown exercise",
                "notes": raw_exercise.get("notes") or None,
                "exercise_template_id": raw_exercise.get("exercise_template_id"),
                "sets": sets,
            }
        )

    return {
        "id": str(raw.get("id") or ""),
        "title": raw.get("title") or "Workout",
        "description": raw.get("description") or None,
        "start_time": raw.get("start_time"),
        "end_time": raw.get("end_time"),
        "duration_minutes": duration_minutes,
        "working_sets": working_sets,
        "volume_kg": round(volume_kg, 1),
        "exercises": exercises,
    }
