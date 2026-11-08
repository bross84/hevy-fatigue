"""Read-only Rackbook stress-index evidence for AI coaching reports.

Pure: no database, Hevy or provider access. It scores the sessions coaching.build_report
has already merged (local exact sets preferred over imports) with rackbook.stress_index,
so the coach and the logger/dashboard use one calculation. Descriptive context only.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median

from rackbook import stress_index

RECENT_SESSIONS = 6
PATTERNS = ('knee', 'hip', 'push', 'pull')
PATTERN_COLUMNS = dict(knee='pct_quad_dom', hip='pct_posterior', push='pct_upper_push', pull='pct_upper_pull')
WINDOW_DAYS = 7          # rolling windows end on the report date; never a calendar week
WINDOWS_SHOWN = 9        # the latest window (the last 7 days) and the eight before it
MIN_TYPICAL_WINDOWS = 4
WEIGHT_TOLERANCE = .01   # mapping percentages must sum to 1.0 within this
DESCRIPTION = (
    'Rackbook stress index: a descriptive per-movement training-dose estimate relative to an '
    'estimated max, split into central (mechanical) and peripheral (metabolic) parts. Totals are '
    'comparable only within one movement. They are not recovery limits, fatigue measurements or '
    'optimal zones, and are not additive across different movements.')
LIMITATIONS = (
    'Stress index is descriptive context. Compare a session only with the same movement’s own typical '
    'range; values are not additive across movements and are not recovery or fatigue measurements.',
    'Stress index: imported Hevy sets carry no set type, so warm-ups cannot be separated and may be '
    'counted; blank RPEs are estimated at 5 (counted in estimated_sets). Sessions without a start '
    'time are not scored (unscored_sessions). History before the six-month window is not used.',
    'Pattern stress index: each movement session’s stress is split across knee/hip/push/pull by the '
    'current exercise_mappings percentages (accessories are not discounted; editing a mapping re-attributes '
    'history). Auto-classified mappings may be wrong (see reviewed_share). Mappings that are missing or do '
    'not sum to 1 are kept in unmapped, and conditioning exercises are excluded. Windows are rolling 7 local '
    'days ending on the report date, not calendar weeks; the latest window is the last 7 days. Attributed '
    'totals are not recovery limits.')
PATTERN_DESCRIPTION = (
    'Rackbook stress index attributed to knee, hip, push and pull from the exercise mapping percentages, '
    'summed over rolling 7-day windows. This is a different quantity from the host Pattern Stress card '
    '(ATL/CTL, soreness).')


def window_end(day, today):
    """Last day of the rolling WINDOW_DAYS window that holds `day`, counting back from `today`."""
    return today - timedelta(days=((today - day).days // WINDOW_DAYS) * WINDOW_DAYS)


def utc_start(value):
    """Imported host times are naive UTC (the importer strips the offset); logger times carry one."""
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _score(score):
    return dict(total=round(score['total'], 2), central=round(score['central'], 2),
                peripheral=round(score['peripheral'], 2), sets=score['sets'],
                estimated_sets=score['estimated_sets'], skipped_sets=score['skipped_sets'])


def _summary(entries, now, unscored, dates):
    """(compact summary, [(local date, unrounded score)] for every scored session)."""
    board = stress_index.build_dashboard(entries, now=now, days=0)
    rows = board['sessions']
    if not rows:
        return dict(status='no_scorable_sessions', unscored_sessions=unscored), []
    current, window, latest = board['current'], board['current']['window'], rows[-1]
    return dict(
        model_version=board['model_version'], as_of=board['as_of'], status='available',
        scored_sessions=board['available_sessions'], unscored_sessions=unscored,
        days_since_last=current['days_since_last'],
        typical_session=dict(
            median=None if window['median'] is None else round(window['median'], 2),
            usual_low=None if window['lower'] is None else round(window['lower'], 2),
            usual_high=None if window['upper'] is None else round(window['upper'], 2),
            baseline_days=window['days'], baseline_sessions=window['sessions'],
            estimated_baseline_sessions=window['estimated_sessions'], provisional=window['provisional']),
        rolling_7_day=_score(current['rolling_7']), rolling_28_day=_score(current['rolling_28']),
        latest_session=dict(date=dates.get(latest['workout_id']), status=latest['status'], **_score(latest['score'])),
        recent_sessions=[dict(date=dates.get(r['workout_id']), session_id=r['workout_id'], status=r['status'],
                              baseline_median=None if r['window']['median'] is None else round(r['window']['median'], 2),
                              baseline_sessions=r['window']['sessions'], **_score(r['score']))
                         for r in rows[-RECENT_SESSIONS:]]), [(dates.get(r['workout_id']), r['score']) for r in rows]


def attach(exercises, ordered, today):
    """Add exercise['stress'] to each report exercise; returns {exercise_id: [(local date, score)]}.

    Never writes or contacts Hevy."""
    entries, unscored, dates, latest = defaultdict(list), defaultdict(set), {}, None
    for session in ordered:
        start = utc_start(session.get('start_time'))
        dates[session['id']] = session['date']
        for s in session['sets']:
            if s.get('conditioning'):
                continue
            key = s['exercise_id']
            if start is None:
                unscored[key].add(session['id'])
                continue
            latest = start if latest is None or start > latest else latest
            entries[key].append(dict(
                weight_kg=s['weight_kg'], reps=s['reps'], rpe=s['actual_rpe'],
                type='warmup' if s['role'] == 'warmup' else 'normal', workout_id=session['id'],
                workout_start_time=start.isoformat(), workout_title=session.get('title')))
    # Sessions are dated by local calendar day; include every session on `today`, even a late
    # evening one whose UTC start falls on the next day.
    end = datetime.combine(today, time(23, 59, 59), timezone.utc)
    now = max(end, latest) if latest else end
    scored = {}
    for exercise in exercises.values():
        key = exercise['exercise_id']
        exercise['stress'], rows = _summary(entries.get(key, []), now, len(unscored.get(key, ())), dates)
        if rows:
            scored[key] = rows
    return scored


def mapping_table(rows):
    """{exercise_title: weights/reviewed/conditioning} from ExerciseMapping rows or equivalent objects."""
    return {row.exercise_title: dict(
        weights={p: float(getattr(row, column) or 0) for p, column in PATTERN_COLUMNS.items()},
        reviewed=bool(row.is_reviewed), conditioning=bool(row.is_conditioning)) for row in rows}


def _local_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bucket():
    return dict(patterns={p: dict(total=0., central=0., peripheral=0.) for p in PATTERNS},
                unmapped=dict(total=0., central=0., peripheral=0.))


def _add(bucket, score, weights):
    """Add a session score by pattern weight, or to unmapped when there are no valid weights."""
    parts = [('unmapped', 1., bucket['unmapped'])] if weights is None else [
        (p, weights[p], bucket['patterns'][p]) for p in PATTERNS if weights[p] > 0]
    for _, share, target in parts:
        for field in ('total', 'central', 'peripheral'):
            target[field] += score[field] * share


def _rounded(value):
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    return round(value, 2) if isinstance(value, float) else value


def pattern_rollup(scored, exercises, mappings, today):
    """Stress attributed to patterns over rolling 7-day windows ending `today`. Pure, read-only, nothing stored."""
    ends = [today - timedelta(days=WINDOW_DAYS * (WINDOWS_SHOWN - 1 - i)) for i in range(WINDOWS_SHOWN)]
    windows = {end: dict(bucket=_bucket(), sessions=0) for end in ends}
    rolling_28 = _bucket()
    unmapped_titles, mapped_total, reviewed_total = set(), 0., 0.
    for key, rows in scored.items():
        title = exercises[key]['title']
        mapping = mappings.get(title)
        if mapping and mapping['conditioning']:
            continue
        weights = mapping['weights'] if mapping and abs(sum(mapping['weights'].values()) - 1) <= WEIGHT_TOLERANCE else None
        for day_text, score in rows:
            day = _local_day(day_text)
            if day is None or day > today or not score['sets']:
                continue
            window = windows.get(window_end(day, today))
            if window is not None:
                _add(window['bucket'], score, weights)
                window['sessions'] += 1
                if weights is None:
                    unmapped_titles.add(title)
                else:
                    mapped_total += score['total']
                    reviewed_total += score['total'] if mapping['reviewed'] else 0.
            if (today - day).days < 28:
                _add(rolling_28, score, weights)
    if not any(window['sessions'] for window in windows.values()):
        return dict(status='no_scorable_sessions', windows_shown=WINDOWS_SHOWN, window_days=WINDOW_DAYS)
    # The latest window is the one being judged, so it never enters the typical range.
    earlier = [w for end, w in windows.items() if end != today and w['sessions']]
    typical = {p: dict(median=round(median(w['bucket']['patterns'][p]['total'] for w in earlier), 2) if earlier else None,
                       trained_windows=len(earlier), provisional=len(earlier) < MIN_TYPICAL_WINDOWS) for p in PATTERNS}
    return _rounded(dict(
        status='available', model_version=stress_index.MODEL_VERSION, as_of=str(today),
        description=PATTERN_DESCRIPTION, window_days=WINDOW_DAYS,
        window_basis='Rolling 7 local days ending on as_of (local workout dates); the last entry is the last 7 days.',
        patterns=list(PATTERNS),
        windows=[dict(window_start=str(end - timedelta(days=WINDOW_DAYS - 1)), window_end=str(end),
                      trained=bool(windows[end]['sessions']), scored_movement_sessions=windows[end]['sessions'],
                      **windows[end]['bucket']) for end in ends],
        rolling_28_day=rolling_28, typical_window=typical,
        unmapped_exercises=sorted(unmapped_titles)[:10],
        reviewed_share=round(reviewed_total / mapped_total, 2) if mapped_total else None))
