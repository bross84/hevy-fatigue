"""Personal joint baselines, rise counts, coaching-call state and movement evidence (#154).

Each region (upper, lower) gets a "usual" rating: the most common check-in rating over the previous
28 days, using normal days only. Check-ins that were part of a flagged stretch never count toward
usual, so a lasting flare cannot quietly become the athlete's normal. Usual moves up only when the
athlete chooses "new normal" in a coaching call; it moves down on its own.

A "session" is a check-in. 3 of the last 7 check-ins (within 14 days) above usual is a notice: a
coaching call is due and that region's lifts are held. 5 of the last 10 (within 21 days) is a review:
the call focuses on the movement. A rating of 3 or 4 keeps its own existing advisory and is not
handled here, except that it ends a "carry on" period early.

The fatigue trial keeps its own joint rule; this module never touches trial records.
"""
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, Field, model_validator

from rackbook.config import database_path
from rackbook.local_day import local_day

BASELINE_DAYS = 28
MIN_BASELINE = 7
NOTICE = (3, 7, 14)     # above-usual check-ins, out of the last N check-ins, within D days
REVIEW = (5, 10, 21)
HIGH_RATING = 3
CARRY_ON_DAYS = 7
EVIDENCE_DAYS = 84
EVIDENCE_MIN = 3
EVIDENCE_SETTLED = 6    # lines below this many after-lift check-ins are an "early read"
REGIONS = {
    'upper': dict(field='joint_upper', label='Upper', patterns=('push', 'pull')),
    'lower': dict(field='joint_lower', label='Lower', patterns=('knee', 'hip')),
}
PATTERN_COLUMNS = dict(knee='pct_quad_dom', hip='pct_posterior', push='pct_upper_push', pull='pct_upper_pull')
OUTCOMES = ('new_normal', 'carry_on', 'change', 'not_now')


def _usual(ratings):
    """Most common rating; a tie goes to the lower rating (the cautious side)."""
    if len(ratings) < MIN_BASELINE:
        return None
    counts = Counter(ratings)
    top = max(counts.values())
    return min(r for r, n in counts.items() if n == top)


def _count(history, size, days, today):
    recent = [h for h in history[-size:] if h['date'] > today - timedelta(days=days)]
    return sum(1 for h in recent if h['above']), recent


def replay_region(checkins, decisions, today):
    """checkins: [(date, rating or None)], decisions: this region's decisions oldest first.

    Replays day by day so flagged days, consent and restarts are applied in the order they happened.
    """
    rows = sorted((d, r) for d, r in checkins if r is not None and d <= today)
    decisions = sorted((x for x in decisions if x['decided_on'] <= today), key=lambda x: (x['decided_on'], x['created_at']))
    flare, history = set(), []
    level, stretch_start = 'none', None
    for d, rating in rows:
        made = [x for x in decisions if x['decided_on'] < d]
        consent = next((x for x in reversed(made) if x['outcome'] == 'new_normal'), None)
        restart = next((x['decided_on'] for x in reversed(made) if x['outcome'] in ('new_normal', 'change')), None)
        window = []
        for dd, rr in rows:
            if not (d - timedelta(days=BASELINE_DAYS) <= dd < d):
                continue
            consented = consent is not None and dd <= consent['decided_on']
            if dd in flare and not consented:
                continue
            window.append(max(rr, consent['level']) if consented and consent.get('level') is not None else rr)
        usual = _usual(window)
        above = usual is not None and rating > usual
        history.append(dict(date=d, rating=rating, usual=usual, above=above))
        counted = [h for h in history if restart is None or h['date'] > restart]
        notice, notice_rows = _count(counted, NOTICE[1], NOTICE[2], d)
        review, review_rows = _count(counted, REVIEW[1], REVIEW[2], d)
        level = 'review' if review >= REVIEW[0] else 'notice' if notice >= NOTICE[0] else 'none'
        if level != 'none':
            flare.update(h['date'] for h in notice_rows + review_rows if h['above'])
            stretch_start = stretch_start or d
        else:
            stretch_start = None
    last = history[-1] if history else None
    # A new normal or a change made today (after today's check-in) restarts the count straight away.
    restart = next((x['decided_on'] for x in reversed(decisions) if x['outcome'] in ('new_normal', 'change')), None)
    counted = [h for h in history if restart is None or h['date'] > restart]
    notice_count = _count(counted, NOTICE[1], NOTICE[2], today)[0]
    review_count = _count(counted, REVIEW[1], REVIEW[2], today)[0]
    level = 'review' if review_count >= REVIEW[0] else 'notice' if notice_count >= NOTICE[0] else 'none'
    if level == 'none':
        stretch_start = None
    current_usual = last['usual'] if last else None
    # Usual for the next check-in, so the dashboard shows the bar today's rating would be compared with.
    return dict(usual=current_usual, today=dict(last, date=str(last['date'])) if last and last['date'] == today else None,
                level=level, stretch_start=str(stretch_start) if stretch_start else None, notice_count=notice_count, review_count=review_count,
                recent=[dict(date=str(h['date']), rating=h['rating'], above=h['above'], flare=h['date'] in flare)
                        for h in history[-14:]],
                baseline_status='tracking' if current_usual is not None else 'collecting')


