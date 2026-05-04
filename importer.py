from collections import defaultdict
import re

from database import SessionLocal, WorkoutLog, WorkoutSession, ExerciseMapping, ExerciseCanonical, ExerciseConflict, AppSetting, init_db
from hevy_client import HevyClient
from rpe_table import calculate_e1rm, seed_rpe_table
from exercise_classifier import classify_exercise, ensure_exercise_mapped
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


CONDITIONING_TITLE_KEYWORDS = [
    "metcon", "wod", "amrap", "emom", "hiit",
    "conditioning", "cardio", "crossfit", "circuit",
    " con", "strongman",
]

STRENGTH_TITLE_KEYWORDS = [
    "me upper", "me lower", "max effort",
    " st",
]

HYPERTROPHY_TITLE_KEYWORDS = [
    "hypertrophy", "hyp", "bodybuilding",
    " hyp",
]

CARDIO_TITLE_KEYWORDS = [
    " car",
]

_MIXED_SESSION_NOTE = "Mixed session detected - consider splitting by modality"

_SRPE_TITLE_TAG_PATTERN = re.compile(r"@(?P<value>\d+(?:\.\d+)?)")
_IMPORT_CONTEXT_KEY = "importer_sync_context"
_LAST_SYNC_SETTING_KEY = "last_sync"
_AUTO_VERIFY_CONFIDENCE_THRESHOLD_DEFAULT = 0.87


def _extract_srpe_from_title(workout_title):
    """Extract first valid sRPE tag (@N or @N.N, 0..10) from title."""
    if not workout_title:
        return None
    match = _SRPE_TITLE_TAG_PATTERN.search(workout_title)
    if not match:
        return None
    try:
        srpe = float(match.group("value"))
    except (TypeError, ValueError):
        return None
    if 0.0 <= srpe <= 10.0:
        return srpe
    return None


def _parse_hevy_datetime(raw_value):
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _compute_duration_minutes(start_dt, end_dt):
    if not start_dt or not end_dt:
        return None
    duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
    if duration_minutes <= 0 or duration_minutes > 480:
        return None
    return duration_minutes


def _infer_modality_from_exercises(workout_title, exercises, conditioning_cache):
    title = (workout_title or "").lower()
    cardio_title_keywords = ["run", "running", "jog", "cardio", "ride", "cycling", "bike", "row", "rowing"]
    has_cardio_title_hint = any(keyword in title for keyword in cardio_title_keywords)

    conditioning_sets = 0
    strength_sets = 0
    reps_values = []

    for exercise in exercises:
        ex_title = exercise.get('title')
        is_conditioning = conditioning_cache.get(ex_title, False)

        for set_data in exercise.get('sets', []):
            if set_data.get('type') == 'warmup':
                continue
            if is_conditioning:
                conditioning_sets += 1
            else:
                strength_sets += 1
                reps = set_data.get('reps')
                if reps is not None:
                    try:
                        reps_values.append(int(reps))
                    except (TypeError, ValueError):
                        pass

    total_sets = conditioning_sets + strength_sets
    if total_sets == 0:
        if has_cardio_title_hint:
            return "cardio", 0.60
        return "strength", 0.50

    conditioning_ratio = conditioning_sets / total_sets
    if conditioning_ratio >= 0.70:
        modality = "cardio" if has_cardio_title_hint else "conditioning"
        confidence = round(min(0.99, 0.70 + conditioning_ratio * 0.25), 2)
        return modality, confidence

    if reps_values:
        avg_reps = sum(reps_values) / len(reps_values)
    else:
        avg_reps = 8.0

    if avg_reps <= 6.5:
        return "strength", 0.85
    if avg_reps >= 10.0:
        return "hypertrophy", 0.82
    return "hypertrophy", 0.70


def _infer_modality_from_title(workout_title):
    title = (workout_title or "").lower()
    modality_order = [
        ("conditioning", CONDITIONING_TITLE_KEYWORDS),
        ("strength", STRENGTH_TITLE_KEYWORDS),
        ("hypertrophy", HYPERTROPHY_TITLE_KEYWORDS),
        ("cardio", CARDIO_TITLE_KEYWORDS),
    ]
    first_match_order = []
    modality_matches = {}
    for modality, keywords in modality_order:
        indices = []
        for kw in keywords:
            idx = title.find(kw)
            if idx != -1:
                indices.append(idx)
        if indices:
            first_match_order.append((min(indices), modality))
            modality_matches[modality] = len(indices)
        else:
            modality_matches[modality] = 0

    active = [modality for modality, count in modality_matches.items() if count > 0]

    # A valid @sRPE title tag is treated as a conditioning signal when no
    # explicit modality keywords/codes are present.
    if _extract_srpe_from_title(workout_title) is not None and not active:
        return "conditioning", 0.95, None

    if not active:
        return None, None, None

    if "+" in title:
        dominant = min(first_match_order, key=lambda m: m[0])[1]
        return dominant, 0.70, _MIXED_SESSION_NOTE

    if len(active) == 1:
        return active[0], 0.95, None

    # Mixed titles are forced to pending confidence by design.
    priority = {"conditioning": 3, "strength": 2, "hypertrophy": 1}
    dominant = max(
        active,
        key=lambda modality: (modality_matches[modality], priority[modality]),
    )
    return dominant, 0.70, _MIXED_SESSION_NOTE


