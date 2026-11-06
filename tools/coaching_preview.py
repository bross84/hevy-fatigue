"""Disposable, fully mocked coaching extension of preview_app. No provider traffic."""
import json
from datetime import date, timedelta
from fastapi.responses import StreamingResponse
from tools.preview_app import app, main
from database import DailyReadiness, WorkoutSession, WorkoutLog

main._get_ai_api_key = lambda db: 'mock-preview-only'


def stream(model, api_key, messages, on_finish=None):
    report=json.loads(messages[0]['content'].split('FROZEN TRAINING REPORT:\n')[1])
    content=f"Recorded sessions: {report['coverage']['sessions']}. Your goal is not recorded; what would you like this phase to accomplish?"
    content+=' <a href="https://pubmed.ncbi.nlm.nih.gov/19204579/">ACSM2009</a>'
    content+=' <a href="https://example.invalid/fabricated">Unverified</a><img src=x onerror="window.unsafeAI=true">'
    interrupted='interrupt' in messages[-1]['content'].lower()
    def events():
        yield 'data: '+json.dumps(dict(choices=[dict(delta=dict(content=content))]))+'\n\n'
        if on_finish: on_finish(content,'interrupted' if interrupted else 'complete')
        if interrupted:
            yield 'data: {"error":{"message":"Mock interruption; reload the saved review."}}\n\n'
        else:
            yield 'data: [DONE]\n\n'
    return StreamingResponse(events(),media_type='text/event-stream')


main._stream_openrouter=stream


@app.on_event('startup')
def seed_coaching():
    with main.SessionLocal() as db:
        db.add(DailyReadiness(date=date.today(),**{k:1 for k in main.RATING_FIELDS}))
        for i in range(12):
            day=date.today()-timedelta(days=i*8)
            db.add(WorkoutSession(hevy_workout_id=f'mock-{i}',workout_date=day,workout_title='Mock strength'))
            db.add(WorkoutLog(date=day,workout_id=f'mock-{i}',exercise_id='sq',exercise_title='Squat',set_number=1,weight_lbs=200,reps=5,rpe=7))
        db.commit()
