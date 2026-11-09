"""AI coach plan changes to an existing microcycle, applied only on the athlete's Accept tap (ADR 0002).

The coach describes a change in a ```plan-change-v1 block: swap a movement, replace its sets, add or
remove a movement, on days that are not yet trained or skipped. Parsing and preview write nothing.
Accept applies the change to that plan and records the previous document in one transaction, so it
can be undone. A change is pinned to the plan revision the coach saw; if the plan changed since, it
is refused. Trained and skipped days are never changed, weights are never set (an athlete's own
fixed weights are kept only where a movement keeps its sets), nothing is activated, and Hevy is
never contacted. Reply text is untrusted: fields are length-limited and titles come from local records.
"""
import json
import re
from datetime import datetime, timezone
from typing import Annotated, Literal, Union
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .database import get_db
from . import mesocycles, plan_proposals
from .plan_proposals import ProposedSet

FENCE = 'plan-change-v1'
MAX_REPLY_CHARS = plan_proposals.MAX_REPLY_CHARS
MAX_BLOCK_CHARS = 20_000
MAX_CHANGES = 30
BLOCK = re.compile(r'```' + re.escape(FENCE) + r'[ \t]*\r?\n(.*?)```', re.DOTALL)


class ChangeError(Exception):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


class _Op(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: int = Field(ge=1, le=14)
    exercise_template_id: str = Field(min_length=1, max_length=200)


class SetSets(_Op):
    op: Literal['set_sets']
    sets: list[ProposedSet] = Field(min_length=1, max_length=50)


class Replace(_Op):
    op: Literal['replace']
    new_exercise_template_id: str = Field(min_length=1, max_length=200)
    sets: list[ProposedSet] | None = Field(default=None, min_length=1, max_length=50)
    notes: str = Field(default='', max_length=500)


class Add(_Op):
    op: Literal['add']
    sets: list[ProposedSet] = Field(min_length=1, max_length=50)
    notes: str = Field(default='', max_length=500)


class Remove(_Op):
    op: Literal['remove']


Change = Annotated[Union[SetSets, Replace, Add, Remove], Field(discriminator='op')]


class PlanChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['plan-change-v1']
    plan_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=500)
    changes: list[Change] = Field(min_length=1, max_length=MAX_CHANGES)


def change_id(conversation_id: UUID, turn_id: UUID) -> str:
    return str(uuid5(NAMESPACE_URL, f'hevy-fatigue:plan-change:{conversation_id}:{turn_id}'))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse(text):
    """(report, PlanChange or None). Pure."""
    if not isinstance(text, str) or len(text) > MAX_REPLY_CHARS:
        return dict(found=False), None
    blocks = BLOCK.findall(text)
    if not blocks:
        return dict(found=False), None
    report = dict(found=True, valid=False, stale=False, issues=[])
    if len(blocks) > 1:
        report['issues'].append('Only one plan change per reply is supported.')
        return report, None
    if len(blocks[0]) > MAX_BLOCK_CHARS:
        report['issues'].append('The plan change is too large to review.')
        return report, None
    try:
        change = PlanChange.model_validate(json.loads(blocks[0]))
    except json.JSONDecodeError:
        report['issues'].append('The plan change is not valid JSON.')
        return report, None
    except ValidationError as exc:
        report['issues'].extend(plan_proposals.problems(exc))
        return report, None
    report.update(title=change.title, rationale=change.rationale)
    return report, change


def _set(s, weight=None):
    return dict(reps=s.reps, rpe=s.rpe, weight_kg=weight, type=s.type, ts=s.ts)


def _fixed(sets):
    return any(s.get('weight_kg') is not None for s in sets)