def call_state(region_state, decisions, ratings_after, today):
    """Whether a call is due for one region, given its replayed state and decisions."""
    if region_state['level'] == 'none':
        return dict(due=False, covered_until=None)
    carry = next((x for x in sorted(decisions, key=lambda x: (x['decided_on'], x['created_at']), reverse=True)
                  if x['outcome'] == 'carry_on' and x['until'] and x['until'] > today), None)
    if carry and not any(r >= HIGH_RATING for d, r in ratings_after if d > carry['decided_on']):
        return dict(due=False, covered_until=str(carry['until']))
    return dict(due=True, covered_until=None)


def status(checkins, decisions, today):
    """checkins: [{'date','joint_upper','joint_lower'}]; decisions: rows from joint_call_decisions."""
    regions, due = {}, []
    for key, meta in REGIONS.items():
        mine = [x for x in decisions if x['region'] == key]
        pairs = [(c['date'], c.get(meta['field'])) for c in checkins]
        state = replay_region(pairs, mine, today)
        call = call_state(state, mine, [(d, r) for d, r in pairs if r is not None], today)
        last = max(mine, key=lambda x: (x['decided_on'], x['created_at'])) if mine else None
        regions[key] = dict(label=meta['label'], patterns=list(meta['patterns']), **state, call_due=call['due'],
                            carry_on_until=call['covered_until'], hold=call['due'],
                            last_decision=_public_decision(last) if last else None)
        if call['due']:
            due.append(key)
    kind = 'review' if any(regions[k]['level'] == 'review' for k in due) else 'notice'
    call = None
    if due:
        # A new conversation per stretch and per earlier decision, so a returning call starts fresh.
        starts = '|'.join(f"{k}:{regions[k]['stretch_start']}:{(regions[k]['last_decision'] or {}).get('id')}" for k in due)
        call = dict(regions=due, kind=kind, id=str(uuid5(NAMESPACE_URL, f'hevy-fatigue:joint-call:{kind}:{starts}')))
    held = sorted({p for k in due for p in REGIONS[k]['patterns']})
    return dict(date=str(today), regions=regions, call=call, held_patterns=held)


def accepted_level(region_state):
    """The level a "new normal" accepts: the most common elevated rating in the current stretch."""
    raised = [h['rating'] for h in region_state['recent'] if h['above']]
    if not raised:
        return None
    counts = Counter(raised)
    top = max(counts.values())
    return min(r for r, n in counts.items() if n == top)


def _public_decision(x):
    return dict(id=x['id'], region=x['region'], decided_on=str(x['decided_on']), outcome=x['outcome'],
                until=str(x['until']) if x['until'] else None, level=x.get('level'), note=x.get('note') or '')


