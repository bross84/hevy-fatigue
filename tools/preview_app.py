"""Disposable local preview with Hevy mocked below the routes. No real credentials.

python -X utf8 -m uvicorn tools.preview_app:app --host 127.0.0.1 --port 18127
"""
import os
from pathlib import Path
import tempfile
import atexit
from uuid import uuid4

_data = tempfile.TemporaryDirectory(prefix='hevy-combined-preview-')
os.environ.update(DB_PATH=str(Path(_data.name)/'host.db'),
                  RACKBOOK_DB_PATH=str(Path(_data.name)/'rack.db'),
                  FERNET_KEY_PATH=str(Path(_data.name)/'app.key'),
                  HEVY_WRITES_ENABLED='0', HEVY_FATIGUE_DB_PATH=str(Path(_data.name)/'host.db'))

import main
from rackbook import main as training, hevy_client, mesocycles
from rackbook.database import get_db


class MockHevy:
    workouts = {}

    def list_workouts(self, page=1, page_size=10):
        return {'page':page,'page_count':1,'workouts':list(self.workouts.values())}

    def exercise_history(self, *args, **kwargs): return []
    def create_workout(self, body):
        workout={**body['workout'],'id':str(uuid4())}
        for exercise in workout['exercises']: exercise.setdefault('title','Squat (Barbell)')
        self.workouts[workout['id']]=workout
        return workout
    def get_workout(self, workout_id): return self.workouts[workout_id]
    def sync_exercise_cache(self): return 1
    def list_body_measurements(self, *args, **kwargs): return {"page":1,"page_count":1,"body_measurements":[]}


hevy_client.HevyClient=MockHevy
main.import_hevy_data=lambda db:{'status':'mocked preview','imported':0}
app=main.app
atexit.register(lambda: main.SessionLocal.kw['bind'].dispose())


@app.on_event('startup')
def seed():
    import training_integration
    training_integration.request_monitoring_refresh=lambda workout_id:'pending'
    with get_db() as db:
        db.execute("INSERT INTO hevy_exercise_cache(id,title,primary_muscle) VALUES ('sq','Squat (Barbell)','quadriceps')")
    plan=mesocycles.save_plan(mesocycles.PlanInput(name='Mock preview plan',weeks=[dict(name='Week',sessions=[
        dict(id='day-one',name='Mock Workout',exercises=[dict(exercise_template_id='sq',title='Squat (Barbell)',sets=[
            dict(reps=1,rpe=8,weight_kg=100,ts=True),dict(reps=5,rpe=5,weight_kg=80)])]),
        dict(id='day-two',name='Next Workout',exercises=[dict(exercise_template_id='sq',title='Squat (Barbell)',sets=[dict(reps=5,rpe=7)])])])]))
    mesocycles.activate(plan['id'])
