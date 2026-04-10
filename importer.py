from database import SessionLocal, WorkoutLog, init_db
from hevy_client import HevyClient
from datetime import datetime
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

def calculate_e1rm(weight, reps, rpe):
    """
    Calculates e1RM using Brzycki formula, adjusted for RPE.
    RIR (reps in reserve) is added to actual reps to get effective reps.
    """
    if not rpe:
        rpe = 10  # Assume max effort if RPE not logged

    if not weight or not reps or reps <= 0:
        return None

    rir = 10 - rpe
    effective_reps = reps + rir

    if effective_reps == 1:
        return weight

    return weight / (1.0278 - (0.0278 * effective_reps))

def import_hevy_data():
    init_db()  # Ensure tables exist before we try to use them
    client = HevyClient()
    db = SessionLocal()

    if not client.test_connection():
        print("❌ Could not connect to Hevy API. Check your API key.")
        db.close()
        return

    page = 1
    total_added = 0

    while True:
        data = client.get_workouts(page)
        workouts = data.get('workouts', [])
        page_count = data.get('page_count', 1)

        for workout in workouts:
            workout_id = workout.get('id')
            raw_date = workout.get('start_time')
            workout_date = datetime.fromisoformat(raw_date).date() if raw_date else None

            for exercise in workout.get('exercises', []):
                title = exercise.get('title')
                exercise_id = exercise.get('exercise_template_id')

                for set_data in exercise.get('sets', []):
                    if set_data.get('type') == 'warmup':
                        continue  # Skip warmup sets — working sets only

                    set_number = set_data.get('index')
                    weight_kg = set_data.get('weight_kg') or 0.0
                    reps = set_data.get('reps') or 0
                    rpe = set_data.get('rpe')

                    weight_lbs = round(weight_kg * 2.20462, 2) if weight_kg else None

                    e1rm = None
                    if weight_lbs and reps:
                        result = calculate_e1rm(weight_lbs, reps, rpe)
                        if result:
                            e1rm = round(result, 2)

                    # Insert and silently skip if this set already exists
                    stmt = sqlite_insert(WorkoutLog).values(
                        date=workout_date,
                        workout_id=workout_id,
                        exercise_id=exercise_id,
                        exercise_title=title,
                        set_number=set_number,
                        weight_lbs=weight_lbs,
                        reps=reps,
                        rpe=rpe,
                        estimated_1rm=e1rm
                    ).on_conflict_do_nothing()
                    result = db.execute(stmt)
                    if result.rowcount:
                        total_added += 1

        db.commit()

        if page >= page_count:
            break
        page += 1

    db.close()
    print(f"✅ Import complete. {total_added} new sets added.")

if __name__ == "__main__":
    import_hevy_data()
