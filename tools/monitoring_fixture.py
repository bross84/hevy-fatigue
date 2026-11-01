"""Deterministic host output fixture, also runnable against the recorded baseline."""
from datetime import date, timedelta
import json

import main
from database import Base, engine, SessionLocal, DailyReadiness, WorkoutLog, WorkoutSession
from recommendations import RATING_FIELDS

DAY=date(2026,10,30)
class FrozenDate(date):
    @classmethod
    def today(cls): return cls(2026,10,30)
main.date_type=FrozenDate
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for i,offset in enumerate((50,40,30,10,6,3,0)):
        key=f'workout-{i}';day=DAY-timedelta(days=offset)
        db.add(WorkoutSession(hevy_workout_id=key,workout_date=day,modality='strength',verification_status='verified'))
        db.add(WorkoutLog(date=day,workout_id=key,exercise_id='squat',exercise_title='Squat',set_number=0,weight_lbs=100,reps=10,rpe=8))
    # A monitoring gap and unknown observation stay in the fixture.
    for offset in (15,14,13,9,8,7,6,5,4,3,2,1,0):
        ratings={k:2 for k in RATING_FIELDS}
        if offset==7:ratings['sore_upper_pull']=None
        db.add(DailyReadiness(date=DAY-timedelta(days=offset),**ratings))
    db.commit()
    output=main.get_training_load(days=30,db=db)
    print(json.dumps(output,sort_keys=True,default=str,allow_nan=False))
engine.dispose()