def primary_pattern(mapping):
    """The pattern with the largest share of an exercise mapping, or None when unmapped."""
    if not mapping:
        return None
    best = max(PATTERN_COLUMNS, key=lambda p: mapping.get(PATTERN_COLUMNS[p]) or 0)
    return best if (mapping.get(PATTERN_COLUMNS[best]) or 0) > 0 else None


def movement_evidence(checkins, training, patterns, today, days=EVIDENCE_DAYS):
    """Compare each lift's next check-in with all other check-ins, per region.

    training: {title: set(training dates)}. A training day belongs to the first check-in dated after it
    (check-ins are morning ratings, so same-day training comes after that day's check-in).
    """
    start = today - timedelta(days=days)
    result = {}
    for key, meta in REGIONS.items():
        rows = sorted((c['date'], c[meta['field']]) for c in checkins
                      if c.get(meta['field']) is not None and start <= c['date'] <= today)
        dates = [d for d, _ in rows]

        def after(days_trained):
            hit = set()
            for t in days_trained:
                nxt = next((d for d in dates if d > t), None)
                if nxt is not None:
                    hit.add(nxt)
            return hit

        def line(name, kind, pattern, days_trained):
            hit = after(days_trained)
            on = [r for d, r in rows if d in hit]
            off = [r for d, r in rows if d not in hit]
            if not on:
                return None
            enough = len(on) >= EVIDENCE_MIN and len(off) >= EVIDENCE_MIN
            return dict(name=name, kind=kind, pattern=pattern, after_count=len(on), other_count=len(off),
                        after_average=round(sum(on) / len(on), 1) if enough else None,
                        other_average=round(sum(off) / len(off), 1) if enough else None,
                        status='early' if enough and len(on) < EVIDENCE_SETTLED else 'shown' if enough else 'collecting')

        lifts = []
        for pattern in meta['patterns']:
            titles = sorted(t for t, p in patterns.items() if p == pattern and t in training)
            pattern_days = set().union(*(training[t] for t in titles)) if titles else set()
            group = [x for x in (line(t, 'lift', pattern, training[t]) for t in titles) if x]
            group.sort(key=lambda x: (-x['after_count'], x['name']))
            rollup = line(pattern.capitalize() + ' pattern overall', 'pattern', pattern, pattern_days)
            if group:
                lifts.extend(group)
                if rollup and len(group) > 1:  # with one lift the pattern line would just repeat it
                    lifts.append(rollup)
        result[key] = dict(label=meta['label'], checkins=len(rows), lines=lifts)
    return dict(window_days=days, minimum=EVIDENCE_MIN, settled=EVIDENCE_SETTLED, regions=result)


# ── Database reads (host SQLAlchemy session plus the logger's read-only file) ─────────────

def load_checkins(db, database):
    rows = db.query(database.DailyReadiness).all()
    return [dict(date=r.date, joint_upper=r.joint_upper, joint_lower=r.joint_lower) for r in rows]


def load_decisions(db, database):
    return [dict(id=r.id, region=r.region, decided_on=r.decided_on, outcome=r.outcome, until=r.until,
                 level=r.level, note=r.note, created_at=r.created_at)
            for r in db.query(database.JointCallDecision).all()]


