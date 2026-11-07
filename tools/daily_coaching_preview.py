"""Synthetic daily interpretation fixture; no account, real database or provider."""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from typing import Literal
from fastapi.responses import StreamingResponse
from tools.dashboard_preview import app, main
from database import CoachingTurn

calls=0
mode='success'
main._get_ai_api_key=lambda db: None if mode=='unavailable' else 'mock-only'


def stream(model, api_key, messages, on_finish=None):
    global calls
    calls+=1
    report=json.loads(messages[0]['content'].split('FROZEN TRAINING REPORT:\n')[1])
    daily=report['daily_context']
    content=f"Tiredness {daily['observation']['tiredness']}; perceived recovery {daily['observation']['perceived_recovery']}. Your usual range is descriptive. Discuss the next session; no programming has been changed. <img src=x onerror=window.unsafeAI=true>"
    interrupted=mode=='interrupted'
    def events():
        yield 'data: '+json.dumps(dict(choices=[dict(delta=dict(content=content))]))+'\n\n'
        if on_finish:on_finish(content,'interrupted' if interrupted else 'complete')
        yield 'data: {"error":{"message":"Mock provider interrupted"}}\n\n' if interrupted else 'data: [DONE]\n\n'
    return StreamingResponse(events(),media_type='text/event-stream')


main._stream_openrouter=stream


@app.get('/mock/daily-provider')
def state():return dict(calls=calls,mode=mode)


@app.post('/mock/daily-provider')
def set_mode(value: Literal['success','unavailable','interrupted']):
    global mode
    mode=value
    return state()


@app.post('/mock/stale-daily-turn/{conversation_id}')
def seed_stale_daily_turn(conversation_id: UUID):
    turn_id = str(uuid4())
    with main.SessionLocal() as db:
        db.add(CoachingTurn(id=turn_id, conversation_id=str(conversation_id), sequence=1,
                           message='Interpret this saved check-in.', model='mock/model',
                           status='pending', created_at=(datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()))
        db.commit()
    return {'id': turn_id}
