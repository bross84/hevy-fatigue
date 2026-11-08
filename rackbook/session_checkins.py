"""Confirmed pre-session observations; independent of fatigue/trial calculations."""
import json
from datetime import datetime, timedelta, timezone
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


CLOSING_WINDOW = timedelta(days=14)  # a finished microcycle older than this is reviewed only on request


def normalized(data):
    return MotivationInput.model_validate(data).model_dump(mode='json')


def _moment(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def closing_candidate(conn, start, identity, confirmed_at=None):
    """The finished microcycle whose look-back review is due at this check-in, or None. Pure reads.

    A microcycle is finished when every one of its sessions is resolved: trained (or marked done) or
    skipped, the predicate the end-of-microcycle review itself requires. It is due when its last
    session started before this check-in but within CLOSING_WINDOW, it is the most recently finished
    one, and no other check-in has started since it finished. A skip is an event rather than a workout,
    so it is compared with when this check-in was confirmed: a draft started before the skip still
    qualifies. Independent of whether this check-in belongs to any plan."""
    confirmed_at = confirmed_at or datetime.now(timezone.utc)
    best = None
    for plan in conn.execute('SELECT id, document FROM mesocycles'):
        try:
            document = json.loads(plan['document'])
            sessions = [s['id'] for week in document['weeks'] for s in week['sessions']]
        except (ValueError, KeyError, TypeError):
            continue
        if not sessions:
            continue
        done = {r['session_id']: (_moment(r['workout_start']), r['outcome']) for r in conn.execute(
            'SELECT session_id, workout_start, outcome FROM mesocycle_completions WHERE mesocycle_id=?', (plan['id'],))}
        if any(done.get(s, (None,))[0] is None for s in sessions):
            continue
        trained = [done[s][0] for s in sessions if done[s][1] != 'skipped']
        skipped = [done[s][0] for s in sessions if done[s][1] == 'skipped']
        final = max(trained + skipped)
        if trained and not max(trained) < start:
            continue
        if skipped and not max(skipped) < confirmed_at:
            continue
        if not start <= final + CLOSING_WINDOW:
            continue
        if best is None or final > best[0]:
            best = (final, plan['id'], document.get('name') or 'Microcycle')
    if best is None:
        return None
    final, plan_id, name = best
    floor = (final - timedelta(days=1)).date().isoformat()
    for row in conn.execute('SELECT workout_start FROM session_checkins WHERE session_id != ? AND substr(workout_start,1,10) >= ?',
                            (identity, floor)):
        later = _moment(row['workout_start'])
        if later and later > final:
            return None
    return dict(plan_id=plan_id, name=name, completed_on=final.date().isoformat())


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
        before_sets=motivation['timing']=='before_working_sets'
        closing=closing_candidate(conn,data.workout_start,identity,datetime.now(timezone.utc)) if before_sets else None
    return dict(recorded=True,weekly_review_eligible=first and before_sets,closing_review=closing)


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
