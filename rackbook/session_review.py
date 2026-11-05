"""Frozen session evidence and descriptive review; never writes prescriptions."""
from contextlib import closing
from datetime import datetime
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .database import get_db


class PrescribedSet(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    reps: int | None = Field(default=None, ge=0, le=1000)
    rpe: float | None = Field(default=None, ge=0, le=10)
    weight_kg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    type: Literal['warmup', 'normal', 'failure', 'dropset'] = 'normal'
    ts: bool = False


class PrescribedExercise(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    exercise_template_id: str = Field(min_length=1, max_length=200)
    title: str = Field(max_length=200)
    notes: str = Field(default='', max_length=4000)
    sets: list[PrescribedSet] = Field(max_length=200)


class ChartCell(BaseModel):
    rpe: float = Field(ge=0, le=10, allow_inf_nan=False)
    reps: int = Field(ge=1, le=1000)
    percentage: float = Field(gt=0, le=1, allow_inf_nan=False)


class Prescription(BaseModel):
    version: Literal[1] = 1
    source: Literal['plan', 'repeated_workout', 'ad_hoc']
    name: str = Field(max_length=4000)
    plan_revision: int | None = Field(default=None, ge=0)
    plan_id: str | None = Field(default=None, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)
    exercises: list[PrescribedExercise] = Field(max_length=100)
    rpe_chart: list[ChartCell] = Field(max_length=2000)

    @model_validator(mode='after')
    def unique_ids(self):
        ids = [s.id for ex in self.exercises for s in ex.sets]
        if len(ids) != len(set(ids)) or len({ex.id for ex in self.exercises}) != len(self.exercises):
            raise ValueError('Prescription identities must be unique')
        return self


class SetEvidence(BaseModel):
    set_id: str = Field(min_length=1, max_length=200)
    exercise_id: str = Field(min_length=1, max_length=200)
    suggested_weight_kg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    manual_weight: bool
    ls_enabled: bool
    basis: Literal['e1rm', 'tm', 'manual']
    completed_at: datetime
    rpe_source: Literal['entered', 'copied_target', 'unrated', 'unknown']
    actual_percentage: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)


class SetReview(BaseModel):
    role: str
    set_type: str
    planned_reps: int | None
    planned_weight_kg: float | None
    actual_reps: int | None
    planned_rpe: float | None
    target_rpe: float | None
    actual_rpe: float | None
    weight_kg: float | None
    suggested_weight_kg: float | None
    rpe_source: str
    e1rm_kg: float | None
    manual_weight: bool | None
    ls_enabled: bool | None


class MovementReview(BaseModel):
    exercise_template_id: str
    title: str
    weight_unit: Literal['kg', 'lb']
    planned_sets: int | None
    completed_sets: int
    omitted_sets: int | None
    added_sets: int | None
    planned_reps: int | None
    completed_reps: int | None
    opening_e1rm_kg: float | None
    last_e1rm_kg: float | None
    change_pct: float | None
    notes: list[str]
    sets: list[SetReview]


class SessionReview(BaseModel):
    version: Literal['session-description-v1'] = 'session-description-v1'
    title: str
    prescription_source: str
    movements: list[MovementReview]
    notes: list[str]


class ReviewResponse(BaseModel):
    available: bool
    reason: str | None = None
    review: SessionReview | None = None
    prescription: Prescription | None = None


def build(payload):
    prescription = payload.get('prescription')
    originals = {ex['id']: ex for ex in (prescription or {}).get('exercises', [])}
    baseline_known = prescription is not None and prescription['source'] != 'ad_hoc'
    actuals = {}
    for index, ex in enumerate(payload['exercises']):
        evidence = next((s.get('review') for s in ex['sets'] if s.get('review')), None)
        key = evidence['exercise_id'] if evidence else f'unknown-{index}'
        actuals[key] = ex
    movements = []
    for key in dict.fromkeys([*originals, *actuals]):
        original, actual = originals.get(key), actuals.get(key)
        info = actual or original
        planned = {s['id']: s for s in (original or {}).get('sets', []) if s['type'] != 'warmup'}
        working = [s for s in (actual or {}).get('sets', []) if s['type'] != 'warmup']
        matched, details = set(), []
        for s in working:
            evidence = s.get('review') or {}
            target = planned.get(evidence.get('set_id'))
            if target:
                matched.add(target['id'])
            # Only explicitly entered effort supplies performance evidence. A
            # copied target is still shown as recorded, never treated as measured.
            pct = evidence.get('actual_percentage')
            e1rm = s['weight_kg'] / pct if (evidence.get('rpe_source') == 'entered'
                and pct and s.get('rpe') is not None and s.get('reps', 0) and s.get('weight_kg')) else None
            earlier = working[:len(details)]
            details.append(dict(role='top set' if s.get('ts') else 'back-off' if any(x.get('ts') for x in earlier) else s['type'],
                set_type=s['type'],
                planned_reps=target.get('reps') if target else None, actual_reps=s.get('reps'),
                planned_weight_kg=target.get('weight_kg') if target else None,
                planned_rpe=target.get('rpe') if target else None, target_rpe=s.get('target_rpe'), actual_rpe=s.get('rpe'),
                weight_kg=s.get('weight_kg'), suggested_weight_kg=evidence.get('suggested_weight_kg'),
                rpe_source=evidence.get('rpe_source', 'unknown'), e1rm_kg=e1rm,
                manual_weight=evidence.get('manual_weight'), ls_enabled=evidence.get('ls_enabled')))
        timed = sorted(zip(working, details), key=lambda pair:
            datetime.fromisoformat(pair[0]['review']['completed_at'].replace('Z', '+00:00')).timestamp()
            if (pair[0].get('review') or {}).get('completed_at') else float('inf'))
        first = timed[0][1]['e1rm_kg'] if timed else None
        last = timed[-1][1]['e1rm_kg'] if timed else None
        # Report endpoint change only for like-for-like prescriptions and roles.
        comparable = len(details) >= 2 and first and last and all(
            (s['actual_reps'], s['actual_rpe'], s['role'], s['set_type']) ==
            (details[0]['actual_reps'], details[0]['actual_rpe'], details[0]['role'], details[0]['set_type']) for s in details)
        notes = []
        if not comparable:
            notes.append('No like-for-like within-session change: sets differ in reps, effort or role, or lack entered RPE.')
        if any((s.get('review') or {}).get('completed_at') is None for s in working):
            notes.append('Set order is shown; completion timing is unavailable.')
        copied = sum(s['rpe_source'] == 'copied_target' for s in details)
        if copied:
            notes.append(f'{copied} set(s) used the target as actual RPE; excluded from performance comparisons.')
        item = dict(exercise_template_id=info['exercise_template_id'], title=info.get('title') or info['exercise_template_id'],
            weight_unit=(actual or {}).get('weight_unit') or payload.get('weight_unit') or 'kg',
            planned_sets=len(planned) if baseline_known else None, completed_sets=len(working),
            omitted_sets=len(planned.keys() - matched) if baseline_known else None,
            added_sets=len(working) - len(matched) if baseline_known else None,
            planned_reps=sum(s['reps'] for s in planned.values()) if baseline_known and all(s.get('reps') is not None for s in planned.values()) else None,
            completed_reps=sum(s['reps'] for s in working) if all(s.get('reps') is not None for s in working) else None,
            opening_e1rm_kg=first, last_e1rm_kg=last,
            change_pct=(last / first - 1) * 100 if comparable else None,
            notes=notes, sets=details)
        movements.append(item)
    return dict(version='session-description-v1', title=payload['title'],
        prescription_source=(prescription or {}).get('source', 'unavailable'), movements=movements,
        notes=['Descriptive estimates, not a fatigue diagnosis or programming recommendation.',
               'e1RM uses the RPE-table percentage captured with each completed set; it is not a measured maximum.',
               'Rest, exercise order and RPE estimation can affect these values; completion spacing is not measured rest.',
               'This review describes this workout only; comparisons across sessions are not included.'])


def record(payload, workout_id, connection):
    if not payload.get('prescription'):
        return  # Legacy frozen saves stay compatible; never invent a baseline.
    review = build(payload)
    connection.execute('INSERT INTO session_reviews (hevy_workout_id, workout_start, prescription, actual, review) VALUES (?,?,?,?,?)',
        (workout_id, payload['start_time'], json.dumps(payload['prescription'], allow_nan=False),
         json.dumps(payload['exercises'], allow_nan=False), json.dumps(review, allow_nan=False)))


def read(workout_id):
    with closing(get_db()) as conn:
        row = conn.execute('SELECT prescription, review FROM session_reviews WHERE hevy_workout_id=?', (workout_id,)).fetchone()
    if row is None:
        return dict(available=False, reason='No preserved session prescription is available for this workout.')
    return dict(available=True, prescription=json.loads(row['prescription']), review=json.loads(row['review']))
