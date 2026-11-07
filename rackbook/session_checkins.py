"""Confirmed pre-session observations; independent of fatigue/trial calculations."""
import json
from datetime import datetime, timezone
from uuid import UUID
from pydantic import AwareDatetime, BaseModel
from .database import get_db
from .motivation import MotivationInput
from .mesocycles import PlanLink


class CheckinInput(BaseModel):
    session_id: UUID
    workout_start: AwareDatetime
    motivation: MotivationInput
    planned_session: PlanLink | None = None


def normalized(data):
    return MotivationInput.model_validate(data).model_dump(mode='json')


def record(data):
    identity=str(data.session_id)
    motivation=normalized(data.motivation)
    link=data.planned_session
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM workout_saves WHERE client_workout_id=?',(identity,)).fetchone():
            raise ValueError('This workout save is frozen. Its check-in cannot be changed.')
        first=False
        if link:
            plan=conn.execute('SELECT document,archived FROM mesocycles WHERE id=?',(link.mesocycle_id,)).fetchone()
            if not plan or plan['archived']: raise ValueError('The planned week is unavailable.')
            sessions=[s for w in json.loads(plan['document'])['weeks'] for s in w['sessions']]
            if not any(s['id']==link.session_id for s in sessions): raise ValueError('Session does not belong to this week.')
            first=bool(sessions and sessions[0]['id']==link.session_id and not conn.execute(
                'SELECT 1 FROM mesocycle_completions WHERE mesocycle_id=? AND session_id=?',(link.mesocycle_id,link.session_id)).fetchone())
        existing=conn.execute('SELECT workout_start FROM session_checkins WHERE session_id=?',(identity,)).fetchone()
        start=data.workout_start.isoformat()
        if existing and existing['workout_start']!=start: raise ValueError('This check-in belongs to a different workout start.')
        conn.execute('''INSERT INTO session_checkins
            (session_id,workout_start,plan_id,plan_session_id,motivation,recorded_at)
            VALUES (?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
            plan_id=excluded.plan_id,plan_session_id=excluded.plan_session_id,
            motivation=excluded.motivation,recorded_at=excluded.recorded_at''',
            (identity,start,link.mesocycle_id if link else None,link.session_id if link else None,
             json.dumps(motivation,sort_keys=True),datetime.now(timezone.utc).isoformat()))
    return dict(recorded=True,weekly_review_eligible=first and motivation['timing']=='before_working_sets')


def validate_save(conn, payload, identity):
    if not payload.get('checkin_required'): return  # Frozen legacy saves remain valid.
    if not payload.get('motivation'): raise ValueError('Confirm your motivation check-in before saving.')
    row=conn.execute('SELECT * FROM session_checkins WHERE session_id=?',(str(identity),)).fetchone()
    if not row: raise ValueError('Confirm your motivation check-in before saving.')
    if datetime.fromisoformat(row['workout_start'].replace('Z','+00:00'))!=datetime.fromisoformat(payload['start_time'].replace('Z','+00:00')):
        raise ValueError('Check-in workout start does not match.')
    if normalized(payload['motivation'])!=json.loads(row['motivation']): raise ValueError('The motivation answer changed. Confirm it again before saving.')
    link=payload.get('planned_session') or {}
    if (row['plan_id'],row['plan_session_id'])!=(link.get('mesocycle_id'),link.get('session_id')):
        raise ValueError('The planned session changed. Confirm your check-in again.')


def link_workout(conn, identity, workout_id):
    conn.execute('UPDATE session_checkins SET linked_workout_id=? WHERE session_id=?',(workout_id,str(identity)))
