import math
from urllib import response
from database import SessionLocal, WorkoutLog
from hevy_client import HevyClient
from datetime import datetime

def calculate_e1rm(weight, reps, rpe):
    """
    Calculates e1RM using Brzycki, adjusted for RPE.
    If RPE is 8 on a set of 5, it treats it as a set of 7 for the formula.
    """
    if not rpe:
        rpe = 10  # Assume max effort if not logged
    
    # Adjusted reps = actual reps + reps in reserve
    rir = 10 - rpe
    effective_reps = reps + rir
    
    if effective_reps == 1:
        return weight
    
    return weight / (1.0278 - (0.0278 * effective_reps))

def import_hevy_data():
    client = HevyClient()
    db = SessionLocal()
    workouts = client.test_connection()

    if not workouts:
        print("No workouts found.")
        return
    
    workouts = response.json().get('workouts', [])

    for workout in workouts:
        workout_date = workout.get('start_time')
        
        for exercise in workout.get('exercises', []):
            title = exercise.get('title') # Define the 'title' variable
            
# Here we can filter for specific lifts (e.g., Squat, Bench, Deadlift)
for set_data in exercise['sets']:
    weight_lbs = set_data.get('weight_kg', 0.0) 
    reps = set_data.get('reps', 0)
    rpe = set_data.get('rpe')

    # 2. Check that we have the necessary data to calculate e1rm
    if weight_lbs and reps:
        e1rm = calculate_e1rm(weight_lbs, reps, rpe)

        # 3. Check for duplicates in the database
        exists = db.query(WorkoutLog).filter(
            WorkoutLog.date == workout_date,
            WorkoutLog.exercise_title == title,
            # Your use of .between() is a smart way to handle float precision!
            WorkoutLog.weight_lbs.between(weight_lbs - 0.1, weight_lbs + 0.1),
            WorkoutLog.reps == reps
        ).first()

        # 4. Only add to session if it doesn't already exist
        if not exists:
            log_entry = WorkoutLog(
                date=workout_date, # Consistency: use workout_date
                exercise_title=title,
                weight_lbs=round(float(weight_lbs), 2),
                reps=reps,
                rpe=rpe,
                estimated_1rm=round(e1rm, 2)
            )
            db.add(log_entry)
    
    db.commit()
    db.close()
    print("✅ Workouts imported and e1RM calculated.")

if __name__ == "__main__":
    import_hevy_data()