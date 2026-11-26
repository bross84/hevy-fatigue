"""Custom exercises: local record first, then a Hevy copy. Frozen intent, no automatic
repost, independent movement history."""
import json
import os
import time
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import local_exercises
from .database import get_db
from .hevy_client import WorkoutNotSent

ExerciseType = Literal['weight_reps', 'reps_only', 'bodyweight_reps', 'bodyweight_assisted_reps', 'duration', 'weight_duration', 'distance_duration', 'short_distance_weight']
Equipment = Literal['none', 'barbell', 'dumbbell', 'kettlebell', 'machine', 'plate', 'resistance_band', 'suspension', 'other']
Muscle = Literal['abdominals', 'shoulders', 'biceps', 'triceps', 'forearms', 'quadriceps', 'hamstrings', 'calves', 'glutes', 'abductors', 'adductors', 'lats', 'upper_back', 'traps', 'lower_back', 'chest', 'cardio', 'neck', 'full_body', 'other']


class CreationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    title: str = Field(min_length=1, max_length=150)
    exercise_type: ExerciseType
    equipment_category: Equipment
    muscle_group: Muscle
    other_muscles: list[Muscle] = Field(default_factory=list, max_length=19)
    source_id: str | None = Field(default=None, max_length=200)

    @field_validator('title')
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Enter an exercise name.')
        return value

    @model_validator(mode='after')
    def muscles(self):
        if len(set(self.other_muscles)) != len(self.other_muscles) or self.muscle_group in self.other_muscles:
            raise ValueError('Secondary muscles must be distinct and exclude the primary muscle.')
        return self


def writes_enabled():
    return os.environ.get('HEVY_WRITES_ENABLED', '0') == '1' and os.environ.get('RACKBOOK_READ_ONLY_PREVIEW') != '1'


def _require_writes():
    if not writes_enabled():
        raise PermissionError('Exercise creation is disabled in preview or while Hevy writes are disabled.')


def status(identity):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM exercise_creations WHERE id=?', (str(identity),)).fetchone()
    if not row:
        raise LookupError('Creation attempt not found.')
    return {'request_id': row['id'], 'local_id': row['id'], 'state': row['state'], 'exercise_id': row['remote_id'],
            'title': json.loads(row['payload'])['title']}


def _finish(identity):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM exercise_creations WHERE id=?', (identity,)).fetchone()
        if row['state'] == 'complete':
            return status(identity)
        if not row['remote_id']:
            raise ValueError('No confirmed Hevy exercise ID.')
        body, prefs = json.loads(row['payload']), json.loads(row['preferences'])
        local_exercises.save_created(conn, identity, body)
        local_exercises.link_hevy(conn, identity, row['remote_id'])
        conn.execute('INSERT INTO hevy_exercise_cache(id,title,primary_muscle) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, primary_muscle=excluded.primary_muscle', (row['remote_id'], body['title'], body['muscle_group']))
        if prefs:
            # Only equipment/rest/display increments; strength records and sources are never inherited.
            conn.execute('INSERT OR IGNORE INTO exercise_refs(exercise_template_id,step_kg,step_lb,bar_kg,chain_kg,rest_sec,weight_unit) VALUES(?,?,?,?,?,?,?)', (row['remote_id'], *[prefs[k] for k in ('step_kg','step_lb','bar_kg','chain_kg','rest_sec','weight_unit')]))
        conn.execute("UPDATE exercise_creations SET state='complete' WHERE id=?", (identity,))
    return status(identity)


