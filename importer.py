from database import SessionLocal, WorkoutLog, init_db
from hevy_client import HevyClient
from rpe_table import calculate_e1rm, seed_rpe_table
from exercise_classifier import ensure_exercise_mapped
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

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

        while True:
            data = client.get_workouts(page)
            workouts = data.get('workouts', [])
            page_count = data.get('page_count', 1)

            for workout in workouts:
                workout_id = workout.get('id')
                workout_title = workout.get('title')
                raw_date = workout.get('start_time')

                # start_time is required for WorkoutLog.date (NOT NULL); skip invalid payloads.
                if not raw_date:
                    skipped_workouts_missing_date += 1
                    continue
                try:
                    workout_date = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).date()
                except ValueError:
                    skipped_workouts_missing_date += 1
                    continue

                for exercise in workout.get('exercises', []):
                    title = exercise.get('title')
                    exercise_id = exercise.get('exercise_template_id')

                    # Auto-classify exercise if not already in the mapping table
                    ensure_exercise_mapped(title, db)

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
                            estimated_1rm=e1rm
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
