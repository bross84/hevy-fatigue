"""Disposable, fully mocked AI plan-proposal preview. No provider traffic, no real Hevy account.

python -X utf8 -m uvicorn tools.plan_proposal_preview:app --host 127.0.0.1 --port 18241
"""
import json
from fastapi.responses import StreamingResponse
from tools.coaching_preview import app, main

PROPOSAL = dict(
    version='plan-proposal-v1', title='Deload <b>week</b>',
    rationale='Recent sessions ran above target. <img src=x onerror="window.unsafeProposal=true">',
    sessions=[dict(name='Squat day', exercises=[dict(
        exercise_template_id='sq', notes='Keep it smooth.',
        sets=[dict(reps=3, rpe=7, ts=True), dict(reps=5, rpe=7), dict(reps=5, rpe=7)])])])
ordinary = main._stream_openrouter


def stream(model, api_key, messages, on_finish=None):
    if 'propose a week' not in messages[-1]['content'].lower():
        return ordinary(model, api_key, messages, on_finish)
    content = ('Here is a week to discuss.\n```plan-proposal-v1\n' + json.dumps(PROPOSAL) +
               '\n```\nWhat would you change?')

    def events():
        yield 'data: ' + json.dumps(dict(choices=[dict(delta=dict(content=content))])) + '\n\n'
        if on_finish:
            on_finish(content, 'complete')
        yield 'data: [DONE]\n\n'
    return StreamingResponse(events(), media_type='text/event-stream')


main._stream_openrouter = stream