def create(data, client):
    _require_writes()
    identity = str(data.request_id)
    body = data.model_dump(mode='json', exclude={'request_id'})
    payload = json.dumps(body, sort_keys=True)
    with get_db() as conn:
        old = conn.execute('SELECT * FROM exercise_creations WHERE id=?', (identity,)).fetchone()
    resend = False
    if old:
        if old['remote_id'] or old['state'] != 'rejected':
            if old['payload'] != payload:
                raise ValueError('This creation ID already belongs to different exercise details.')
            return _finish(identity) if old['remote_id'] else status(identity)
        # Hevy definitely did not create it. The athlete's tap may resend it, edited or not.
        resend = True
    # Capture existing identities before the write, so reconciliation cannot claim an older exercise.
    catalog = client.list_exercise_templates()
    if any(e['title'].strip().casefold() == data.title.casefold() for e in catalog):
        raise ValueError('That exercise name already exists. Choose a distinct name or select the existing exercise.')
    prefs = {}
    if data.source_id:
        source = client.get_exercise_template(data.source_id)
        if source['title'].strip().casefold() == data.title.casefold():
            raise ValueError('Give the duplicate a distinct name.')
        if source.get('type') == data.exercise_type and source.get('equipment') == data.equipment_category:
            with get_db() as conn:
                ref = conn.execute('SELECT step_kg,step_lb,bar_kg,chain_kg,rest_sec,weight_unit FROM exercise_refs WHERE exercise_template_id=?', (data.source_id,)).fetchone()
                prefs = dict(ref) if ref else {}
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        # Serializes concurrent tabs even when they supply different UUIDs.
        old = conn.execute('SELECT id FROM exercise_creations WHERE id != ? AND title_key=? AND state != ?', (identity, data.title.casefold(), 'rejected')).fetchone()
        if old:
            raise ValueError('A creation attempt already exists for this name. Reopen it and check its status.')
        if local_exercises.title_taken(conn, data.title, identity):
            raise ValueError('That exercise name already exists. Choose a distinct name or select the existing exercise.')
        current = conn.execute('SELECT state FROM exercise_creations WHERE id=?', (identity,)).fetchone()
        before, now = json.dumps([str(e['id']) for e in catalog]), time.time()
        if resend:
            if not current or current['state'] != 'rejected':
                raise ValueError('This exercise is already being sent. Check its status.')
            conn.execute("UPDATE exercise_creations SET payload=?,title_key=?,state='sending',before_ids=?,preferences=?,created_at=? WHERE id=?",
                         (payload, data.title.casefold(), before, json.dumps(prefs), now, identity))
        elif current:
            raise ValueError('A creation attempt already exists for this name. Reopen it and check its status.')
        else:
            conn.execute('INSERT INTO exercise_creations VALUES(?,?,?,?,?,?,?,?)', (identity, payload, data.title.casefold(), 'sending', None, before, json.dumps(prefs), now))
        # The local record is committed with the journal, before Hevy is contacted.
        local_exercises.save_created(conn, identity, body)
    try:
        remote_id = client.create_exercise_template({k:v for k,v in body.items() if k != 'source_id'})
    except Exception as exc:
        rejected = isinstance(exc, WorkoutNotSent) or isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400,401,403,404,422,429)
        with get_db() as conn:
            conn.execute('UPDATE exercise_creations SET state=? WHERE id=?', ('rejected' if rejected else 'uncertain', identity))
        return status(identity)
    # Persist remote identity before any required local effects.
    with get_db() as conn:
        conn.execute("UPDATE exercise_creations SET remote_id=?,state='acknowledged' WHERE id=?", (str(remote_id), identity))
    return _finish(identity)


def reconcile(identity, client):
    identity = str(identity)
    with get_db() as conn:
        row = conn.execute('SELECT * FROM exercise_creations WHERE id=?', (identity,)).fetchone()
    if not row:
        raise LookupError('Creation attempt not found.')
    if row['remote_id']:
        return _finish(identity)
    if row['state'] == 'rejected' or row['state'] == 'sending' and time.time()-row['created_at'] < 120:
        return status(identity)
    body, before = json.loads(row['payload']), set(json.loads(row['before_ids']))
    matches = [e for e in client.list_exercise_templates() if str(e['id']) not in before and e.get('is_custom') is True
               and e.get('title') == body['title'] and e.get('type') == body['exercise_type']
               and e.get('equipment') == body['equipment_category'] and e.get('primary_muscle_group') == body['muscle_group']
               and sorted(e.get('secondary_muscle_groups') or []) == sorted(body['other_muscles'])]
    if len(matches) != 1:
        return status(identity)
    with get_db() as conn:
        conn.execute("UPDATE exercise_creations SET remote_id=?,state='acknowledged' WHERE id=? AND remote_id IS NULL", (str(matches[0]['id']), identity))
    return _finish(identity)
