"""Durable workout delivery: ambiguous remote attempts are never reposted.

SQLite serializes claims and finalization. Network calls happen outside database
transactions. Remote acknowledgement is committed before local effects begin.
"""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .database import get_db, get_rpe_percentage
from . import mesocycles, set_log, training_max, soreness, fatigue_trial, stress_service, session_review, session_advice
from .workout_payload import build_hevy_workout
from .hevy_client import WorkoutNotSent

logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def rejection_reason(error, client):
    reason=f'Hevy rejected the request (HTTP {error.response.status_code}).'
    try:
        message=error.response.json().get('error')
    except (ValueError, AttributeError):
        message=None
    if isinstance(message,str):
        key=getattr(client,'api_key',None)
        if isinstance(key,str) and key:
            message=message.replace(key,'[redacted]')
        reason+=' '+' '.join(message.split())[:200]
    return reason


def initialize():
    with closing(get_db()) as conn, conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS workout_saves (
            client_workout_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
            request_payload TEXT NOT NULL, hevy_payload TEXT NOT NULL, ts_rows TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('prepared','sending','remote_saved','complete','rejected','uncertain')),
            hevy_workout_id TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            failure_reason TEXT, monitoring_refresh TEXT NOT NULL DEFAULT 'pending')''')
        # A sending record is ambiguous even if another worker is still alive.
        # No recovery path is allowed to repost it.
        conn.execute("UPDATE workout_saves SET state='uncertain', failure_reason='Remote result unknown; verify in Hevy.', updated_at=? WHERE state='sending'", (now(),))


def read(client_id):
    with closing(get_db()) as conn:
        row = conn.execute('SELECT * FROM workout_saves WHERE client_workout_id=?', (str(client_id),)).fetchone()
    if row is None:
        raise HTTPException(404, 'No save attempt is recorded for this draft.')
    return dict(row)


def status(client_id):
    row = read(client_id)
    if row['state']=='complete' and row['monitoring_refresh']!='complete':
        try:
            from training_integration import monitoring_visible
            if monitoring_visible(row['hevy_workout_id']):
                monitoring_status(row['hevy_workout_id'],'complete')
                row['monitoring_refresh']='complete'
        except Exception:
            pass  # A local monitoring read never invalidates a saved workout.
    messages = {
        'prepared': 'Ready for the first save attempt.',
        'sending': 'Save in progress; do not save again.',
        'uncertain': 'The workout may be in Hevy. Saving again could duplicate it. Verify its workout ID to reconcile.',
        'remote_saved': 'Saved to Hevy; finishing local records.',
        'complete': 'Saved to Hevy and local records.',
        'rejected': 'This save was rejected. Correct the draft and use a new save identity.',
    }
    return dict(client_workout_id=row['client_workout_id'], state=row['state'], id=row['hevy_workout_id'],
                hevy_workout_id=row['hevy_workout_id'], status=messages[row['state']],
                failure_reason=row['failure_reason'], monitoring_refresh=row['monitoring_refresh'],
                monitoring_sync_url='/#settings')


def transition(client_id, state, reason=None, remote_id=None):
    with closing(get_db()) as conn, conn:
        # A late network result or optional-task error must never reopen a
        # committed workout and replay its required local effects.
        conn.execute(
            "UPDATE workout_saves SET state=?,failure_reason=?,hevy_workout_id=COALESCE(?,hevy_workout_id),updated_at=? WHERE client_workout_id=? AND state NOT IN ('complete','remote_saved')",
            (state, reason, remote_id, now(), str(client_id)))


def monitoring_status(workout_id, state):
    with closing(get_db()) as conn, conn:
        conn.execute('UPDATE workout_saves SET monitoring_refresh=? WHERE hevy_workout_id=?', (state, workout_id))


def prepare(entry):
    payload = entry.model_dump(mode='json')
    if not payload.get('advisory_links'):
        payload.pop('advisory_links',None)
    if payload.get('prescription') is None:
        payload.pop('prescription', None)
    # Keep pre-upgrade frozen requests byte-equivalent for identity/hash checks.
    # An absent prescription remains absent, including on legacy retries.
    for exercise in payload['exercises']:
        for s in exercise['sets']:
            if s.get('review') is None:
                s.pop('review', None)
            if s.get('target_rpe') is None:
                s.pop('target_rpe', None)
    client_id = str(payload.pop('client_workout_id', None) or uuid4())
    try:
        frozen = canonical(payload)
    except ValueError as exc:
        raise HTTPException(422, 'Workout values must be finite numbers.') from exc
    digest = sha256(frozen.encode()).hexdigest()
    # Compare before recalculating TS or checking changed plan state.
    with closing(get_db()) as conn:
        existing = conn.execute('SELECT payload_hash FROM workout_saves WHERE client_workout_id=?', (client_id,)).fetchone()
    if existing:
        if existing['payload_hash'] != digest:
            raise HTTPException(409, 'This save identity belongs to a different frozen workout.')
        return client_id
    body, rows, completed, rejection = {}, [], None, None
    try:
        with closing(get_db()) as conn:
            session_advice.validate_links(conn,entry.advisory_links,entry.client_workout_id,entry.start_time)
        completed = mesocycles.validate_save(entry.planned_session, entry.start_time) if entry.planned_session else None
        body = build_hevy_workout(payload)
        rows = training_max.ts_rows_from_entry(payload, get_rpe_percentage)
    except mesocycles.PlanError as exc:
        rejection = (exc.status, str(exc))
    except session_advice.AdviceError as exc:
        rejection = (exc.status, exc.message)
    except ValueError as exc:
        rejection = (422, str(exc))
    if rejection and not entry.client_workout_id:
        # Older callers retain their original HTTP validation failures.
        raise HTTPException(*rejection)
    stamp = now()
    with closing(get_db()) as conn, conn:
        if completed:
            previous = conn.execute('SELECT client_workout_id,payload_hash FROM workout_saves WHERE hevy_workout_id=?', (completed['hevy_workout_id'],)).fetchone()
            if previous:
                if entry.client_workout_id and previous['payload_hash'] != digest:
                    raise HTTPException(409, 'This planned session already belongs to a different saved workout.')
                return previous['client_workout_id']
        conn.execute('''INSERT INTO workout_saves
            (client_workout_id,payload_hash,request_payload,hevy_payload,ts_rows,state,hevy_workout_id,created_at,updated_at,failure_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(client_workout_id) DO NOTHING''',
            (client_id, digest, frozen, canonical(body), canonical(rows),
             'rejected' if rejection else 'complete' if completed else 'prepared',
             completed['hevy_workout_id'] if completed and not rejection else None, stamp, stamp,
             rejection[1] if rejection else None))
        actual = conn.execute('SELECT payload_hash FROM workout_saves WHERE client_workout_id=?', (client_id,)).fetchone()
        if actual['payload_hash'] != digest:
            raise HTTPException(409, 'This save identity belongs to a different frozen workout.')
    return client_id


def finalize(client_id):
    already_complete = False
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM workout_saves WHERE client_workout_id=?', (str(client_id),)).fetchone()
        if row is None:
            raise HTTPException(404, 'Save not found.')
        if row['state'] == 'complete':
            already_complete = True
        elif row['state'] != 'remote_saved' or not row['hevy_workout_id']:
            raise HTTPException(409, 'Local finalization requires a verified Hevy workout ID.')
        else:
            payload = json.loads(row['request_payload'])
            remote_id = row['hevy_workout_id']
            set_log.record(set_log.rows_from_entry(payload, remote_id), connection=conn)
            session_review.record(payload, remote_id, conn)
            session_advice.record_outcomes(payload, remote_id, conn)
            training_max.record(json.loads(row['ts_rows']), payload['start_time'], connection=conn)
            if payload.get('planned_session'):
                mesocycles.complete(mesocycles.PlanLink(**payload['planned_session']), remote_id, payload['start_time'], connection=conn)
            if payload.get('soreness'):
                soreness.record(remote_id, payload['start_time'], payload['soreness'], connection=conn)
            conn.execute("UPDATE workout_saves SET state='complete',failure_reason=NULL,updated_at=? WHERE client_workout_id=?", (now(), str(client_id)))
    if already_complete:
        # status() may update refresh metadata on another connection.
        # Release the write transaction before calling it.
        return status(client_id)
    # Optional work is strictly after commit. It cannot change save success.
    warning = []
    trial_results = []
    try:
        ids = [ex['exercise_template_id'] for ex in payload['exercises']]
        stress_service.invalidate(ids)
        fatigue_trial.record_skips(remote_id, payload['start_time'], ids)
        trial_results = fatigue_trial.complete_workout(remote_id, payload['start_time'])
    except Exception:
        logger.error('Workout saved; optional trial completion failed')
        warning.append('Optional trial results are unavailable. Do not save the workout again.')
    try:
        from training_integration import request_monitoring_refresh
        request_monitoring_refresh(remote_id)
    except Exception:
        try:
            monitoring_status(remote_id, 'failed')
        except Exception:
            pass
    return {**status(client_id), 'trial_results': trial_results, 'plan_warning': ' '.join(warning) or None}


def finish_or_pending(client_id):
    try:
        return finalize(client_id)
    except HTTPException:
        raise
    except Exception:
        # Never expose exceptions containing payloads or credentials.
        logger.error('Workout saved to Hevy; local completion pending')
        with closing(get_db()) as conn, conn:
            conn.execute("UPDATE workout_saves SET failure_reason=?,updated_at=? WHERE client_workout_id=? AND state='remote_saved'",
                         ('Local records could not be committed. Retry local finalization.',now(),str(client_id)))
        return {**status(client_id), 'plan_warning': 'Saved to Hevy; finishing local records. Do not save the workout again.'}


def save(entry, client):
    client_id = prepare(entry)
    row = read(client_id)
    if row['state'] == 'complete':
        return status(client_id)
    if row['state'] == 'remote_saved':
        return finish_or_pending(client_id)
    if row['state'] != 'prepared':
        return status(client_id)
    # Resolve credentials before claiming: no remote call can have happened yet.
    try:
        remote = client()
    except Exception:
        raise HTTPException(400, 'Configure the Hevy credential in Settings.')
    with closing(get_db()) as conn, conn:
        claimed = conn.execute("UPDATE workout_saves SET state='sending',failure_reason=NULL,updated_at=? WHERE client_workout_id=? AND state='prepared'", (now(), client_id)).rowcount
    if not claimed:
        return status(client_id)
    try:
        created = remote.create_workout(json.loads(row['hevy_payload']))
        remote_id = created.get('id')
        if not isinstance(remote_id, str) or not remote_id.strip():
            raise RuntimeError('Missing remote ID')
    except WorkoutNotSent as exc:
        # Only this explicit exception guarantees that no POST was started.
        # A generic ValueError can also mean a lost/malformed response.
        with closing(get_db()) as conn, conn:
            conn.execute("UPDATE workout_saves SET state='prepared',failure_reason=?,updated_at=? WHERE client_workout_id=? AND state='sending'",
                         (str(exc), now(), client_id))
        return status(client_id)
    except httpx.HTTPStatusError as exc:
        # Only unambiguous client rejections are definitive; timeout/rate-limit
        # and all server failures require read-only reconciliation.
        code = exc.response.status_code
        rejected = code in (400, 401, 403, 404, 405, 413, 415, 422)
        transition(client_id, 'rejected' if rejected else 'uncertain',
                   rejection_reason(exc,remote) if rejected else 'Remote result unknown; verify in Hevy.')
        return status(client_id)
    except ValueError:
        # Preview policy or malformed response: never assume delivery failed.
        transition(client_id, 'uncertain', 'Remote result unknown or writes disabled; verify status before continuing.')
        return status(client_id)
    except Exception:
        transition(client_id, 'uncertain', 'Remote result unknown; verify in Hevy.')
        return status(client_id)
    transition(client_id, 'remote_saved', remote_id=remote_id)
    return finish_or_pending(client_id)


def normalized(workout):
    def timestamp(value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Timezone required for reconciliation')
        return parsed.astimezone(timezone.utc).isoformat()
    return {
        'title': workout['title'], 'start_time': timestamp(workout['start_time']), 'end_time': timestamp(workout['end_time']),
        'description': workout.get('description') or '',
        'exercises': [dict(exercise_template_id=ex['exercise_template_id'], notes=ex.get('notes') or '',
                           sets=[{key: (round(float(s[key]), 6) if key == 'weight_kg' and s.get(key) is not None else s.get(key))
                                  for key in ('type', 'weight_kg', 'reps', 'rpe')} for s in ex['sets']])
                      for ex in workout['exercises']],
    }


def reconcile(client_id, remote_id, client):
    row = read(client_id)
    if row['state'] not in ('uncertain', 'sending'):
        raise HTTPException(409, 'Only ambiguous attempts require reconciliation.')
    try:
        actual = client().get_workout(remote_id)
        expected = json.loads(row['hevy_payload'])['workout']
        matches = actual.get('id') == remote_id and normalized(expected) == normalized(actual)
    except Exception:
        raise HTTPException(409, 'Could not verify the selected Hevy workout. No records were linked.')
    if not matches:
        raise HTTPException(409, 'The selected Hevy workout does not match the frozen submission.')
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        current = conn.execute('SELECT state,hevy_workout_id FROM workout_saves WHERE client_workout_id=?', (str(client_id),)).fetchone()
        if current['state'] not in ('uncertain', 'sending'):
            if current['hevy_workout_id'] != remote_id:
                raise HTTPException(409, 'Save already linked to another workout.')
        else:
            other = conn.execute('SELECT 1 FROM workout_saves WHERE hevy_workout_id=? AND client_workout_id<>?', (remote_id, str(client_id))).fetchone()
            if other:
                raise HTTPException(409, 'That Hevy workout is already linked to another save.')
            conn.execute("UPDATE workout_saves SET state='remote_saved', hevy_workout_id=?, updated_at=?, failure_reason=NULL WHERE client_workout_id=?", (remote_id, now(), str(client_id)))
    return finish_or_pending(client_id)
