"""
training_max.py — The TS: the set you mark on the log page to set a movement's TM.

Marking a TS only takes effect when the workout is saved to Hevy, so an abandoned draft changes nothing.
The movement's TM is then the latest TS's e1RM x the TM percentage (the percentage lives in exercise_refs and
is applied on the page). Every TS is kept, newest workout last, so the TM's trend can be shown later.
"""
from __future__ import annotations

from typing import Any, Callable

from .transactions import transaction
from .database import get_db
from .exercise_state import LB_PER_KG, e1rm_lb

PctLookup = Callable[[float, int], "float | None"]


def ts_rows_from_entry(entry: dict[str, Any], pct: PctLookup) -> list[dict[str, Any]]:
    """
    The TS of each exercise in a logged workout (weights in lb): its weight, reps, RPE and e1RM from the RPE table.
    Raises ValueError, naming the exercise, if a marked set can't give an e1RM or an exercise has two.
    """
    rows = []
    for exercise in entry.get("exercises") or []:
        template_id = exercise.get("exercise_template_id")
        name = exercise.get("title") or template_id or "exercise"
        marked = [s for s in exercise.get("sets") or [] if s.get("ts")]
        if not marked:
            continue
        if len(marked) > 1:
            raise ValueError(f"{name}: only one TS per exercise.")
        s = marked[0]
        if s.get("type") == "warmup":
            raise ValueError(f"{name}: a warm-up can't be the TS.")
        kg, reps, rpe = s.get("weight_kg"), s.get("reps"), s.get("rpe")
        if not kg or not reps or rpe is None:
            raise ValueError(f"{name}: the TS set needs a weight, reps and an RPE.")
        weight = float(kg) * LB_PER_KG   # the e1RM sheet works in lb
        e1rm = e1rm_lb(weight, int(reps), float(rpe), pct)
        if e1rm is None:
            raise ValueError(f"{name}: the RPE table has no value for the TS set ({reps} reps at RPE {rpe}).")
        rows.append({
            "exercise_template_id": template_id,
            "weight_lb": round(weight, 1),
            "reps": int(reps),
            "rpe": float(rpe),
            "e1rm_lb": round(e1rm, 1),
        })
    return rows


def record(rows: list[dict[str, Any]], set_at: str, connection=None) -> None:
    """Keep each TS. set_at is the workout's start time."""
    if not rows:
        return
    with transaction(connection) as conn:
        conn.executemany(
            """
            INSERT INTO training_max_history (exercise_template_id, e1rm_lb, weight_lb, reps, rpe, set_at)
            VALUES (:exercise_template_id, :e1rm_lb, :weight_lb, :reps, :rpe, :set_at)
            """,
            [{**r, "set_at": set_at} for r in rows],
        )


def history(exercise_template_id: str) -> list[dict[str, Any]]:
    """Every TS the movement has had, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT e1rm_lb, weight_lb, reps, rpe, set_at
            FROM training_max_history
            WHERE exercise_template_id = ?
            ORDER BY set_at, id
            """,
            (exercise_template_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def latest(exercise_template_id: str) -> dict[str, Any]:
    """The movement's current TS (the one from the newest workout), or found=False."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT e1rm_lb, weight_lb, reps, rpe, set_at
            FROM training_max_history
            WHERE exercise_template_id = ?
            ORDER BY set_at DESC, id DESC
            LIMIT 1
            """,
            (exercise_template_id,),
        ).fetchone()
    if row is None:
        return {"found": False, "e1rm_lb": None, "weight_lb": None, "reps": None, "rpe": None, "set_at": None}
    return {"found": True, **dict(row)}