def _infer_modality(workout_title, exercises, conditioning_cache):
    title_modality, title_confidence, title_note = _infer_modality_from_title(workout_title)
    if title_modality is not None:
        return title_modality, title_confidence, title_note

    modality, confidence = _infer_modality_from_exercises(
        workout_title=workout_title,
        exercises=exercises,
        conditioning_cache=conditioning_cache,
    )
    return modality, confidence, None


def _build_exercises_from_logs(workout_logs):
    exercises_by_title = defaultdict(list)
    for log_row in workout_logs:
        title = log_row.exercise_title
        if not title:
            continue
        exercises_by_title[title].append({
            "type": "normal",
            "reps": log_row.reps,
        })

    return [
        {"title": title, "sets": sets}
        for title, sets in exercises_by_title.items()
    ]


def _resolve_conditioning_from_current_classifier(exercise_title, db, mapping_cache):
    if exercise_title in mapping_cache:
        return mapping_cache[exercise_title]

    mapping = db.query(ExerciseMapping).filter(
        ExerciseMapping.exercise_title == exercise_title
    ).first()

    if mapping and mapping.source == "user":
        is_conditioning = bool(mapping.is_conditioning)
    else:
        is_conditioning = bool(classify_exercise(exercise_title)["is_conditioning"])

    mapping_cache[exercise_title] = is_conditioning
    return is_conditioning


