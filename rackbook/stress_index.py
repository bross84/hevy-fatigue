"""Rackbook stress v1: a descriptive training-dose estimate, independent of load planning.

One reference per movement/session, from its heaviest usable set and the fixed
default rep-max curve. Blank RPEs are estimated at 5; recorded values are untouched.
The fitted coefficients and 80/120/150% bands are working conventions, not recovery limits.
Pure: no database or network access.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

MODEL_VERSION = "rackbook-stress-v1"
BASELINE_DAYS = 56
ESTIMATED_RPE = 5.0
CENTRAL_BETA = 14.72311
PERIPHERAL_SCALE = 0.5365534125622946
EFFORT_MULTIPLIER = 1.23927
REP_MAX_PERCENT = (
    100, 95.5, 92.2, 89.2, 86.3, 83.7, 81.1, 78.6, 76.2, 73.9,
    72.4, 70.7, 69.1, 67.6, 66.3, 65, 63.8, 62.7, 61.7, 60.8,
    59.9, 59.1, 58.4, 57.7, 57.1, 56.5, 55.9, 55.4, 54.9, 54.5,
    54.1, 53.7, 53.3, 53, 52.7, 52.4, 52.2, 51.9, 51.7, 51.5,
    51.3, 51.1, 50.9, 50.8, 50.6, 50.5, 50.4, 50.3, 50.2, 50.1,
)


def default_fraction(reps: int, rpe: float) -> float | None:
    k = reps + 10 - rpe
    if not math.isfinite(k) or not 1 <= k <= len(REP_MAX_PERCENT):
        return None
    low, high = math.floor(k), math.ceil(k)
    percent = REP_MAX_PERCENT[low - 1]
    if high != low:
        percent += (REP_MAX_PERCENT[high - 1] - percent) * (k - low)
    return math.floor(percent * 10 + 0.50000001) / 1000


def empty_score() -> dict:
    return {"total": 0.0, "peripheral": 0.0, "central": 0.0,
            "sets": 0, "estimated_sets": 0, "skipped_sets": 0}


def session_score(sets: list[dict]) -> dict:
    return score_session_sets(sets)[0]


def score_session_sets(sets: list[dict]) -> tuple[dict, list[dict | None]]:
    """Aligned set contributions, all using the same movement/session reference."""
    out = empty_score()
    contributions = [None] * len(sets)
    usable = []
    for index, s in enumerate(sets):
        if s.get("type", s.get("set_type")) == "warmup":
            continue
        weight, reps, rpe = s.get("weight_kg"), s.get("reps"), s.get("rpe")
        rpe = ESTIMATED_RPE if rpe is None else rpe
        if (not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0
                or not isinstance(reps, int) or isinstance(reps, bool) or reps <= 0
                or not isinstance(rpe, (int, float)) or not math.isfinite(rpe) or not 0 <= rpe <= 10
                or default_fraction(reps, rpe) is None):
            out["skipped_sets"] += 1
            continue
        usable.append((weight, reps, rpe, s.get("rpe") is None, index))
    if not usable:
        return out, contributions
    # Ties: higher RPE, then fewer reps. Deterministic under set reordering.
    anchor = max(usable, key=lambda s: (s[0], s[2], -s[1]))
    e1rm = anchor[0] / default_fraction(anchor[1], anchor[2])
    for weight, reps, rpe, estimated, index in usable:
        intensity = weight / e1rm
        central = reps * 1e-6 * math.exp(CENTRAL_BETA * intensity)
        peripheral = PERIPHERAL_SCALE * intensity * sum(
            EFFORT_MULTIPLIER ** (rpe - 10 - j) for j in range(reps))
        contributions[index] = dict(total=(central + peripheral) / 2, central=central,
                                   peripheral=peripheral, sets=1, estimated_sets=int(estimated), skipped_sets=0)
        out["central"] += central
        out["peripheral"] += peripheral
        out["sets"] += 1
        out["estimated_sets"] += int(estimated)
    out["total"] = (out["central"] + out["peripheral"]) / 2
    return out, contributions


def parse_time(value) -> datetime | None:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def merge_history(entries: list[dict], local_rows: list[dict]) -> list[dict]:
    """Local workouts are complete snapshots: replace their Hevy sets, never add twice.

    This also preserves low RPEs, exact weights, and local-only saves whose Hevy
    history hasn't propagated yet. This overlay is only used for stress.
    """
    local = [dict(s, workout_id=s.get("hevy_workout_id"),
                  workout_start_time=s.get("workout_start")) for s in local_rows]
    ids = {s["workout_id"] for s in local if s.get("workout_id")}
    times = {parse_time(s.get("workout_start_time")) for s in local if not s.get("workout_id")}
    times.discard(None)
    return [dict(s) for s in entries if s.get("workout_id") not in ids
            and parse_time(s.get("workout_start_time")) not in times] + local


def add_scores(scores) -> dict:
    out = empty_score()
    for score in scores:
        for key in out:
            out[key] += score[key]
    return out


def build_summary(entries: list[dict], current_sets: list[dict], *, now: datetime,
                  session_start: datetime | None = None, preview_sets: list[dict] | None = None) -> dict:
    """Rolling trailing durations include completed draft sets once, at their session start.

    Baseline = median session in the preceding 56 days, excluding this draft.
    Empty calendar weeks affect rolling totals, never become zero-dose sessions.
    """
    now = parse_time(now)
    if now is None:
        raise ValueError("now must include a timezone")
    current_at = parse_time(session_start) if session_start is not None else now
    groups = defaultdict(list)
    for entry in entries:
        timestamp = parse_time(entry.get("workout_start_time"))
        if timestamp is None or timestamp > now:
            continue
        groups[(entry.get("workout_id") or "", timestamp)].append(entry)
    sessions = [(key[1], session_score(sets)) for key, sets in groups.items()]
    current, set_scores = score_session_sets(current_sets)
    result = _summary_from_sessions(sessions, current, now, current_at)
    result["set_scores"] = set_scores
    preview, preview_scores = score_session_sets(preview_sets if preview_sets is not None else current_sets)
    result.update(preview=preview, preview_set_scores=preview_scores,
                  preview_status=stress_status(preview, result["window"]["median"]))
    return result


def stress_status(score: dict, typical: float | None) -> str:
    if not score["sets"]:
        return "no_sets"
    if typical is None:
        return "no_baseline"
    ratio = score["total"] / typical
    return "below_usual" if ratio < .8 else "usual" if ratio <= 1.2 else "elevated" if ratio <= 1.5 else "much_higher"


def _summary_from_sessions(sessions, current, now, current_at):
    baseline = [s for t, s in sessions if now - timedelta(days=BASELINE_DAYS) < t <= now and s["sets"]]
    values = [s["total"] for s in baseline]
    typical = median(values) if values else None
    window = {"median": typical, "lower": typical * .8 if typical is not None else None,
              "upper": typical * 1.2 if typical is not None else None,
              "elevated_upper": typical * 1.5 if typical is not None else None,
              "sessions": len(values), "estimated_sessions": sum(s["estimated_sets"] > 0 for s in baseline),
              "provisional": len(values) < 6, "days": BASELINE_DAYS}
    status = stress_status(current, typical)
    rolling = {}
    for days in (7, 28):
        scores = [s for t, s in sessions if now - timedelta(days=days) < t <= now]
        if current_at is not None and now - timedelta(days=days) < current_at <= now:
            scores.append(current)
        rolling[str(days)] = add_scores(scores)
    last = max((t for t, s in sessions if s["sets"]), default=None)
    return {"model_version": MODEL_VERSION, "session": current, "window": window,
            "set_scores": [], "preview": current, "preview_set_scores": [], "preview_status": status,
            "status": status, "rolling_7": rolling["7"], "rolling_28": rolling["28"],
            "days_since_last": (now - last).days if last else None,
            "as_of": now.isoformat()}


def build_dashboard(entries: list[dict], *, now: datetime, days: int = 56) -> dict:
    """Recalculate saved history without writes; historical windows have no look-ahead.

    The display range never truncates the history used for rolling totals or a
    session's preceding baseline. days=0 includes all available saved history.
    Scores are computed once, shared by current totals and retrospective windows.
    """
    now = parse_time(now)
    if now is None:
        raise ValueError("now must include a timezone")
    groups = defaultdict(list)
    for entry in entries:
        start = parse_time(entry.get("workout_start_time"))
        if start is not None and start <= now:
            groups[(entry.get("workout_id") or "", start)].append(entry)
    ordered = sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))
    scored = [(key, sets, session_score(sets)) for key, sets in ordered]
    # Warm-up-only workouts are not movement exposures; invalid working sets remain visible.
    scored = [(key, sets, score) for key, sets, score in scored if score["sets"] or score["skipped_sets"]]
    current = _summary_from_sessions([(key[1], score) for key, _, score in scored], empty_score(), now, now)
    cutoff = now - timedelta(days=days) if days else None
    rows = []
    prior = []
    for key, sets, score in scored:
        start = key[1]
        if cutoff is None or start > cutoff:
            # Workouts with an identical timestamp do not establish precedence.
            earlier = [(t, s) for t, s in prior if t < start]
            summary = _summary_from_sessions(earlier, score, start, start)
            rows.append({"workout_id": key[0] or None, "title": sets[0].get("workout_title") or "Workout",
                         "start_time": start.isoformat(), "score": score,
                         "window": summary["window"], "status": summary["status"],
                         "rolling_7": summary["rolling_7"], "rolling_28": summary["rolling_28"]})
        prior.append((start, score))
    return {"model_version": MODEL_VERSION, "as_of": now.isoformat(), "days": days,
            "current": current, "sessions": rows, "available_sessions": len(scored),
            "first_recorded_at": scored[0][0][1].isoformat() if scored else None}