def load_training(db, database, start, end):
    """{title: dates} from imported Hevy sets plus sets saved in the app's own logger."""
    training = {}
    for title, day in (db.query(database.WorkoutLog.exercise_title, database.WorkoutLog.date)
                       .filter(database.WorkoutLog.date >= start, database.WorkoutLog.date <= end,
                               database.WorkoutLog.is_conditioning.is_not(True)).distinct()):
        if title:
            training.setdefault(title, set()).add(day)
    try:
        with closing(sqlite3.connect(database_path().as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
            rows = conn.execute("SELECT DISTINCT exercise_title, workout_start FROM logged_sets "
                                "WHERE set_type != 'warmup'").fetchall()
    except (sqlite3.Error, OSError):
        rows = []
    for title, started in rows:
        day = local_day(started)
        if title and day and start <= day <= end:
            training.setdefault(title, set()).add(day)
    return training


def load_patterns(db, database):
    return {m.exercise_title: primary_pattern({c: getattr(m, c) for c in PATTERN_COLUMNS.values()})
            for m in db.query(database.ExerciseMapping).all() if not m.is_conditioning}


def held_exercises(db, database, held_patterns):
    """Titles whose main pattern is held; the logger shows its hold note on these."""
    if not held_patterns:
        return []
    return sorted(t for t, p in load_patterns(db, database).items() if p in held_patterns)


def current_status(db, database, today):
    result = status(load_checkins(db, database), load_decisions(db, database), today)
    result['held_exercises'] = held_exercises(db, database, result['held_patterns'])
    return result


def current_evidence(db, database, today):
    start = today - timedelta(days=EVIDENCE_DAYS + 1)
    return movement_evidence(load_checkins(db, database), load_training(db, database, start, today),
                             load_patterns(db, database), today)


def call_context(db, database, today):
    """What the coach receives for a joint coaching call (and inside a weekly call when both are due)."""
    state = current_status(db, database, today)
    if not state['call']:
        return None
    decisions = sorted(load_decisions(db, database), key=lambda x: (x['decided_on'], x['created_at']))
    return dict(kind=state['call']['kind'], regions=state['call']['regions'], call_id=state['call']['id'],
                state={k: v for k, v in state['regions'].items() if k in state['call']['regions']},
                held_patterns=state['held_patterns'], movement_evidence=current_evidence(db, database, today),
                past_decisions=[_public_decision(x) for x in decisions[-6:]],
                rules=dict(baseline_days=BASELINE_DAYS, notice=NOTICE, review=REVIEW, carry_on_default_days=CARRY_ON_DAYS))


# ── Decisions ────────────────────────────────────────────────────────────────────────────

class DecisionInput(BaseModel):
    id: UUID
    regions: list[Literal['upper', 'lower']] = Field(min_length=1, max_length=2)
    outcome: Literal['new_normal', 'carry_on', 'change', 'not_now']
    until: date | None = None
    note: str = Field(default='', max_length=1000)
    conversation_id: UUID | None = None

    @model_validator(mode='after')
    def until_only_for_carry_on(self):
        if (self.outcome == 'carry_on') != (self.until is not None):
            raise ValueError('Carry on needs an end date; other decisions must not supply one')
        if len(set(self.regions)) != len(self.regions):
            raise ValueError('Each region can appear once')
        return self


def record_decision(db, database, data, today):
    """Save the athlete's call decision, one row per region. Repeating the same request is a no-op."""
    existing = db.query(database.JointCallDecision).filter_by(request_id=str(data.id)).all()
    if existing:
        if {r.region for r in existing} != set(data.regions) or existing[0].outcome != data.outcome:
            raise ValueError('This decision ID belongs to a different decision.')
        return current_status(db, database, today)
    if data.outcome == 'carry_on' and data.until <= today:
        raise ValueError('Carry on needs an end date after today.')
    state = current_status(db, database, today)
    for region in data.regions:
        region_state = state['regions'][region]
        if region_state['level'] == 'none':
            raise ValueError(f"{REGIONS[region]['label']} joint is not above your usual, so there is nothing to decide.")
        level = accepted_level(region_state) if data.outcome == 'new_normal' else None
        if data.outcome == 'new_normal' and level is None:
            raise ValueError('No recent rating above your usual to accept as the new normal.')
        db.add(database.JointCallDecision(
            id=str(uuid5(NAMESPACE_URL, f'hevy-fatigue:joint-decision:{data.id}:{region}')), request_id=str(data.id),
            region=region, decided_on=today, outcome=data.outcome, until=data.until, level=level,
            note=data.note.strip() or None, conversation_id=str(data.conversation_id) if data.conversation_id else None,
            evidence=json.dumps(dict(state=region_state, call=state['call']), default=str),
            created_at=datetime.now(timezone.utc).isoformat()))
    db.commit()
    return current_status(db, database, today)