def _apply(conn, change, report):
    """Apply the change to a copy of the plan. Returns (row, new document, touched session ids) or None
    with report['issues'] filled. Pure reads."""
    issues = report['issues']
    row = conn.execute('SELECT * FROM mesocycles WHERE id = ?', (change.plan_id,)).fetchone()
    if row is None:
        issues.append('That plan no longer exists.')
        return None
    document = json.loads(row['document'])
    report['plan'] = dict(id=row['id'], name=document['name'], active=bool(row['active']), revision=row['revision'])
    if row['archived']:
        issues.append('That plan has been deleted, so it cannot be changed.')
        return None
    if row['revision'] != change.revision:
        report['stale'] = True
        issues.append('This plan has been edited since the coach wrote this change. Ask the coach to look at the current plan again.')
        return None
    titles = plan_proposals.movement_titles(conn)
    done = {r['session_id']: r['outcome'] for r in conn.execute(
        'SELECT session_id, outcome FROM mesocycle_completions WHERE mesocycle_id = ?', (row['id'],))}
    sessions = document['weeks'][0]['sessions']
    days, touched = {}, []
    for op in change.changes:
        where = f'Day {op.day}'
        if op.day > len(sessions):
            issues.append(f'{where} does not exist in this plan.')
            continue
        session = sessions[op.day - 1]
        where = f"Day {op.day} ({session['name']})"
        if session['id'] in done:
            issues.append(f"{where} is already {'skipped' if done[session['id']] == 'skipped' else 'trained'}; finished days are never changed.")
            continue
        exercises = session['exercises']
        found = [i for i, ex in enumerate(exercises) if ex['exercise_template_id'] == op.exercise_template_id]
        lines = days.setdefault(op.day, dict(day=op.day, name=session['name'], changes=[]))['changes']
        if op.op == 'add':
            if op.exercise_template_id not in titles:
                issues.append(f'{where}: unknown movement id {op.exercise_template_id}.')
                continue
            if found:
                issues.append(f'{where} already has {exercises[found[0]]["title"]}; change its sets instead.')
                continue
            sets = [_set(s) for s in op.sets]
            title = titles[op.exercise_template_id]
            exercises.append(dict(exercise_template_id=op.exercise_template_id, title=title, notes=op.notes, sets=sets))
            lines.append(f'Add {title}: {plan_proposals.sets_text(sets)}')
        else:
            if not found:
                issues.append(f'{where} does not include movement {op.exercise_template_id}.')
                continue
            if len(found) > 1:
                issues.append(f'{where} has {exercises[found[0]]["title"]} more than once, so the change is ambiguous.')
                continue
            index = found[0]
            old = exercises[index]
            was = plan_proposals.sets_text(old['sets'])
            if op.op == 'remove':
                exercises.pop(index)
                lines.append(f"Remove {old['title']} (was {was})")
            elif op.op == 'set_sets':
                sets = [_set(s, old['sets'][i].get('weight_kg') if i < len(old['sets']) else None) for i, s in enumerate(op.sets)]
                exercises[index] = dict(old, sets=sets)
                lines.append(f"{old['title']}: {was} → {plan_proposals.sets_text(sets)}"
                             + (' (your fixed weights kept)' if _fixed(sets) else ''))
            else:
                new = op.new_exercise_template_id
                if new not in titles:
                    issues.append(f'{where}: unknown movement id {new}.')
                    continue
                if new != old['exercise_template_id'] and any(ex['exercise_template_id'] == new for ex in exercises):
                    issues.append(f'{where} already has {titles[new]}.')
                    continue
                sets = [_set(s) for s in op.sets] if op.sets else [dict(s, weight_kg=None) for s in old['sets']]
                exercises[index] = dict(exercise_template_id=new, title=titles[new], notes=op.notes, sets=sets)
                lines.append(f"Swap {old['title']} → {titles[new]}: {plan_proposals.sets_text(sets)}"
                             + (' (fixed weights cleared; loads come from automatic planning)' if _fixed(old['sets']) else ''))
        if session['id'] not in touched:
            touched.append(session['id'])
    if issues:
        return None
    try:
        data = mesocycles.PlanInput.model_validate(document)
    except ValidationError as exc:
        issues.extend(plan_proposals.problems(exc))
        return None
    report['days'] = [days[d] for d in sorted(days)]
    return row, data.model_dump(exclude={'revision', 'rpe_assignments'}), touched


def _analyse(conn, text):
    report, change = _parse(text)
    if change is None:
        return report, None, None
    applied = _apply(conn, change, report)
    if applied is None:
        return report, None, None
    report['valid'] = True
    return report, change, applied


