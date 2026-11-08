"""Read-only per-movement progress evidence for AI coaching reports.

Pure: no database, Hevy or provider access. From the sessions coaching.build_report has already
merged, it follows each movement's e1RM (heaviest recorded-RPE set, the stress index's anchor)
and compares the last 28 days with the 28 days before. It states what the logs show and what
could confound it. It never recommends a change; the coach and the athlete decide.

The thresholds are product heuristics sized to RPE rounding error, not established science.
"""
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

from rackbook import stress_index

VERSION = 'rackbook-progress-v1'
PERIOD_DAYS = 28            # the last 28 days are compared with the 28 days before
MIN_RECENT_EXPOSURES = 3
MIN_PREVIOUS_EXPOSURES = 2
MIN_RPE = 7.0               # lighter anchor sets give e1RMs too uncertain to trend
NOISE_PCT = 2.5             # about one half-step of RPE misjudgement at 5 reps
DECLINE_PCT = 5.0
REP_SHIFT = 3               # anchor reps moving this far makes e1RM comparison less reliable
HIGH_REPS = 12
RECENT_SHOWN = 6
MAX_FLAGS = 8
SUPPORTED = ('progressing', 'flat', 'declining')
DESCRIPTION = (
    f'Per-movement progress from e1RM (heaviest recorded-RPE working set, RPE {MIN_RPE:g} or harder) in the '
    f'last {PERIOD_DAYS} days against the {PERIOD_DAYS} days before. progressing: the median e1RM rose '
    f'{NOISE_PCT:g}% or more. declining: it fell {DECLINE_PCT:g}% or more. flat: anything between, which is within '
    'ordinary RPE rounding. insufficient_evidence: too few usable exposures to say. These are descriptive '
    'comparisons, not diagnoses; a flat or declining movement is a prompt to look at the confounders, not a '
    'reason by itself to change the program.')
LIMITATIONS = (
    'Progress status uses the e1RM implied by each session’s heaviest recorded-RPE set (rep-max table, '
    f'RPE {MIN_RPE:g} or harder); blank-RPE sets, lighter anchors and loads that cannot be known (bodyweight or '
    'manual) are not used, so some movements will read insufficient_evidence. The thresholds are product '
    'heuristics, not established science. e1RM from sets above about 12 reps is least reliable, and for '
    'weighted bodyweight movements a percentage of added load is not a percentage of a true max.',
    'Progress comparisons are confounded by deloads, illness, time off, a change of rep range or technique, '
    'a different exercise variation and imported RPEs of weaker provenance (entered_share). A flat or declining '
    'status does not show why, and does not show that the program failed.',
)


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def collect(ordered, today):
    """{exercise_id: points/unusable/low_effort} for sessions in the two comparison periods.

    A point is one exposure whose anchor set is usable; sessions on `today` are included."""
    first = today - timedelta(days=2 * PERIOD_DAYS - 1)
    found = {}
    for session in ordered:
        day = _day(session['date'])
        if day is None or not first <= day <= today:
            continue
        groups = defaultdict(list)
        for s in session['sets']:
            if s['role'] != 'warmup' and not s.get('conditioning'):
                groups[s['exercise_id']].append(s)
        for key, sets in groups.items():
            entry = found.setdefault(key, dict(points=[], unusable=0, low_effort=0))
            anchor = stress_index.session_anchor(
                [dict(weight_kg=s['weight_kg'], reps=s['reps'], rpe=s['actual_rpe']) for s in sets])
            if anchor is None:
                entry['unusable'] += 1
            elif anchor['rpe'] < MIN_RPE:
                entry['low_effort'] += 1
            else:
                entry['points'].append(dict(
                    date=day, e1rm=anchor['e1rm'], weight_kg=anchor['weight_kg'], reps=anchor['reps'],
                    rpe=anchor['rpe'], entered=sets[anchor['index']].get('rpe_source') == 'entered'))
    return found


def _period(points):
    return dict(exposures=len(points), median_e1rm=round(median(p['e1rm'] for p in points), 1),
                median_anchor_reps=median(p['reps'] for p in points),
                entered_share=round(sum(p['entered'] for p in points) / len(points), 2))


def assess(entry, today):
    """One movement's progress block from its collect() entry. Pure."""
    points = entry['points']
    block = dict(eligible_exposures=len(points), unusable_exposures=entry['unusable'],
                 low_effort_exposures=entry['low_effort'])  # version and period live in the summary
    boundary = today - timedelta(days=PERIOD_DAYS - 1)
    recent = [p for p in points if p['date'] >= boundary]
    previous = [p for p in points if p['date'] < boundary]
    if len(recent) < MIN_RECENT_EXPOSURES:
        return dict(block, status='insufficient_evidence', reason='too_few_recent_exposures',
                    recent_exposures=len(recent))
    if len(previous) < MIN_PREVIOUS_EXPOSURES:
        return dict(block, status='insufficient_evidence', reason='too_little_earlier_history',
                    recent_exposures=len(recent), previous_exposures=len(previous))
    now, before = median(p['e1rm'] for p in recent), median(p['e1rm'] for p in previous)
    change = round((now / before - 1) * 100, 6)  # thresholds are inclusive; ignore float dust
    status = 'progressing' if change >= NOISE_PCT else 'declining' if change <= -DECLINE_PCT else 'flat'
    best = max(points, key=lambda p: (p['e1rm'], p['date']))
    return dict(
        block, status=status, change_pct=round(change, 1), recent=_period(recent), previous=_period(previous),
        rep_range_shift=abs(median(p['reps'] for p in recent) - median(p['reps'] for p in previous)) >= REP_SHIFT,
        high_rep_exposures=sum(p['reps'] > HIGH_REPS for p in points),
        best_e1rm=round(best['e1rm'], 1), best_date=str(best['date']),
        exposures_since_best=sum(p['date'] > best['date'] for p in points),
        recent_points=[dict(date=str(p['date']), e1rm=round(p['e1rm'], 1), weight_kg=p['weight_kg'],
                            reps=p['reps'], rpe=p['rpe']) for p in points[-RECENT_SHOWN:]])


def assess_at(ordered, as_of, exercise_ids):
    """{exercise_id: progress block} as the logs stood on `as_of` (sessions after it are ignored)."""
    found = collect(ordered, as_of)
    empty = dict(points=[], unusable=0, low_effort=0)
    return {key: assess(found.get(key, empty), as_of) for key in exercise_ids}


def attach(exercises, ordered, today):
    """Add exercise['progress'] to each report exercise and return the report-level summary."""
    blocks = assess_at(ordered, today, [exercise['exercise_id'] for exercise in exercises.values()])
    for exercise in exercises.values():
        exercise['progress'] = blocks[exercise['exercise_id']]
    return summary(exercises)


def summary(exercises):
    counts = {status: 0 for status in (*SUPPORTED, 'insufficient_evidence')}
    flagged = []
    for exercise in exercises.values():
        progress = exercise.get('progress') or {}
        status = progress.get('status')
        if status in counts:
            counts[status] += 1
        if status in ('flat', 'declining'):
            flagged.append(dict(
                exercise_id=exercise['exercise_id'], title=exercise['title'], status=status,
                change_pct=progress['change_pct'], recent_exposures=progress['recent']['exposures'],
                rep_range_shift=progress['rep_range_shift'], entered_share=progress['recent']['entered_share']))
    flagged.sort(key=lambda f: (f['status'] != 'declining', -f['recent_exposures'], f['title']))
    return dict(model_version=VERSION, description=DESCRIPTION, movements=counts,
                attention=flagged[:MAX_FLAGS], attention_total=len(flagged))
