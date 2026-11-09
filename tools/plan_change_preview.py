"""Disposable, fully mocked AI plan-change preview (ADR 0002). No provider traffic, no real Hevy account.

python -X utf8 -m uvicorn tools.plan_change_preview:app --host 127.0.0.1 --port 18242

Asking the coach to "change my plan" streams a plan-change block written against the live planning state the
coach was actually sent (plan id, revision and pending day), so the preview also shows that state reaching it.
"""
import json
from fastapi.responses import StreamingResponse
from tools.coaching_preview import app, main
from rackbook.database import get_db

MARKER = 'LIVE PLANNING STATE (read for this message, newer than the frozen report):\n'
ordinary = main._stream_openrouter


def _change(live):
    plan = next(p for p in live['current_plans'] if p['active'])
    day = next(d for d in plan['days'] if d['status'] == 'pending' and d['exercises'])
    return dict(version='plan-change-v1', plan_id=plan['plan_id'], revision=plan['revision'],
                title='Swap <b>squat</b> for RDLs',
                rationale='Squat ran above target. <img src=x onerror="window.unsafeChange=true">',
                changes=[dict(op='replace', day=day['day'], exercise_template_id=day['exercises'][0]['exercise_template_id'],
                              new_exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 3),
                         dict(op='add', day=day['day'], exercise_template_id='face', sets=[dict(reps=15, rpe=7)] * 2)])


NEXT_WEEK = dict(version='plan-proposal-v1', title='Same again, swap in RDLs',
                 rationale='Squat moved well; day 2 gets RDLs for hinge work.',
                 sessions=[dict(name='Squat day', exercises=[dict(exercise_template_id='sq', sets=[dict(reps=1, rpe=8, ts=True), dict(reps=5, rpe=6)])]),
                           dict(name='Hinge day', exercises=[dict(exercise_template_id='rdl', sets=[dict(reps=8, rpe=7)] * 3)])])


def stream(model, api_key, messages, on_finish=None):
    asked = messages[-1]['content'].lower()
    if asked.startswith('this is our weekly coaching call'):
        content = ('Good week: both days done at target.\n```plan-proposal-v1\n' + json.dumps(NEXT_WEEK) +
                   '\n```\nAccept it, or Run it back if you would rather repeat the week.')
    elif 'change my plan' in asked:
        system = messages[0]['content']
        live = json.loads(system[system.index(MARKER) + len(MARKER):].split('\n', 1)[0])
        content = ('Here is what I would change.\n```plan-change-v1\n' + json.dumps(_change(live)) +
                   '\n```\nAccept it if it looks right.')
    else:
        return ordinary(model, api_key, messages, on_finish)

    def events():
        yield 'data: ' + json.dumps(dict(choices=[dict(delta=dict(content=content))])) + '\n\n'
        if on_finish:
            on_finish(content, 'complete')
        yield 'data: [DONE]\n\n'
    return StreamingResponse(events(), media_type='text/event-stream')


@app.on_event('startup')
def library():
    with get_db() as db:
        db.executemany('INSERT OR IGNORE INTO hevy_exercise_cache(id,title) VALUES (?,?)',
                       [('rdl', 'Romanian Deadlift (Barbell)'), ('face', 'Face Pull (Cable)')])


main._stream_openrouter = stream