def _get_setting_value(db, key: str) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set_setting_value(db, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _get_auto_verify_confidence_threshold(db) -> float:
    raw = _get_setting_value(db, "auto_verify_confidence_threshold")
    if raw is None:
        return _AUTO_VERIFY_CONFIDENCE_THRESHOLD_DEFAULT
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _AUTO_VERIFY_CONFIDENCE_THRESHOLD_DEFAULT
    if 0.50 <= value <= 1.00:
        return value
    return _AUTO_VERIFY_CONFIDENCE_THRESHOLD_DEFAULT


def _get_client_api_key(db) -> str | None:
    api_key = db.info.get("hevy_api_key")
    if api_key:
        return api_key

    raw = _get_setting_value(db, "hevy_api_key")
    if not raw:
        return None

    raw = raw.strip()
    if not raw:
        return None

    # API-layer sync calls inject the decrypted key through db.info.
    # When the DB still contains legacy plaintext, preserve that fallback.
    if raw.startswith("gAAAA"):
        return None
    return raw


def load_canonical_map(db) -> dict[str, str]:
    return {
        row.exercise_id: row.canonical_title
        for row in db.query(ExerciseCanonical).all()
        if row.exercise_id
    }


def _get_import_context(db) -> dict:
    context = db.info.get(_IMPORT_CONTEXT_KEY)
    if context is None:
        raise RuntimeError("Importer context has not been initialized.")
    return context


def _process_workout(db, workout, canonical_map):
    context = _get_import_context(db)
    auto_verify_confidence_threshold = context["auto_verify_confidence_threshold"]
    exercise_conditioning_cache = context["exercise_conditioning_cache"]
    stats = context["stats"]

    workout_id = workout.get('id')
    workout_title = workout.get('title')
    raw_start = workout.get('start_time')
    raw_end = workout.get('end_time')
    start_dt = _parse_hevy_datetime(raw_start)
    end_dt = _parse_hevy_datetime(raw_end)
    raw_date = raw_start

    # start_time is required for WorkoutLog.date (NOT NULL); skip invalid payloads.
    if not raw_date:
        stats["skipped_workouts_missing_date"] += 1
        return
    try:
        workout_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).date()
    except ValueError:
        stats["skipped_workouts_missing_date"] += 1
        return

    exercises = workout.get('exercises', [])

    for exercise in exercises:
        title = exercise.get('title')

        # Auto-classify exercise if not already in the mapping table
        ensure_exercise_mapped(title, db)

        if title in exercise_conditioning_cache:
            continue

        mapping = db.query(ExerciseMapping).filter(
            ExerciseMapping.exercise_title == title
        ).first()
        is_conditioning = bool(mapping.is_conditioning) if mapping else False
        exercise_conditioning_cache[title] = is_conditioning

    modality, modality_confidence, modality_note = _infer_modality(
        workout_title=workout_title,
        exercises=exercises,
        conditioning_cache=exercise_conditioning_cache,
    )
    srpe_from_title = _extract_srpe_from_title(workout_title)
    duration_minutes = _compute_duration_minutes(start_dt, end_dt)
    verification_status, verified_at = _resolve_verification(
        modality=modality,
        confidence=modality_confidence,
        duration_minutes=duration_minutes,
        auto_verify_confidence_threshold=auto_verify_confidence_threshold,
        srpe=srpe_from_title,
        srpe_from_title=srpe_from_title is not None,
    )

    existing_session = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.hevy_workout_id == workout_id)
        .first()
    )

    if existing_session and existing_session.verification_status == "verified":
        session_stmt = sqlite_insert(WorkoutSession).values(
            hevy_workout_id=workout_id,
            workout_date=workout_date,
            workout_title=workout_title,
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=duration_minutes,
            modality=existing_session.modality,
            modality_confidence=existing_session.modality_confidence,
            modality_note=existing_session.modality_note,
            verification_status=existing_session.verification_status,
            verified_at=existing_session.verified_at,
            srpe=existing_session.srpe,
            updated_at=datetime.utcnow(),
        ).on_conflict_do_update(
            index_elements=[WorkoutSession.hevy_workout_id],
            set_={
                "workout_date": workout_date,
                "workout_title": workout_title,
                "start_time": start_dt,
                "end_time": end_dt,
                "duration_minutes": duration_minutes,
                "updated_at": datetime.utcnow(),
            },
        )
    else:
        session_stmt = sqlite_insert(WorkoutSession).values(
            hevy_workout_id=workout_id,
            workout_date=workout_date,
            workout_title=workout_title,
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=duration_minutes,
            modality=modality,
            modality_confidence=modality_confidence,
            modality_note=modality_note,
            verification_status=verification_status,
            verified_at=verified_at,
            srpe=srpe_from_title,
            updated_at=datetime.utcnow(),
        ).on_conflict_do_update(
            index_elements=[WorkoutSession.hevy_workout_id],
            set_={
                "workout_date": workout_date,
                "workout_title": workout_title,
                "start_time": start_dt,
                "end_time": end_dt,
                "duration_minutes": duration_minutes,
                "modality": modality,
                "modality_confidence": modality_confidence,
                "modality_note": modality_note,
                "verification_status": verification_status,
                "verified_at": verified_at,
                "srpe": srpe_from_title,
                "updated_at": datetime.utcnow(),
            },
        )
    db.execute(session_stmt)

    for exercise in exercises:
        exercise_id = exercise.get('exercise_template_id')
        title = canonical_map.get(exercise_id, exercise.get('title'))

        is_conditioning = exercise_conditioning_cache.get(exercise.get('title'), False)

        for set_data in exercise.get('sets', []):
            if set_data.get('type') == 'warmup':
                continue  # Skip warmup sets — working sets only

            set_number = set_data.get('index')
            weight_kg = set_data.get('weight_kg') or 0.0
            reps = set_data.get('reps') or 0
            rpe = set_data.get('rpe')
            rir = set_data.get('rir')  # Reps in Reserve — Hevy may expose this field

            weight_lbs = round(weight_kg * 2.20462, 2) if weight_kg else None

            # Calculate e1RM using full fallback hierarchy:
            # RPE/RIR table → history inference → Wendler
            e1rm = calculate_e1rm(
                weight=weight_lbs,
                reps=reps,
                rpe=rpe,
                rir=rir,
                exercise_title=title,
                db=db
            )

            # Upsert set rows: preserve training data fields but allow title renames
            # from Hevy to propagate to existing stored sets.
            stmt = sqlite_insert(WorkoutLog).values(
                date=workout_date,
                workout_id=workout_id,
                workout_title=workout_title,
                exercise_id=exercise_id,
                exercise_title=title,
                set_number=set_number,
                weight_lbs=weight_lbs,
                reps=reps,
                rpe=rpe,
                rir=rir,
                estimated_1rm=e1rm,
                is_conditioning=is_conditioning,
            ).on_conflict_do_update(
                index_elements=[
                    WorkoutLog.workout_id,
                    WorkoutLog.exercise_id,
                    WorkoutLog.set_number,
                ],
                set_={
                    "exercise_title": title,
                    "workout_title": workout_title,
                },
            )
            result = db.execute(stmt)
            if result.rowcount:
                stats["new_sets"] += 1


