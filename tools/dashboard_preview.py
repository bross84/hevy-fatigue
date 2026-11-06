"""Populated disposable dashboard fixtures on top of the fully mocked preview."""
from datetime import date, timedelta
import os
from pathlib import Path

from tools.preview_app import app, main
from database import DailyReadiness, ExerciseMapping, WorkoutLog, WorkoutSession

assert Path(main.SessionLocal.kw['bind'].url.database).resolve() == Path(os.environ['DB_PATH']).resolve()


@app.on_event('startup')
def seed_dashboard():
    patterns = [('Squat (Barbell)', 'pct_quad_dom'),
                ('Romanian Deadlift (Barbell)', 'pct_posterior'),
                ('Bench Press (Barbell)', 'pct_upper_push'),
                ('Lat Pulldown (Cable)', 'pct_upper_pull')]
    with main.SessionLocal() as db:
        for offset in range(1, 32):
            if offset == 3:  # An actual monitoring gap, not a zero rating.
                continue
            values = {key: 1 for key in main.RATING_FIELDS}
            values['tiredness'] = offset % 3
            db.add(DailyReadiness(date=date.today() - timedelta(days=offset), **values))
        for title, column in patterns:
            db.add(ExerciseMapping(exercise_title=title, **{column: 1.0}))
        for index, offset in enumerate(range(1, 61, 3)):
            day = date.today() - timedelta(days=offset)
            identity = 'dashboard-mock-' + str(index)
            db.add(WorkoutSession(hevy_workout_id=identity, workout_date=day,
                                  workout_title='ST · Full body ' + ('A' if index % 2 == 0 else 'B'),
                                  modality='strength', duration_minutes=45, srpe=7))
            for movement, (title, _) in enumerate(patterns):
                for number in range(1, 4):
                    db.add(WorkoutLog(date=day, workout_id=identity, workout_title='Mock full body',
                                      exercise_id='mock-' + str(movement), exercise_title=title,
                                      set_number=number, weight_lbs=180 - movement * 20,
                                      reps=5 + movement, rpe=7))
        db.commit()
