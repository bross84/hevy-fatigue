"""Mocked preview with a lower-joint rise above usual (#154). Disposable data only.

python -X utf8 -m uvicorn tools.joint_preview:app --host 127.0.0.1 --port 18154
"""
from datetime import timedelta

from tools import preview_app
from database import DailyReadiness, ExerciseMapping, SessionLocal, WorkoutLog, WorkoutSession
from rackbook.local_day import local_today

app = preview_app.app


@app.on_event('startup')
def seed_joint_rise():
    today = local_today()
    ratings = [1] * 30 + [2, 1, 2, 1, 2, 2]
    with SessionLocal() as db:
        for i, rating in enumerate(ratings):
            day = today - timedelta(days=len(ratings) - 1 - i)
            db.add(DailyReadiness(date=day, joint_lower=rating, joint_upper=0, tiredness=1, perceived_recovery=1,
                                  sore_quad_dom=1, sore_posterior=1, sore_upper_push=0, sore_upper_pull=0))
        db.add(ExerciseMapping(exercise_title='Squat (Barbell)', pct_quad_dom=1.0, is_reviewed=True))
        db.add(ExerciseMapping(exercise_title='Romanian Deadlift (Barbell)', pct_posterior=1.0, is_reviewed=True))
        db.add(ExerciseMapping(exercise_title='Bench Press (Barbell)', pct_upper_push=1.0, is_reviewed=True))
        plan = {1: 'Squat (Barbell)', 3: 'Squat (Barbell)', 5: 'Squat (Barbell)', 8: 'Romanian Deadlift (Barbell)',
                10: 'Squat (Barbell)', 12: 'Romanian Deadlift (Barbell)', 15: 'Romanian Deadlift (Barbell)',
                17: 'Romanian Deadlift (Barbell)', 19: 'Romanian Deadlift (Barbell)', 22: 'Bench Press (Barbell)'}
        for offset, title in plan.items():
            day = today - timedelta(days=offset)
            key = f'preview-{offset}'
            db.add(WorkoutSession(hevy_workout_id=key, workout_date=day, workout_title='Preview strength'))
            db.add(WorkoutLog(workout_id=key, date=day, exercise_id=title[:8], exercise_title=title,
                              set_number=1, weight_lbs=185, reps=5, rpe=7))
        db.commit()
