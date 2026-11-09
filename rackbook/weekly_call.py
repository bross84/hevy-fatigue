"""Weekly coaching call: setting up the microcycle after a finished one (ADR 0002).

When every day of a microcycle is trained or skipped and no next one is active, the Log page holds one
weekly coaching call for it. Its next week becomes active only on the athlete's tap: either Accept on
the coach's plan proposal in that call, or Run it back, which repeats the finished microcycle unchanged
without any AI. Each finished microcycle gets at most one next week, recorded in
microcycle_successors with whatever was active before, so the tap can be undone until day 1 is trained
or the new week is edited. Nothing here contacts Hevy, sets a weight the athlete did not already set, or
changes a finished microcycle. The logger cannot read host conversations; a reply can set up a next week
only if its conversation id is that microcycle's call identity.
"""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from pydantic import ValidationError

from .database import get_db
from . import mesocycles, plan_proposals

CALL_WINDOW = timedelta(days=14)  # a microcycle finished longer ago than this gets no automatic call


class CallError(Exception):
    def __init__(self, message, status=409):
        self.status = status
        super().__init__(message)


def call_identity(plan_id):
    """The weekly coaching call conversation for a finished microcycle; matches the host's weekly_coaching.identity."""
    return str(uuid5(NAMESPACE_URL, 'hevy-fatigue:weekly-review:' + plan_id + ':call'))


def _now():
    return datetime.now(timezone.utc)