def reclassify_existing_sessions(db, force_all=False):
    init_db()
    session_query = db.query(WorkoutSession).order_by(WorkoutSession.workout_date.desc(), WorkoutSession.start_time.desc())
    session_rows = session_query.all()

    workout_ids = [row.hevy_workout_id for row in session_rows]
    workout_logs = []
    if workout_ids:
        workout_logs = (
            db.query(WorkoutLog)
            .filter(WorkoutLog.workout_id.in_(workout_ids))
            .order_by(WorkoutLog.workout_id.asc(), WorkoutLog.exercise_title.asc(), WorkoutLog.set_number.asc())
            .all()
        )

    logs_by_workout_id = defaultdict(list)
    for log_row in workout_logs:
        logs_by_workout_id[log_row.workout_id].append(log_row)

    conditioning_cache = {}
    reclassified_count = 0
    skipped_verified_count = 0

    for session_row in session_rows:
        if session_row.verification_status == "verified" and not force_all:
            skipped_verified_count += 1
            continue

        session_logs = logs_by_workout_id.get(session_row.hevy_workout_id, [])
        exercises = _build_exercises_from_logs(session_logs)
        for exercise in exercises:
            title = exercise.get("title")
            if not title:
                continue
            conditioning_cache[title] = _resolve_conditioning_from_current_classifier(
                title,
                db,
                conditioning_cache,
            )

        modality, confidence, note = _infer_modality(
            workout_title=session_row.workout_title,
            exercises=exercises,
            conditioning_cache=conditioning_cache,
        )
        session_row.modality = modality
        session_row.modality_confidence = confidence
        session_row.modality_note = note
        session_row.updated_at = datetime.utcnow()
        reclassified_count += 1

    db.commit()
    return {
        "reclassified_sessions": reclassified_count,
        "skipped_verified_sessions": skipped_verified_count,
    }


def _resolve_verification(
    modality,
    confidence,
    duration_minutes,
    auto_verify_confidence_threshold=0.87,
    srpe=None,
    srpe_from_title=False,
):
    if duration_minutes is None:
        return "pending", None

    if (
        modality in {"conditioning", "cardio"}
        and srpe is not None
        and srpe_from_title
        and confidence >= auto_verify_confidence_threshold
    ):
        return "verified", datetime.utcnow()

    if modality in {"strength", "hypertrophy"} and confidence >= auto_verify_confidence_threshold:
        return "verified", datetime.utcnow()

    return "pending", None


def detect_exercise_conflicts(db):
    candidate_rows = (
        db.query(WorkoutLog.exercise_id)
        .filter(WorkoutLog.exercise_id.isnot(None))
        .group_by(WorkoutLog.exercise_id)
        .having(func.count(func.distinct(WorkoutLog.exercise_title)) > 1)
        .all()
    )
    candidate_ids = [row.exercise_id for row in candidate_rows if row.exercise_id]
    if not candidate_ids:
        return

    canonical_ids = {
        row.exercise_id
        for row in db.query(ExerciseCanonical.exercise_id)
        .filter(ExerciseCanonical.exercise_id.in_(candidate_ids))
        .all()
    }
    unresolved_ids = {
        row.exercise_id
        for row in db.query(ExerciseConflict.exercise_id)
        .filter(
            ExerciseConflict.exercise_id.in_(candidate_ids),
            ExerciseConflict.resolved == False,
        )
        .all()
    }

    for exercise_id in candidate_ids:
        if exercise_id in canonical_ids or exercise_id in unresolved_ids:
            continue

        newest = (
            db.query(WorkoutLog.exercise_title)
            .filter(WorkoutLog.exercise_id == exercise_id)
            .order_by(WorkoutLog.date.desc(), WorkoutLog.id.desc())
            .first()
        )
        oldest = (
            db.query(WorkoutLog.exercise_title)
            .filter(WorkoutLog.exercise_id == exercise_id)
            .order_by(WorkoutLog.date.asc(), WorkoutLog.id.asc())
            .first()
        )
        hevy_title = newest[0] if newest else None
        stored_title = oldest[0] if oldest else None
        if not hevy_title or not stored_title:
            continue

        stmt = sqlite_insert(ExerciseConflict).values(
            exercise_id=exercise_id,
            hevy_title=hevy_title,
            stored_title=stored_title,
            detected_at=datetime.utcnow(),
            resolved=False,
            resolved_at=None,
        ).on_conflict_do_update(
            index_elements=[ExerciseConflict.exercise_id],
            set_={
                "hevy_title": hevy_title,
                "stored_title": stored_title,
                "detected_at": datetime.utcnow(),
                "resolved": False,
                "resolved_at": None,
            },
        )
        db.execute(stmt)