def _undo_problem(conn, row):
    plan = conn.execute('SELECT revision, archived FROM mesocycles WHERE id = ?', (row['plan_id'],)).fetchone()
    if plan is None or plan['archived']:
        return 'That plan has been deleted.'
    if plan['revision'] != row['applied_revision']:
        return 'The plan was edited after this change, so it cannot be undone here. Edit it in the builder instead.'
    touched = json.loads(row['touched'])
    if touched:
        marks = ','.join('?' * len(touched))
        if conn.execute(f'SELECT 1 FROM mesocycle_completions WHERE mesocycle_id = ? AND session_id IN ({marks}) LIMIT 1',
                        (row['plan_id'], *touched)).fetchone():
            return 'A changed day has been trained or skipped since, so this change cannot be undone.'
    return None


def _recorded(conn, row):
    """Report for a change that was accepted earlier, from what was stored at the time."""
    report = json.loads(row['summary'])
    problem = None if row['undone_at'] else _undo_problem(conn, row)
    report.update(found=True, valid=True, stale=False, issues=[], change_id=row['id'], applied_at=row['applied_at'],
                  status='undone' if row['undone_at'] else 'applied', undone_at=row['undone_at'],
                  can_undo=not row['undone_at'] and problem is None, undo_problem=problem)
    return report


def preview(text, conversation_id: UUID, turn_id: UUID):
    """Describe a reply's plan change day by day without writing anything."""
    identifier = change_id(conversation_id, turn_id)
    with get_db() as conn:
        row = conn.execute('SELECT * FROM plan_changes WHERE id = ?', (identifier,)).fetchone()
        if row:
            return _recorded(conn, row)
        report = _analyse(conn, text)[0]
        if report.get('found'):
            report.update(change_id=identifier, status='pending')
        return report


def accept(text, conversation_id: UUID, turn_id: UUID):
    """The athlete's Accept tap: apply the change and keep the previous plan, atomically. Repeats return the first result."""
    identifier = change_id(conversation_id, turn_id)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM plan_changes WHERE id = ?', (identifier,)).fetchone()
        if row:
            return dict(already_applied=True, change=_recorded(conn, row), plan=mesocycles.view(conn, row['plan_id']))
        report, change, applied = _analyse(conn, text)
        if not report.get('found'):
            raise ChangeError('No plan change was found in that reply.')
        if not report['valid']:
            raise ChangeError('This change cannot be applied: ' + ' '.join(report['issues']), 409 if report['stale'] else 422)
        plan, document, touched = applied
        summary = dict(title=report['title'], rationale=report['rationale'], plan=report['plan'], days=report['days'])
        now = _now()
        conn.execute('UPDATE mesocycles SET document = ?, revision = revision + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                     (json.dumps(document), plan['id']))
        conn.execute('INSERT INTO plan_changes (id, conversation_id, turn_id, plan_id, title, base_revision, applied_revision, '
                     'previous_document, proposed, summary, touched, applied_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (identifier, str(conversation_id), str(turn_id), plan['id'], report['title'], plan['revision'],
                      plan['revision'] + 1, plan['document'], change.model_dump_json(), json.dumps(summary),
                      json.dumps(touched), now))
        row = conn.execute('SELECT * FROM plan_changes WHERE id = ?', (identifier,)).fetchone()
        return dict(already_applied=False, change=_recorded(conn, row), plan=mesocycles.view(conn, plan['id']))


def undo(identifier: str):
    """Put the plan back exactly as it was before an accepted change, if nothing has moved on since."""
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM plan_changes WHERE id = ?', (identifier,)).fetchone()
        if row is None:
            raise ChangeError('That plan change was not found.', 404)
        if row['undone_at']:
            raise ChangeError('That change has already been undone.', 409)
        problem = _undo_problem(conn, row)
        if problem:
            raise ChangeError(problem, 409)
        conn.execute('UPDATE mesocycles SET document = ?, revision = revision + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                     (row['previous_document'], row['plan_id']))
        conn.execute('UPDATE plan_changes SET undone_at = ? WHERE id = ?', (_now(), identifier))
        row = conn.execute('SELECT * FROM plan_changes WHERE id = ?', (identifier,)).fetchone()
        return dict(change=_recorded(conn, row), plan=mesocycles.view(conn, row['plan_id']))
