"""AI week proposals become inactive draft microcycles only through an explicit save.

Parsing, validation and preview write nothing. Saving inserts one new inactive plan and its
provenance row in one transaction. It never edits, activates, archives or completes a plan,
sets a weight, or contacts Hevy. Text from the AI is untrusted: fields are length-limited,
movement titles come from local records, and unknown movements are rejected.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .database import get_db
from . import mesocycles

FENCE = 'plan-proposal-v1'
MAX_REPLY_CHARS = 80_000
MAX_BLOCK_CHARS = 30_000
MAX_ISSUES = 8
BLOCK = re.compile(r'```' + re.escape(FENCE) + r'[ \t]*\r?\n(.*?)```', re.DOTALL)


class ProposalError(Exception):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


class ProposedSet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reps: int = Field(ge=1, le=100)
    rpe: float | None = Field(default=None, ge=4, le=10)
    ts: bool = False
    type: Literal['normal', 'failure', 'dropset'] = 'normal'

    @field_validator('reps', 'rpe', mode='before')
    @classmethod
    def numbers_only(cls, value):
        if isinstance(value, bool):
            raise ValueError('Expected a number')
        return value

    @field_validator('rpe')
    @classmethod
    def half_steps(cls, value):
        if value is not None and value * 2 != int(value * 2):
            raise ValueError('RPE must use half-point steps')
        return value


class ProposedMovement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    exercise_template_id: str = Field(min_length=1, max_length=200)
    notes: str = Field(default='', max_length=500)
    sets: list[ProposedSet] = Field(min_length=1, max_length=50)


class ProposedSession(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)
    exercises: list[ProposedMovement] = Field(min_length=1, max_length=30)


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['plan-proposal-v1']
    title: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=500)
    sessions: list[ProposedSession] = Field(min_length=1, max_length=14)


def proposal_id(conversation_id: UUID, turn_id: UUID) -> str:
    return str(uuid5(NAMESPACE_URL, f'hevy-fatigue:plan-proposal:{conversation_id}:{turn_id}'))


def _problems(error: ValidationError):
    return [f"{'.'.join(str(p) for p in e['loc']) or 'proposal'}: {e['msg']}"[:300] for e in error.errors()][:MAX_ISSUES]


def _titles(conn):
    """Movement titles known to this install: exercise cache, then logged sets, then saved plans."""
    titles = {}
    for sql in ('SELECT id, title FROM hevy_exercise_cache',
                'SELECT DISTINCT exercise_template_id, exercise_title FROM logged_sets WHERE exercise_title IS NOT NULL'):
        for key, title in conn.execute(sql):
            titles.setdefault(key, title)
    for row in conn.execute('SELECT document FROM mesocycles'):
        for week in json.loads(row['document']).get('weeks', []):
            for session in week.get('sessions', []):
                for ex in session.get('exercises', []):
                    titles.setdefault(ex['exercise_template_id'], ex['title'])
    return titles


def _sets_text(sets):
    groups = []
    for s in sets:
        label = f"{s['reps']}" + (f" @{s['rpe']:g}" if s.get('rpe') is not None else '') + (' TS' if s.get('ts') else '')
        if groups and groups[-1][0] == label:
            groups[-1][1] += 1
        else:
            groups.append([label, 1])
    return ', '.join(f'{n}×{label}' for label, n in groups)


movement_titles = _titles
sets_text = _sets_text
problems = _problems


def _movements(sessions):
    """{template id: (title, [set signature, ...])} across a plan or proposal, in order."""
    found = {}
    for session in sessions:
        for ex in session['exercises']:
            _, sets = found.setdefault(ex['exercise_template_id'], (ex['title'], []))
            sets.extend(ex['sets'])
    return found


def _diff(conn, sessions):
    active = conn.execute('SELECT id, document FROM mesocycles WHERE active = 1 AND archived = 0').fetchone()
    if active is None:
        return dict(active_plan=None, added=[], removed=[], changed=[])
    document = json.loads(active['document'])
    old = _movements(s for week in document['weeks'] for s in week['sessions'])
    new = _movements(sessions)
    return dict(
        active_plan=dict(id=active['id'], name=document['name']),
        added=[title for key, (title, _) in new.items() if key not in old],
        removed=[title for key, (title, _) in old.items() if key not in new],
        changed=[dict(title=title, was=_sets_text(old[key][1]), now=_sets_text(sets))
                 for key, (title, sets) in new.items()
                 if key in old and _sets_text(old[key][1]) != _sets_text(sets)])


def _analyse(conn, text):
    """(report, PlanInput or None, canonical proposal or None). Pure reads."""
    if not isinstance(text, str) or len(text) > MAX_REPLY_CHARS:
        return dict(found=False), None, None
    blocks = BLOCK.findall(text)
    if not blocks:
        return dict(found=False), None, None
    report = dict(found=True, valid=False, issues=[])
    if len(blocks) > 1:
        report['issues'].append('Only one proposal per reply is supported.')
        return report, None, None
    if len(blocks[0]) > MAX_BLOCK_CHARS:
        report['issues'].append('The proposal is too large to review.')
        return report, None, None
    try:
        proposal = Proposal.model_validate(json.loads(blocks[0]))
    except json.JSONDecodeError:
        report['issues'].append('The proposal is not valid JSON.')
        return report, None, None
    except ValidationError as exc:
        report['issues'].extend(_problems(exc))
        return report, None, None
    titles = _titles(conn)
    unknown = sorted({e.exercise_template_id for s in proposal.sessions for e in s.exercises} - set(titles))
    if unknown:
        report['issues'].append('Unknown movement id(s) (not in your exercise cache, history or plans): ' + ', '.join(unknown[:5]))
        return report, None, None
    sessions = [dict(name=s.name, exercises=[
        dict(exercise_template_id=e.exercise_template_id, title=titles[e.exercise_template_id], notes=e.notes,
             sets=[x.model_dump() for x in e.sets]) for e in s.exercises]) for s in proposal.sessions]
    stamp = hashlib.sha256(json.dumps([proposal.title, sessions], sort_keys=True).encode()).hexdigest()[:8]
    try:
        data = mesocycles.PlanInput(
            name=proposal.title, notes='AI proposal, saved as a draft and not applied: ' + proposal.rationale,
            weeks=[dict(name='Week 1', sessions=[dict(
                id=f'ai-{stamp}-{index}', name=s['name'], exercises=[
                    dict(exercise_template_id=e['exercise_template_id'], title=e['title'], notes=e['notes'],
                         sets=[dict(reps=x['reps'], rpe=x['rpe'], ts=x['ts'], type=x['type']) for x in e['sets']])
                    for e in s['exercises']]) for index, s in enumerate(sessions, 1)])])
    except ValidationError as exc:
        report['issues'].extend(_problems(exc))
        return report, None, None
    canonical = dict(version=proposal.version, title=proposal.title, rationale=proposal.rationale, sessions=sessions)
    report.update(valid=True, title=proposal.title, rationale=proposal.rationale, diff=_diff(conn, sessions),
                  sessions=[dict(s, exercises=[dict(e, summary=_sets_text(e['sets'])) for e in s['exercises']]) for s in sessions])
    return report, data, canonical


analyse = _analyse  # (report, PlanInput or None, canonical or None) for a reply. Pure reads.


def preview(text):
    """Validate and describe a reply's proposal without writing anything."""
    with get_db() as conn:
        return _analyse(conn, text)[0]


def save_draft(text, conversation_id: UUID, turn_id: UUID):
    """Create one inactive draft plan plus provenance atomically; repeating the call returns the first save."""
    identifier = proposal_id(conversation_id, turn_id)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        saved = conn.execute('SELECT plan_id FROM plan_proposals WHERE id = ?', (identifier,)).fetchone()
        if saved:
            return dict(already_saved=True, proposal_id=identifier, plan=mesocycles.view(conn, saved['plan_id']))
        report, data, canonical = _analyse(conn, text)
        if not report.get('found'):
            raise ProposalError('No plan proposal was found in that reply.')
        if not report['valid']:
            raise ProposalError('This proposal cannot be saved: ' + ' '.join(report['issues']))
        plan_id = mesocycles.insert_draft(conn, data)
        conn.execute('INSERT INTO plan_proposals (id, conversation_id, turn_id, plan_id, proposed, saved_at) VALUES (?, ?, ?, ?, ?, ?)',
                     (identifier, str(conversation_id), str(turn_id), plan_id, json.dumps(canonical),
                      datetime.now(timezone.utc).isoformat()))
        return dict(already_saved=False, proposal_id=identifier, plan=mesocycles.view(conn, plan_id))
