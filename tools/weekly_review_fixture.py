"""Synthetic completed week for isolated tests and disposable previews only."""
import json
from datetime import timedelta
from rackbook import database as logger


def seed_completed_week():
    from rackbook import mesocycles, session_review
    from datetime import datetime, timezone
    sessions = [dict(id=f'day{day}', name=f'Day {day}', exercises=[dict(
        exercise_template_id=f'movement-{ex}', title=f'Long exercise title {ex}',
        sets=[dict(reps=5, rpe=7) for _ in range(4)]) for ex in range(6)]) for day in range(3)]
    plan = mesocycles.save_plan(mesocycles.PlanInput(name='Large completed week', weeks=[dict(name='Week', sessions=sessions)]))
    chart = [dict(rpe=rpe / 2, reps=reps, percentage=1 / (1 + reps / 30))
             for rpe in range(8, 21) for reps in range(1, 61)]
    for day, session in enumerate(sessions):
        stamp = (datetime.now(timezone.utc) - timedelta(days=3-day)).isoformat()
        workout = f'completed-{day}'
        prescribed, actual = [], []
        for ex in session['exercises']:
            ident = ex['exercise_template_id']
            prescribed.append(dict(id=ident, exercise_template_id=ident, title=ex['title'], notes='',
                sets=[dict(id=f'{ident}-{n}', type='normal', reps=5, rpe=7, weight_kg=100) for n in range(4)]))
            actual.append(dict(exercise_template_id=ident, title=ex['title'], sets=[dict(
                type='warmup' if n == 0 else 'normal', weight_kg=102.512345, reps=5,
                rpe=3.5 if n == 0 else (None if n == 3 else 7), target_rpe=7,
                review=dict(exercise_id=ident, set_id=f'{ident}-{n}', rpe_source='entered',
                            basis='e1rm', actual_percentage=.8, manual_weight=False, ls_enabled=True)) for n in range(4)]))
        prescription = dict(version=1, source='plan', name=session['name'], plan_id=plan['id'],
                            session_id=session['id'], plan_revision=1, exercises=prescribed, rpe_chart=chart)
        review = session_review.build(dict(title=session['name'], prescription=prescription, exercises=actual))
        with logger.get_db() as conn:
            conn.execute('INSERT INTO session_reviews VALUES (?,?,?,?,?)',
                (workout, stamp, json.dumps(prescription), json.dumps(actual), json.dumps(review)))
            for ex in actual:
                for n, entry in enumerate(ex['sets'], 1):
                    conn.execute('INSERT INTO logged_sets(hevy_workout_id,workout_start,exercise_template_id,exercise_title,set_number,set_type,weight_kg,reps,rpe,target_rpe) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (workout, stamp, ex['exercise_template_id'], ex['title'], n, entry['type'],entry['weight_kg'],entry['reps'],entry['rpe'],entry['target_rpe']))
        mesocycles.mark_completed(plan['id'], session['id'])
        with logger.get_db() as conn:
            conn.execute('UPDATE mesocycle_completions SET hevy_workout_id=?,workout_start=? WHERE mesocycle_id=? AND session_id=?',
                         (workout, stamp, plan['id'], session['id']))
    return plan
