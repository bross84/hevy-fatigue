"""Week text in the builder: read-only preview, and an explicit save of several weeks as drafts.

Preview writes nothing. One week is loaded into the builder by the page and saved there like any
other edit. Text holding several weeks is saved here as one inactive draft per week, all in one
transaction; nothing is activated, completed or sent to Hevy. Movement titles come from local records.
"""
from uuid import uuid4

from pydantic import ValidationError

from .database import get_db
from . import mesocycles, plan_proposals, week_text


class WeekTextError(Exception):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


def _read(conn, text, choices):
    result = week_text.parse_week_text(text, plan_proposals.movement_titles(conn), choices)
    for week in result['weeks']:
        week['sessions'] = week_text.plan_sessions(week, lambda: str(uuid4())) if result['ready'] else []
    return result


def preview(text: str, choices: dict[str, str]):
    with get_db() as conn:
        return _read(conn, text, choices)


def _plan(week, program_name, cycle):
    data = dict(name=f"Week {week['week']}", program_name=program_name, cycle=cycle, week=week['week'],
                notes='', weeks=[dict(name=f"Week {week['week']}", sessions=week['sessions'])])
    try:
        return mesocycles.PlanInput.model_validate(data)
    except ValidationError as exc:
        raise WeekTextError(f"Week {week['week']}: " + '; '.join(plan_proposals.problems(exc)))


def save_drafts(text: str, choices: dict[str, str], program_name: str, cycle: int):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result = _read(conn, text, choices)
        if not result['ready']:
            raise WeekTextError('Fix the problems in the preview before saving.')
        plans = [_plan(week, program_name, cycle) for week in result['weeks']]
        saved = [dict(id=mesocycles.insert_draft(conn, plan), name=plan.name) for plan in plans]
    return dict(saved=saved)
