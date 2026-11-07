"""Session-level self-report for coaching context, never an input to fatigue models."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import AwareDatetime, BaseModel, Field
from .database import get_db


class MotivationInput(BaseModel):
    level: int = Field(strict=True, ge=0, le=4)
    reason: Literal['fatigue', 'stale', 'life_stress', 'other'] | None = None  # Historical compatibility; no dropdown in the new UI.
    note: str = Field(default='', max_length=500)
    recorded_at: AwareDatetime | None = None  # Client-reported, not server-verified prospective timing.
    timing: Literal['before_working_sets', 'after_working_sets', 'unknown'] = 'unknown'


class MotivationRecord(MotivationInput):
    saved_at: str


def record(payload, workout_id, connection):
    data = payload.get('motivation')
    if data is None:
        return
    connection.execute('''INSERT INTO session_motivation
        (hevy_workout_id,workout_start,level,reason,note,recorded_at,timing,saved_at)
        VALUES (?,?,?,?,?,?,?,?)''',
        (workout_id,payload['start_time'],data['level'],data.get('reason'),data.get('note',''),
         data.get('recorded_at'),data.get('timing','unknown'),datetime.now(timezone.utc).isoformat()))


def read(workout_id):
    with get_db() as conn:
        row = conn.execute('SELECT level,reason,note,recorded_at,timing,saved_at FROM session_motivation WHERE hevy_workout_id=?',(workout_id,)).fetchone()
    return dict(row) if row else None