def _moment(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sessions(row):
    return [s for week in json.loads(row['document'])['weeks'] for s in week['sessions']]


def _completions(conn, plan_id):
    return {r['session_id']: r for r in conn.execute(
        'SELECT session_id, workout_start, outcome FROM mesocycle_completions WHERE mesocycle_id = ?', (plan_id,))}


def _finished_at(conn, row):
    """When the last day of a microcycle was resolved, or None while any day is pending."""
    sessions = _sessions(row)
    done = _completions(conn, row['id'])
    if not sessions or any(s['id'] not in done for s in sessions):
        return None
    moments = [_moment(done[s['id']]['workout_start']) for s in sessions]
    return max(m for m in moments if m) if any(moments) else None


def _plan(conn, plan_id):
    row = conn.execute('SELECT * FROM mesocycles WHERE id = ?', (plan_id,)).fetchone()
    if row is None:
        raise CallError('That microcycle was not found.', 404)
    return row


def _finished_source(conn, plan_id):
    row = _plan(conn, plan_id)
    if row['archived']:
        raise CallError('That microcycle has been deleted.')
    if _finished_at(conn, row) is None:
        raise CallError('That microcycle still has days to train or skip.')
    return row


def _undo_problem(conn, successor):
    row = conn.execute('SELECT revision, archived FROM mesocycles WHERE id = ?', (successor['plan_id'],)).fetchone()
    if row is None or row['archived']:
        return 'The next week has been deleted.'
    if conn.execute('SELECT 1 FROM mesocycle_completions WHERE mesocycle_id = ? LIMIT 1', (successor['plan_id'],)).fetchone():
        return 'A day of the next week has been trained or skipped, so it cannot be undone here.'
    if row['revision'] != 1:
        return 'The next week was edited in the builder, so it cannot be undone here. Delete it there if you want to.'
    return None


def _next_view(conn, source_id):
    successor = conn.execute('SELECT * FROM microcycle_successors WHERE source_plan_id = ?', (source_id,)).fetchone()
    if successor is None:
        return None
    row = conn.execute('SELECT document FROM mesocycles WHERE id = ?', (successor['plan_id'],)).fetchone()
    problem = _undo_problem(conn, successor)
    return dict(plan_id=successor['plan_id'], name=json.loads(row['document'])['name'] if row else None,
                origin=successor['origin'], proposal_id=successor['proposal_id'], created_at=successor['created_at'],
                can_undo=problem is None, undo_problem=problem)


def _next_name(source_document, fallback):
    program = (source_document.get('program_name') or '').strip()
    if program:
        return f"{program}{source_document.get('cycle') or 1}.{(source_document.get('week') or 1) + 1}"
    return fallback


def _status(conn, source_row):
    document = json.loads(source_row['document'])
    finished = _finished_at(conn, source_row)
    return dict(source=dict(id=source_row['id'], name=document['name'], finished=finished is not None,
                            completed_on=finished.date().isoformat() if finished else None, archived=bool(source_row['archived'])),
                call_id=call_identity(source_row['id']), next=_next_view(conn, source_row['id']))


def rollover(now=None):
    """The finished microcycle whose weekly coaching call is due on the Log page, or None. Pure reads.

    Due when no active microcycle has a day left to train, the most recently finished undeleted microcycle
    finished within CALL_WINDOW, and it has no next week yet. A call that was held but not accepted stays
    due, so its reply and Run it back remain available."""
    now = now or _now()
    with get_db() as conn:
        active = conn.execute('SELECT * FROM mesocycles WHERE active = 1 AND archived = 0').fetchone()
        if active is not None and _finished_at(conn, active) is None and _sessions(active):
            return None
        best = None
        for row in conn.execute('SELECT * FROM mesocycles WHERE archived = 0').fetchall():
            finished = _finished_at(conn, row)
            if finished and (best is None or finished > best[0]):
                best = (finished, row)
        if best is None or best[0] < now - CALL_WINDOW:
            return None
        status = _status(conn, best[1])
        return None if status['next'] else status


def status(source_id):
    with get_db() as conn:
        return _status(conn, _plan(conn, source_id))


def preview(text, conversation_id: UUID, turn_id: UUID, source_id):
    """A proposal read as a candidate next week for this call. Writes nothing."""
    with get_db() as conn:
        report = plan_proposals.analyse(conn, text)[0]
        source = _plan(conn, source_id)
        call = _status(conn, source)
        call.update(matches=str(conversation_id) == call_identity(source_id),
                    proposal_id=plan_proposals.proposal_id(conversation_id, turn_id),
                    next_name=_next_name(json.loads(source['document']), report.get('title') or 'Next week'))
        call['this_turn'] = bool(call['next'] and call['next']['proposal_id'] == call['proposal_id'])
        report['call'] = call
        return report


def _activate(conn, plan_id):
    previous = conn.execute('SELECT id FROM mesocycles WHERE active = 1').fetchone()
    conn.execute('UPDATE mesocycles SET active = 0 WHERE active = 1')
    conn.execute('UPDATE mesocycles SET active = 1 WHERE id = ?', (plan_id,))
    return previous['id'] if previous else None


def _continued(source_document, data, name):
    """The next week's identity: same program and cycle, the following week number."""
    week = (source_document.get('week') or 1) + 1
    if week > 9999:
        raise CallError('Week must be below 9999 to advance.')
    try:
        return mesocycles.PlanInput.model_validate(dict(
            data, name=name[:120], program_name=source_document.get('program_name') or '',
            cycle=source_document.get('cycle') or 1, week=week, revision=0, rpe_assignments={}))
    except ValidationError as exc:
        raise CallError('The next week is not a valid plan: ' + ' '.join(plan_proposals.problems(exc)), 422)


def accept_next_week(text, conversation_id: UUID, turn_id: UUID, source_id):
    """The athlete's Accept tap on a proposal in this microcycle's call: create the next week and make it active."""
    if str(conversation_id) != call_identity(source_id):
        raise CallError('Only the weekly coaching call for that microcycle can set up its next week.', 422)
    identifier = plan_proposals.proposal_id(conversation_id, turn_id)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        source = _finished_source(conn, source_id)
        existing = _next_view(conn, source_id)
        if existing:
            if existing['proposal_id'] == identifier:
                return dict(already_applied=True, call=_status(conn, source))
            raise CallError('Next week is already set up for that microcycle.')
        if conn.execute('SELECT 1 FROM plan_proposals WHERE id = ?', (identifier,)).fetchone():
            raise CallError('This proposal was already saved as a draft. Activate that draft in the builder instead.')
        report, data, canonical = plan_proposals.analyse(conn, text)
        if not report.get('found'):
            raise CallError('No plan proposal was found in that reply.', 422)
        if not report['valid']:
            raise CallError('This proposal cannot be used: ' + ' '.join(report['issues']), 422)
        document = json.loads(source['document'])
        plan = _continued(document, dict(data.model_dump(), notes='Weekly coaching call: ' + report['rationale']),
                          _next_name(document, data.name))
        plan_id = mesocycles.insert_draft(conn, plan)
        previous = _activate(conn, plan_id)
        now = _now().isoformat()
        conn.execute('INSERT INTO plan_proposals (id, conversation_id, turn_id, plan_id, proposed, saved_at) VALUES (?, ?, ?, ?, ?, ?)',
                     (identifier, str(conversation_id), str(turn_id), plan_id, json.dumps(canonical), now))
        conn.execute('INSERT INTO microcycle_successors (source_plan_id, plan_id, origin, proposal_id, previous_active_id, created_at) '
                     "VALUES (?, ?, 'coach', ?, ?, ?)", (source_id, plan_id, identifier, previous, now))
        return dict(already_applied=False, call=_status(conn, source))


def run_it_back(source_id):
    """The athlete's Run it back tap: repeat the finished microcycle unchanged as the next, active week. No AI."""
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        source = _finished_source(conn, source_id)
        existing = _next_view(conn, source_id)
        if existing:
            if existing['origin'] == 'repeat':
                return dict(already_applied=True, call=_status(conn, source))
            raise CallError('Next week is already set up for that microcycle.')
        document = json.loads(source['document'])
        weeks = [dict(week, sessions=[dict(s, id=str(uuid4())) for s in week['sessions']]) for week in document['weeks']]
        plan = _continued(document, dict(document, weeks=weeks), _next_name(document, (document['name'] + ' copy')[:120]))
        plan_id = mesocycles.insert_draft(conn, plan)
        previous = _activate(conn, plan_id)
        conn.execute('INSERT INTO microcycle_successors (source_plan_id, plan_id, origin, proposal_id, previous_active_id, created_at) '
                     "VALUES (?, ?, 'repeat', NULL, ?, ?)", (source_id, plan_id, previous, _now().isoformat()))
        return dict(already_applied=False, call=_status(conn, source))


def undo(source_id):
    """Take back the next week set up from this call while it is untouched; whatever was active before is restored."""
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        source = _plan(conn, source_id)
        successor = conn.execute('SELECT * FROM microcycle_successors WHERE source_plan_id = ?', (source_id,)).fetchone()
        if successor is None:
            raise CallError('No next week has been set up for that microcycle.')
        problem = _undo_problem(conn, successor)
        if problem:
            raise CallError(problem)
        conn.execute('UPDATE mesocycles SET active = 0, archived = 1 WHERE id = ?', (successor['plan_id'],))
        previous = successor['previous_active_id']
        if previous:
            row = conn.execute('SELECT * FROM mesocycles WHERE id = ? AND archived = 0', (previous,)).fetchone()
            if row is not None and _finished_at(conn, row) is None and _sessions(row):
                conn.execute('UPDATE mesocycles SET active = 1 WHERE id = ?', (previous,))
        conn.execute('DELETE FROM microcycle_successors WHERE source_plan_id = ?', (source_id,))
        if successor['proposal_id']:
            # The proposal can be accepted again; its undone plan stays archived for history.
            conn.execute('DELETE FROM plan_proposals WHERE id = ?', (successor['proposal_id'],))
        return dict(call=_status(conn, source))
