"""Session RPE feel check (#199): a small modifier on a session's whole-body (central) stress.

Each rated session has a gap: its session RPE minus the average RPE of its rated sets. Most people
rate a whole session a little above (or below) their sets every time, so a session is only nudged
when its gap differs from the athlete's usual gap (the mean of their last 10 rated sessions within
8 weeks, needing at least 5). Each point of difference moves central stress by 5%, capped at ±15%.
Pattern (Knee/Hip/Push/Pull) and peripheral stress are never touched, sRPE × minutes is not used,
and nothing applies to sessions dated before the feature started (app setting `srpe_modifier_start`)
or to sessions scored by sRPE × minutes (conditioning/cardio).
"""
from datetime import date, timedelta
from statistics import mean

START_SETTING = 'srpe_modifier_start'
PER_POINT = 0.05
CAP = 0.15
MIN_HISTORY = 5
HISTORY_SESSIONS = 10
HISTORY_DAYS = 56
NOTE_THRESHOLD = 0.5      # points of difference before the session shows a note
SRPE_LOAD_MODALITIES = {'conditioning', 'cardio'}


def set_rpe(row):
    """A set's RPE, from RIR when only that was logged; None when unrated."""
    if row.rpe is not None and row.rpe > 0:
        return float(row.rpe)
    if row.rir is not None:
        return 10.0 - float(row.rir)
    return None


def gap(srpe, rpes):
    """Session RPE minus the mean rated-set RPE, or None without a rating or rated sets."""
    rated = [r for r in rpes if r is not None]
    if srpe is None or not rated:
        return None
    return float(srpe) - mean(rated)


def adjustment(today_gap, history_gaps):
    """{'pct', 'difference', 'usual_gap'} or None while fewer than MIN_HISTORY rated sessions exist."""
    if today_gap is None:
        return None
    recent = [g for g in history_gaps if g is not None][-HISTORY_SESSIONS:]
    if len(recent) < MIN_HISTORY:
        return None
    usual = mean(recent)
    difference = today_gap - usual
    pct = max(-CAP, min(CAP, PER_POINT * difference))
    return {'pct': pct, 'difference': difference, 'usual_gap': usual}


def start_date(db, models):
    row = db.query(models.AppSetting).filter(models.AppSetting.key == START_SETTING).first()
    if row is None or not row.value:
        return None
    try:
        return date.fromisoformat(row.value)
    except ValueError:
        return None


def _eligible(session, start):
    return (start is not None and session.srpe is not None and session.workout_date is not None
            and session.workout_date >= start
            and (session.modality or '') not in SRPE_LOAD_MODALITIES)


def _rpes(db, models, workout_id):
    return [set_rpe(row) for row in db.query(models.WorkoutLog).filter(models.WorkoutLog.workout_id == workout_id).all()]


def session_adjustment(db, models, session):
    """The feel-check result for one monitoring session, with what the note needs, or None."""
    start = start_date(db, models)
    if not _eligible(session, start):
        return None
    rpes = _rpes(db, models, session.hevy_workout_id)
    today_gap = gap(session.srpe, rpes)
    if today_gap is None:
        return None
    since = max(start, session.workout_date - timedelta(days=HISTORY_DAYS))
    earlier = (db.query(models.WorkoutSession)
               .filter(models.WorkoutSession.srpe.isnot(None),
                       models.WorkoutSession.workout_date >= since,
                       models.WorkoutSession.workout_date <= session.workout_date,
                       models.WorkoutSession.hevy_workout_id != session.hevy_workout_id)
               .order_by(models.WorkoutSession.workout_date, models.WorkoutSession.start_time)
               .all())
    history = []
    for other in earlier:
        if not _eligible(other, start):
            continue
        if other.workout_date == session.workout_date and (
                other.start_time is None or session.start_time is None or other.start_time >= session.start_time):
            continue          # only sessions before this one count toward "usual"
        history.append(gap(other.srpe, _rpes(db, models, other.hevy_workout_id)))
    result = adjustment(today_gap, history)
    if result is None:
        return None
    rated = [r for r in rpes if r is not None]
    expected = mean(rated) + result['usual_gap']
    return {**result, 'srpe': float(session.srpe), 'expected_srpe': round(expected * 2) / 2,
            'note': note(result['pct'], float(session.srpe), expected, result['difference'])}


def note(pct, srpe, expected, difference):
    if abs(difference) < NOTE_THRESHOLD:
        return None
    direction = 'harder' if difference > 0 else 'easier'
    expected_text = f'{round(expected * 2) / 2:g}'
    return (f'Felt {direction} than usual: whole-body stress {pct * 100:+.0f}% '
            f'(session RPE {srpe:g}; your sets suggested about {expected_text})')


def recent_summary(db, models, today, days=28):
    """What the weekly coaching call is told: how recent rated sessions felt against usual.

    consistently_easier marks at least 3 recent rated sessions, three quarters of them easier than
    usual; combined with low fatigue in the rest of the monitoring context, the coach may treat it as
    room to push (a suggestion only; joint holds still apply).
    """
    since = today - timedelta(days=days)
    sessions = (db.query(models.WorkoutSession)
                .filter(models.WorkoutSession.srpe.isnot(None),
                        models.WorkoutSession.workout_date >= since,
                        models.WorkoutSession.workout_date <= today)
                .order_by(models.WorkoutSession.workout_date, models.WorkoutSession.start_time)
                .all())
    rows = []
    for session in sessions:
        result = session_adjustment(db, models, session)
        if result is None:
            continue
        rows.append({'date': str(session.workout_date), 'title': session.workout_title,
                     'session_rpe': result['srpe'], 'sets_suggested': result['expected_srpe'],
                     'difference': round(result['difference'], 1),
                     'whole_body_change_pct': round(result['pct'] * 100)})
    easier = sum(1 for r in rows if r['difference'] <= -NOTE_THRESHOLD)
    harder = sum(1 for r in rows if r['difference'] >= NOTE_THRESHOLD)
    return {'days': days, 'rated_sessions': len(rows), 'easier_than_usual': easier,
            'harder_than_usual': harder, 'sessions': rows[-10:],
            'consistently_easier': len(rows) >= 3 and easier >= 3 and easier >= 0.75 * len(rows)}
