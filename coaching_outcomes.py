"""Read-only outcome review of the coach's saved week proposals, for AI coaching reports.

Pure: no database, Hevy or provider access. The caller reads the logger's plan_proposals,
mesocycles and mesocycle_completions rows (coaching.local_evidence) and the merged sessions;
this module states what happened afterwards: how far the saved plan got, whether it was edited,
and how the proposed movements' progress status stood before the save and now. It is descriptive.
It cannot show that a proposal caused anything, and it never changes a plan.
"""
from datetime import date, timedelta
import json

import coaching_progress

MAX_PROPOSALS = 5
MAX_MOVEMENTS = 8
MIN_DAYS = coaching_progress.PERIOD_DAYS
LIMITATIONS = (
    f'proposal_outcomes lists the latest {MAX_PROPOSALS} saved week proposals. stage and sessions come from the '
    'saved plan and its completions; a proposal that was never started, or was edited before use, is not a failed '
    f'one. before/after progress is shown only {MIN_DAYS} days or more after the first completed session. before is the '
    'movement’s progress status as of the day before the save (UTC date); after covers everything trained '
    'since, not only the proposed week. Neither shows that a proposal caused a change, and later training, '
    'deloads, illness and rep-range changes all confound it.',
)


def _json(value):
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _movements(proposed):
    """[(exercise id, title, [low, high] reps)] in proposal order, deduplicated."""
    found = {}
    for session in proposed.get('sessions') or []:
        for movement in session.get('exercises') or []:
            key = movement.get('exercise_template_id')
            if not key:
                continue
            entry = found.setdefault(key, dict(title=movement.get('title') or key, reps=[]))
            entry['reps'].extend(s['reps'] for s in movement.get('sets') or [] if isinstance(s.get('reps'), int))
    return [(key, v['title'], [min(v['reps']), max(v['reps'])] if v['reps'] else None) for key, v in found.items()]


def _planned_sessions(plan):
    document = _json(plan['document'])
    return [s['id'] for week in document.get('weeks') or [] for s in week.get('sessions') or []
            if s.get('exercises') and s.get('id')]


def _stage(plan, planned, trained, skipped):
    if plan is None:
        return 'plan_removed'
    resolved = trained | skipped
    if resolved and planned and set(planned) <= resolved:
        return 'finished_with_skips' if skipped & set(planned) else 'completed'
    if resolved:
        return 'in_progress'
    if plan['active']:
        return 'active_not_started'
    return 'archived_unused' if plan['archived'] else 'not_started'


def _view(block):
    if block['status'] == 'insufficient_evidence':
        return dict(status=block['status'], reason=block['reason'])
    return dict(status=block['status'], change_pct=block['change_pct'],
                median_anchor_reps=block['recent']['median_anchor_reps'],
                entered_share=block['recent']['entered_share'])


def review(proposals, plans, completions, ordered, today):
    """Latest saved proposals, newest first.

    proposals: rows with id, plan_id, proposed (JSON), saved_at. plans: {plan_id: row with document,
    active, archived, revision}. completions: {plan_id: [rows with session_id, workout_start]}."""
    result = []
    for row in sorted(proposals, key=lambda r: (str(r['saved_at']), str(r['id'])), reverse=True)[:MAX_PROPOSALS]:
        proposed, plan = _json(row['proposed']), plans.get(row['plan_id'])
        saved, done_rows = _day(row['saved_at']), completions.get(row['plan_id'], [])
        skips = [c for c in done_rows if c.get('outcome') == 'skipped']
        trained_rows = [c for c in done_rows if c.get('outcome') != 'skipped']
        done = {c['session_id'] for c in trained_rows}
        skipped = {c['session_id'] for c in skips}
        dates = sorted(d for d in (_day(c['workout_start']) for c in trained_rows) if d)
        moves = _movements(proposed)[:MAX_MOVEMENTS]
        planned = _planned_sessions(plan) if plan else None
        item = dict(
            proposal_id=row['id'], title=proposed.get('title'), saved_on=str(saved) if saved else None,
            stage=_stage(plan, planned, done, skipped), edited_since_save=bool(plan and plan['revision'] > 1),
            sessions_planned=None if planned is None else len(planned), sessions_completed=len(done), sessions_skipped=len(skipped),
            first_completed=str(dates[0]) if dates else None, last_completed=str(dates[-1]) if dates else None)
        if not done:
            comparison = 'not_executed'
        elif dates and (today - dates[0]).days < MIN_DAYS:
            comparison = 'too_early'
        else:
            comparison = 'available'
        item['comparison'] = comparison
        if dates:
            item['days_since_first_completion'] = (today - dates[0]).days
        ids = [key for key, _, _ in moves]
        if comparison == 'available' and saved:
            before_date = saved - timedelta(days=1)
            before = coaching_progress.assess_at(ordered, before_date, ids)
            after = coaching_progress.assess_at(ordered, today, ids)
            item.update(before_as_of=str(before_date), after_as_of=str(today))
            item['movements'] = [dict(exercise_id=key, title=title, proposed_reps=reps,
                                      before=_view(before[key]), after=_view(after[key])) for key, title, reps in moves]
        else:
            item['movements'] = [dict(exercise_id=key, title=title, proposed_reps=reps) for key, title, reps in moves]
        result.append(item)
    return result
