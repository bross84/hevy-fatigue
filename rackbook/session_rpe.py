"""Whole-session RPE from the Finish workout box (#199).

Same values as a set RPE: 4 to 10 in steps of 0.5. Optional; recorded with the other local
records when a save finalizes, keyed by the Hevy workout id. The host reads it (read-only) to
fill an empty sRPE on that workout's monitoring session; a value typed on the dashboard wins.
"""
from contextlib import closing
from datetime import datetime, timezone

from .database import get_db


def valid(value):
    """True for 4, 4.5 ... 10, the set RPE values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return 4 <= number <= 10 and (number * 2).is_integer()


def record(payload, workout_id, connection):
    value = payload.get('session_rpe')
    if value is None:
        return
    connection.execute('''INSERT INTO session_rpe (hevy_workout_id, workout_start, rpe, saved_at)
        VALUES (?,?,?,?) ON CONFLICT(hevy_workout_id) DO NOTHING''',
        (workout_id, payload['start_time'], float(value), datetime.now(timezone.utc).isoformat()))


def read(workout_id):
    with closing(get_db()) as conn:
        row = conn.execute('SELECT rpe FROM session_rpe WHERE hevy_workout_id=?', (workout_id,)).fetchone()
    return float(row['rpe']) if row else None
