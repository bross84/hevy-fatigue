from database import SessionLocal, WorkoutLog, WorkoutSession, ExerciseMapping, init_db
from hevy_client import HevyClient
from rpe_table import calculate_e1rm, seed_rpe_table
from exercise_classifier import ensure_exercise_mapped
from datetime import datetime, timezone
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


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


def _infer_modality(workout_title, exercises, conditioning_cache):
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


def _resolve_verification(modality, confidence, duration_minutes):
    if duration_minutes is None:
        return "pending", None

    if modality in {"strength", "hypertrophy"} and confidence >= 0.80:
        return "verified", datetime.utcnow()

    return "pending", None

def import_hevy_data(api_key: str | None = None):
    init_db()  # Ensure tables exist before we try to use them
    client = HevyClient(api_key=api_key)
    db = SessionLocal()
    try:
        seed_rpe_table(db)  # Seed RPE chart if not already done

        if not client.test_connection():
            print("❌ Could not connect to Hevy API. Check your API key.")
            return {"new_sets": 0, "error": "Could not connect to Hevy API. Check your API key."}

        page = 1
        total_added = 0
        skipped_workouts_missing_date = 0
        exercise_conditioning_cache: dict[str, bool] = {}

        while True:
            data = client.get_workouts(page)
            workouts = data.get('workouts', [])
            page_count = data.get('page_count', 1)

            for workout in workouts:
                workout_id = workout.get('id')
                workout_title = workout.get('title')
                raw_start = workout.get('start_time')
                raw_end = workout.get('end_time')
                start_dt = _parse_hevy_datetime(raw_start)
                end_dt = _parse_hevy_datetime(raw_end)
                raw_date = raw_start

                # start_time is required for WorkoutLog.date (NOT NULL); skip invalid payloads.
                if not raw_date:
                    skipped_workouts_missing_date += 1
                    continue
                try:
                    workout_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).date()
                except ValueError:
                    skipped_workouts_missing_date += 1
                    continue

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

                modality, modality_confidence = _infer_modality(
                    workout_title=workout_title,
                    exercises=exercises,
                    conditioning_cache=exercise_conditioning_cache,
                )
                duration_minutes = _compute_duration_minutes(start_dt, end_dt)
                verification_status, verified_at = _resolve_verification(
                    modality=modality,
                    confidence=modality_confidence,
                    duration_minutes=duration_minutes,
                )

                session_stmt = sqlite_insert(WorkoutSession).values(
                    hevy_workout_id=workout_id,
                    workout_date=workout_date,
                    workout_title=workout_title,
                    start_time=start_dt,
                    end_time=end_dt,
                    duration_minutes=duration_minutes,
                    modality=modality,
                    modality_confidence=modality_confidence,
                    verification_status=verification_status,
                    verified_at=verified_at,
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
                        "verification_status": verification_status,
                        "verified_at": verified_at,
                        "updated_at": datetime.utcnow(),
                    },
                )
                db.execute(session_stmt)

                for exercise in exercises:
                    title = exercise.get('title')
                    exercise_id = exercise.get('exercise_template_id')

                    is_conditioning = exercise_conditioning_cache.get(title, False)

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

                        # Insert and silently skip if this set already exists
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
                        ).on_conflict_do_nothing()
                        result = db.execute(stmt)
                        if result.rowcount:
                            total_added += 1

            db.commit()

            if page >= page_count:
                break
            page += 1

        print(f"✅ Import complete. {total_added} new sets added.")
        return {
            "new_sets": total_added,
            "skipped_workouts_missing_date": skipped_workouts_missing_date,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    import_hevy_data()