def initial_import(db, canonical_map):
    context = _get_import_context(db)
    client = context["client"]

    preserved_session_state = {
        row.hevy_workout_id: {
            "verification_status": row.verification_status,
            "verified_at": row.verified_at,
            "srpe": row.srpe,
        }
        for row in db.query(WorkoutSession).all()
        if row.hevy_workout_id
    }

    db.query(WorkoutLog).delete(synchronize_session=False)
    db.query(WorkoutSession).delete(synchronize_session=False)
    db.query(ExerciseMapping).filter(
        ExerciseMapping.source == "auto",
        ExerciseMapping.is_reviewed == False,
    ).delete(synchronize_session=False)

    page = 1
    while True:
        data = client.get_workouts(page)
        workouts = data.get('workouts', [])
        page_count = data.get('page_count', 1)

        for workout in workouts:
            _process_workout(db, workout, canonical_map)

        db.commit()

        if page >= page_count:
            break
        page += 1

    if preserved_session_state:
        rebuilt_sessions = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.hevy_workout_id.in_(list(preserved_session_state.keys())))
            .all()
        )
        for session in rebuilt_sessions:
            preserved = preserved_session_state.get(session.hevy_workout_id)
            if not preserved:
                continue
            session.verification_status = preserved["verification_status"]
            session.verified_at = preserved["verified_at"]
            session.srpe = preserved["srpe"]

    _set_setting_value(db, _LAST_SYNC_SETTING_KEY, datetime.utcnow().isoformat())
    detect_exercise_conflicts(db)
    db.commit()


def incremental_sync(db, last_sync: str, canonical_map):
    context = _get_import_context(db)
    client = context["client"]

    page = 1
    while True:
        data = client.get_workout_events(since=last_sync, page=page)
        events = data.get("events", [])
        page_count = data.get("page_count", 0)

        for event in events:
            event_type = event.get("type")
            if event_type == "deleted":
                workout_id = event.get("id")
                if workout_id is None:
                    continue
                db.query(WorkoutLog).filter(WorkoutLog.workout_id == workout_id).delete(
                    synchronize_session=False,
                )
                db.query(WorkoutSession).filter(
                    WorkoutSession.hevy_workout_id == workout_id
                ).delete(synchronize_session=False)
            elif event_type == "updated":
                workout = event.get("workout")
                if workout:
                    _process_workout(db, workout, canonical_map)

        db.commit()

        if page >= page_count:
            break
        page += 1

    _set_setting_value(db, _LAST_SYNC_SETTING_KEY, datetime.utcnow().isoformat())
    detect_exercise_conflicts(db)
    db.commit()


def import_hevy_data(db):
    init_db()  # Ensure tables exist before we try to use them
    client = HevyClient(api_key=_get_client_api_key(db))
    prior_context = db.info.get(_IMPORT_CONTEXT_KEY)
    context = {
        "client": client,
        "auto_verify_confidence_threshold": _get_auto_verify_confidence_threshold(db),
        "exercise_conditioning_cache": {},
        "stats": {
            "new_sets": 0,
            "skipped_workouts_missing_date": 0,
        },
    }
    db.info[_IMPORT_CONTEXT_KEY] = context
    try:
        seed_rpe_table(db)  # Seed RPE chart if not already done

        canonical_map = load_canonical_map(db)

        if not client.test_connection():
            print("❌ Could not connect to Hevy API. Check your API key.")
            return {"new_sets": 0, "error": "Could not connect to Hevy API. Check your API key."}

        last_sync = _get_setting_value(db, _LAST_SYNC_SETTING_KEY)
        if last_sync is None:
            initial_import(db, canonical_map)
        else:
            incremental_sync(db, last_sync, canonical_map)

        stats = dict(context["stats"])
        print(f"✅ Import complete. {stats['new_sets']} new sets added.")
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        if prior_context is None:
            db.info.pop(_IMPORT_CONTEXT_KEY, None)
        else:
            db.info[_IMPORT_CONTEXT_KEY] = prior_context

if __name__ == "__main__":
    db = SessionLocal()
    try:
        import_hevy_data(db)
    finally:
        db.close()
