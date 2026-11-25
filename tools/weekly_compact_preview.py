"""Large completed week on preview_app's disposable databases and mocked provider."""
from tools.coaching_preview import app, main
from tools.weekly_review_fixture import seed_completed_week
from rackbook import mesocycles
import weekly_coaching
import coaching


@app.on_event('startup')
def seed_large_week():
    # This fixture tests weekly calls, independently of the daily auto-review flow.
    from database import DailyReadiness
    with main.SessionLocal() as db:
        db.query(DailyReadiness).delete()
        db.commit()
    for plan in mesocycles.list_plans():
        mesocycles.archive(plan['id'])
    seed_completed_week()


@app.get('/mock/weekly-size')
def weekly_size():
    from rackbook.weekly_call import rollover
    due = rollover()
    with main.SessionLocal() as db:
        raw = weekly_coaching.week_context(weekly_coaching.WeekReviewInput(plan_id=due['source']['id'], kind='call'), db)
        return dict(raw_chars=len(coaching.encode(raw)), call_id=due['call_id'])
