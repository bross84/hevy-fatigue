"""Provisional, dismissible session advice. Never edits a plan or posts to Hevy."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from .database import get_db

VERSION = 'provisional-session-v1'
HISTORY_DAYS = 90
STALE_DAYS = 21
CHECKIN_DAYS = 7
DISMISS_DAYS = 7
HIGH_RATING = 3  # Original 0–4 scale; larger = worse. Provisional product rule.
LOW_RATING = 1
CAPACITY_CHANGE_PCT = 3.0
RPE_OVERSHOOT = 1.0
MIN_REPEAT = 2
MIN_TREND = 3
MAX_INCREASE_SETS = 6


def stamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


class AdviceError(Exception):
    def __init__(self, message, status=409):
        self.status, self.message = status, message
        super().__init__(message)


class PlannedSet(BaseModel):
    reps: int = Field(ge=1, le=1000)
    rpe: float | None = Field(default=None, ge=4, le=10)
    ts: bool = False


class AdviceRequest(BaseModel):
    session_id: UUID
    exercise_id: str = Field(min_length=1, max_length=200)
    exercise_template_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    workout_start: datetime
    local_date: date
    sets: list[PlannedSet] = Field(min_length=1, max_length=100)
    automatic_weights: bool = True
    started: bool = False
    pain: bool = False

    @model_validator(mode='after')
    def one_top_set(self):
        if sum(s.ts for s in self.sets)>1:
            raise ValueError('Only one top set is supported per movement')
        return self


class Dose(BaseModel):
    working_sets: int = Field(ge=0, le=100)
    reps: int | None = Field(default=None, ge=1, le=1000)
    target_rpe: float | None = Field(default=None, ge=4, le=10)


class DecisionRequest(BaseModel):
    id: UUID
    action: Literal['accept', 'modify', 'dismiss', 'not_now']
    modification: Dose | None = None
    reason: str = Field(default='', max_length=1000)
    expected_decision_id: UUID | None = None

    @model_validator(mode='after')
    def modification_only_when_modified(self):
        if (self.action == 'modify') != (self.modification is not None):
            raise ValueError('Modify requires an intended dose; other decisions must not supply one')
        return self


class AdviceLink(BaseModel):
    recommendation_id: UUID
    decision_id: UUID | None = None


class AdviceView(BaseModel):
    id: str
    model_version: str
    title: str
    action: str
    message: str
    proposed: Dose
    confidence: str
    reasons: list[str]
    limitations: list[str]
    evidence: dict
    suppressed: bool
    decision: dict | None


class OutcomeView(BaseModel):
    recommendation_id: str
    title: str
    decision: dict | None
    actual: dict
    intended: Dose | None
    matched_intended_sets: bool | None
    matched_intended_reps: bool | None = None
    matched_intended_rpe: bool | None = None
    next_checkin: dict | None = None


def host_context(day, exercise_id=None, cutoff=None):
    """Fixed, read-only bridge. Never returns paths, settings or credentials."""
    result = dict(checkins=[], history=[], status='unavailable', history_status='unavailable')
    source = os.environ.get('HEVY_FATIGUE_DB_PATH')
    if not source:
        return result
    try:
        with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            rows = db.execute('''SELECT date,tiredness,perceived_recovery,sore_quad_dom,sore_posterior,
                sore_upper_push,sore_upper_pull,joint_upper,joint_lower FROM daily_readiness
                WHERE date>=? AND date<=? ORDER BY date''',
                ((day-timedelta(days=CHECKIN_DAYS-1)).isoformat(), day.isoformat())).fetchall()
            result['checkins'] = [dict(r) for r in rows]
            result['status'] = 'available'
            if exercise_id and cutoff:
                result['history'] = [dict(r) for r in db.execute('''SELECT l.workout_id AS hevy_workout_id,
                    s.start_time AS workout_start,s.workout_date,l.set_number,l.weight_lbs,l.reps,l.rpe,
                    l.exercise_id AS exercise_template_id FROM workout_logs l JOIN workout_sessions s
                    ON l.workout_id=s.hevy_workout_id WHERE l.exercise_id=? AND s.workout_date>=?
                    AND s.workout_date<=? ORDER BY s.start_time,l.id''',
                    (exercise_id,(cutoff.date()-timedelta(days=HISTORY_DAYS)).isoformat(),cutoff.date().isoformat()))]
                result['history_status']='available'
    except (sqlite3.Error, OSError, ValueError):
        pass
    return result


def history(conn, data, host, cutoff):
    """Merge by workout identity, preferring exact local sets. No seven-row cap."""
    grouped = {}
    for row in host['history']:
        at = stamp(row.get('workout_start'))
        if at is None:  # Unknown same-day timing cannot establish pre-session history.
            if str(row.get('workout_date')) >= cutoff.date().isoformat():
                continue
            at = stamp(str(row.get('workout_date'))+'T00:00:00Z')
        if at is None or not cutoff-timedelta(days=HISTORY_DAYS) <= at < cutoff:
            continue
        r = dict(row, weight_kg=row['weight_lbs']/2.20462262185 if row.get('weight_lbs') is not None else None,
                 target_rpe=None, set_type='normal', is_ts=0)
        grouped.setdefault(row['hevy_workout_id'],dict(at=at,source='hevy_import',sets=[]))['sets'].append(r)
    local = {}
    for r in conn.execute('SELECT * FROM logged_sets WHERE exercise_template_id=? ORDER BY workout_start,id', (data.exercise_template_id,)):
        r = dict(r)
        at = stamp(r['workout_start'])
        if at and cutoff-timedelta(days=HISTORY_DAYS) <= at < cutoff and r['set_type'] != 'warmup':
            key = r['hevy_workout_id'] or r['workout_start']
            local.setdefault(key,dict(at=at,source='local_exact',sets=[]))['sets'].append(r)
    grouped.update(local)
    target = next((s for s in data.sets if s.ts),data.sets[0])
    samples = []
    ts_rows = [dict(r) for r in conn.execute('SELECT * FROM training_max_history WHERE exercise_template_id=? ORDER BY id', (data.exercise_template_id,))]
    for workout_id, item in sorted(grouped.items(),key=lambda pair:pair[1]['at']):
        sets = item['sets']
        if not sets or item['at'] < cutoff-timedelta(days=STALE_DAYS):
            continue
        recorded = conn.execute('SELECT actual FROM session_reviews WHERE hevy_workout_id=?',(workout_id,)).fetchone()
        if recorded:
            movements = [ex for ex in json.loads(recorded['actual']) if ex['exercise_template_id']==data.exercise_template_id]
            if len(movements) != 1:  # Repeated movements cannot be pooled as one comparable exposure.
                continue
            if len(movements[0]['sets'])==len(sets):
                sets = [{**s,'source':(raw.get('review') or {}).get('rpe_source','unknown')}
                        for s,raw in zip(sets,movements[0]['sets'])]
        rep = next((s for s in sets if s.get('is_ts')),None) if target.ts else sets[0]
        if rep is None or rep.get('reps') != target.reps:
            continue
        errors = [s['rpe']-s['target_rpe'] for s in sets if s.get('rpe') is not None and s.get('target_rpe') is not None
                  and s.get('source') != 'copied_target']
        capacity, kind = None, None
        if data.automatic_weights and item['source']=='local_exact' and rep.get('rpe') == target.rpe and rep.get('source') != 'copied_target':
            marked = next((s for s in reversed(ts_rows) if stamp(s['set_at'])==item['at'] and s['reps']==target.reps and s['rpe']==target.rpe),None)
            if target.ts and marked:
                capacity, kind = marked['e1rm_lb'], 'stored_top_set_e1rm'
            elif not target.ts and rep.get('weight_kg') is not None:
                capacity, kind = rep['weight_kg'], 'load_at_same_reps_and_rpe'
        samples.append(dict(workout_id=workout_id,at=item['at'].isoformat(),source=item['source'],
            sets=len(sets),rpe_error=max(errors) if errors else None,
            confirmed_effort=rep.get('source')=='entered',
            actual_rpe=rep.get('rpe'),capacity=capacity,capacity_kind=kind))
    return len(grouped), samples


def recommend(data, context, total, samples, feedback):
    today = next((r for r in context['checkins'] if str(r['date'])==data.local_date.isoformat()),None)
    def rating(key):
        v = today.get(key) if today else None
        return v if isinstance(v,int) and 0 <= v <= 4 else None
    tired, recovery = rating('tiredness'), rating('perceived_recovery')
    n = len(data.sets)
    recent = samples[-MIN_TREND:]
    reasons = [f'{total} known recorded workout(s) in the {HISTORY_DAYS}-day lookback; {len(samples)} recent rep-matched exposure(s).']
    if context.get('history_status')!='available':
        reasons.append('Imported history is unavailable; any local exact history is still included. This is not proof that older training is absent.')
    limits = ['Provisional product rules, not validated personal recovery thresholds.',
              'Accepting records intent only. Edit the workout yourself; your program is never changed.',
              'Matching a later dose does not prove advice was followed or caused an improvement.']
    if tired is None or recovery is None:
        reasons.append('Today’s tiredness/recovery check-in is missing or incomplete; missing ratings are not zero.')
    else:
        reasons.append(f'Today’s tiredness {tired}/4; poor recovery {recovery}/4 (higher is worse).')
    trend = recent if len(recent)==MIN_TREND and all(s['capacity'] and s['capacity_kind']==recent[0]['capacity_kind'] for s in recent) else []
    declining = bool(trend and trend[-1]['capacity'] <= trend[0]['capacity']*(1-CAPACITY_CHANGE_PCT/100)
                     and all(a['capacity']>b['capacity'] for a,b in zip(trend,trend[1:])))
    overshoot = len(samples)>=MIN_REPEAT and all(s['rpe_error'] is not None and s['rpe_error']>=RPE_OVERSHOOT for s in samples[-MIN_REPEAT:])
    poor = any(v is not None and v>=HIGH_RATING for v in (tired,recovery))
    good = tired is not None and recovery is not None and max(tired,recovery)<=LOW_RATING
    proposed = dict(working_sets=n,reps=None,target_rpe=None)
    action, message = 'hold', 'Keep the written session as the starting point; adjust by your usual judgement.'
    joint_flag = any(v is not None and v>=HIGH_RATING for v in (rating('joint_upper'),rating('joint_lower')))
    if data.pain or joint_flag:
        action, message = 'review', 'A pain or high joint-discomfort flag is recorded. Review the movement before deciding its workload; no increase is suggested.'
    elif poor or declining or overshoot:
        if poor: reasons.append('A current check-in rating meets the provisional high-fatigue threshold.')
        if declining: reasons.append(f'{MIN_TREND} matched exposures show successively lower recorded capacity (at least {CAPACITY_CHANGE_PCT:g}% overall).')
        if overshoot: reasons.append(f'The latest {MIN_REPEAT} comparable sessions recorded effort at least {RPE_OVERSHOOT:g} RPE above their saved targets.')
        if n>1:
            action = 'reduce_set'
            message = ('Consider one fewer back-off set today, retaining the top set and intended effort.' if any(s.ts for s in data.sets)
                       else 'Consider one fewer working set today, keeping the intended reps and effort.')
            proposed['working_sets']=n-1
        else:
            action, message = 'review', 'Review the single working set’s rep/effort target rather than automatically adding work.'
    elif (good and len(recent)==MIN_TREND and n<MAX_INCREASE_SETS and
          all(s['sets']==n and s['rpe_error'] is not None and s['rpe_error']<=0 and s['confirmed_effort'] for s in recent)):
        action, message = 'optional_set', 'If more work fits your goal, consider one additional working set (a back-off if you use a top set).'
        proposed['working_sets']=n+1
        reasons.append(f'{MIN_TREND} comparable sessions sustained the same set count without recorded effort overshooting the saved targets.')
    else:
        reasons.append('No supported reason for a specific volume change was identified from the available inputs.')
    suppressed = any(d['action']=='dismiss' and d['recommendation_action']==action for d in feedback)
    if suppressed:
        reasons.append('You recently dismissed a similar suggestion; it is collapsed until you choose to review it.')
    return dict(model_version=VERSION,title=data.title,action=action,message=message,proposed=proposed,
        confidence='tentative',reasons=reasons,limitations=limits,suppressed=suppressed,
        evidence=dict(checkins=context['checkins'],checkin_status=context['status'],history_workouts=total,
                      imported_history_status=context.get('history_status','unavailable'),
                      comparable_exposures=len(samples),recent_exposures=samples[-6:],feedback=feedback,
                      history_cutoff=data.workout_start.isoformat(),timing='daily ratings are date-only; evidence captured at request time'))


def view(conn, row):
    result = json.loads(row['snapshot'])
    decision = conn.execute('SELECT record FROM advisory_decisions WHERE recommendation_id=? ORDER BY sequence DESC LIMIT 1',(row['id'],)).fetchone()
    return dict(result,id=row['id'],decision=json.loads(decision['record']) if decision else None)


def create(data, *, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = stamp(data.workout_start)
    with closing(get_db()) as conn:
        existing=conn.execute('SELECT * FROM session_advisories WHERE session_id=? AND exercise_id=?',(str(data.session_id),data.exercise_id)).fetchone()
        if existing:
            return view(conn,existing)
    if data.started or cutoff is None or cutoff>now or now-cutoff>timedelta(days=1) or abs((data.local_date-now.date()).days)>1:
        raise AdviceError('New advice is available only before this movement starts in a current workout.',422)
    host=host_context(data.local_date,data.exercise_template_id,cutoff)
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM workout_saves WHERE client_workout_id=?',(str(data.session_id),)).fetchone():
            raise AdviceError('This workout already has a frozen save attempt.')
        existing=conn.execute('SELECT * FROM session_advisories WHERE session_id=? AND exercise_id=?',(str(data.session_id),data.exercise_id)).fetchone()
        if existing:return view(conn,existing)
        total,samples=history(conn,data,host,cutoff)
        feedback=[]
        for r in conn.execute('''SELECT a.id,a.snapshot,d.record,d.recorded_at FROM advisory_decisions d JOIN session_advisories a
            ON a.id=d.recommendation_id WHERE a.exercise_template_id=? AND d.recorded_at>=? AND d.recorded_at<=?
            AND d.sequence=(SELECT MAX(x.sequence) FROM advisory_decisions x WHERE x.recommendation_id=a.id)''',
            (data.exercise_template_id,(now-timedelta(days=DISMISS_DAYS)).isoformat(),now.isoformat())):
            decision=json.loads(r['record'])
            observed=conn.execute('SELECT outcome FROM advisory_outcomes WHERE recommendation_id=?',(r['id'],)).fetchone()
            observed=json.loads(observed['outcome']) if observed else None
            linked=bool(observed and observed.get('decision') and observed['decision']['id']==decision['id'])
            feedback.append(dict(action=decision['action'],reason=decision['reason'],recommendation_action=json.loads(r['snapshot'])['action'],
                saved_working_sets=observed['actual']['working_sets'] if observed else None,
                outcome_linked_to_this_decision=linked,
                matched_intended_sets=observed['matched_intended_sets'] if linked else None))
        snapshot=recommend(data,host,total,samples,feedback)
        snapshot['evidence']['captured_at']=now.isoformat()
        identifier=str(uuid4())
        conn.execute('INSERT INTO session_advisories (id,session_id,exercise_id,exercise_template_id,workout_start,local_date,created_at,request,snapshot) VALUES (?,?,?,?,?,?,?,?,?)',
            (identifier,str(data.session_id),data.exercise_id,data.exercise_template_id,cutoff.isoformat(),data.local_date.isoformat(),now.isoformat(),
             json.dumps(data.model_dump(mode='json')),json.dumps(snapshot,allow_nan=False)))
        return view(conn,conn.execute('SELECT * FROM session_advisories WHERE id=?',(identifier,)).fetchone())


def decide(identifier, data, *, now=None):
    now=now or datetime.now(timezone.utc)
    encoded=json.dumps(data.model_dump(mode='json'),sort_keys=True)
    with closing(get_db()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM session_advisories WHERE id=?',(str(identifier),)).fetchone()
        if not row:raise AdviceError('Recommendation not found.',404)
        existing=conn.execute('SELECT request,recommendation_id FROM advisory_decisions WHERE id=?',(str(data.id),)).fetchone()
        if existing:
            if existing['request']!=encoded or existing['recommendation_id']!=str(identifier):
                raise AdviceError('Decision identity belongs to another request.')
            return view(conn,row)
        if conn.execute('SELECT 1 FROM workout_saves WHERE client_workout_id=?',(row['session_id'],)).fetchone():
            raise AdviceError('Decisions are frozen once saving begins. The saved outcome remains separate.')
        latest=conn.execute('SELECT id FROM advisory_decisions WHERE recommendation_id=? ORDER BY sequence DESC LIMIT 1',(str(identifier),)).fetchone()
        if (latest['id'] if latest else None)!=(str(data.expected_decision_id) if data.expected_decision_id else None):
            raise AdviceError('The decision changed elsewhere. Reload the recommendation before deciding again.')
        snapshot=json.loads(row['snapshot'])
        if data.action in ('accept','modify') and now-stamp(row['workout_start'])>timedelta(days=1):
            raise AdviceError('This advice is stale. Log the workout normally; do not treat it as current guidance.')
        dose=data.modification.model_dump() if data.action=='modify' else snapshot['proposed'] if data.action=='accept' else None
        record=dict(id=str(data.id),action=data.action,dose=dose,reason=data.reason,recorded_at=now.isoformat())
        conn.execute('INSERT INTO advisory_decisions (id,recommendation_id,recorded_at,request,record) VALUES (?,?,?,?,?)',
            (str(data.id),str(identifier),now.isoformat(),encoded,json.dumps(record)))
        return view(conn,row)


def validate_links(conn, links, client_id, workout_start):
    seen=set()
    for link in links or []:
        identifier=str(link.recommendation_id)
        row=conn.execute('SELECT * FROM session_advisories WHERE id=?',(identifier,)).fetchone()
        if identifier in seen or not row or row['session_id']!=str(client_id) or stamp(row['workout_start'])!=stamp(workout_start):
            raise AdviceError('Recommendation does not belong to this workout identity.',422)
        seen.add(identifier)
        if link.decision_id and not conn.execute('SELECT 1 FROM advisory_decisions WHERE id=? AND recommendation_id=?',(str(link.decision_id),identifier)).fetchone():
            raise AdviceError('Decision does not belong to the linked recommendation.',422)


def record_outcomes(payload, workout_id, conn):
    for link in payload.get('advisory_links') or []:
        row=conn.execute('SELECT * FROM session_advisories WHERE id=?',(link['recommendation_id'],)).fetchone()
        candidates=[ex for ex in payload['exercises'] if ex['exercise_template_id']==row['exercise_template_id']]
        exact=[ex for ex in candidates if any((s.get('review') or {}).get('exercise_id')==row['exercise_id'] for s in ex['sets'])]
        identity='exact'
        if exact:
            sets=[s for ex in exact for s in ex['sets'] if s['type']!='warmup']
        elif len(candidates)==1 and not any(s.get('review') for s in candidates[0]['sets']):
            sets=[s for s in candidates[0]['sets'] if s['type']!='warmup'];identity='template_only'
        elif len(candidates)>1 and any(not s.get('review') for ex in candidates for s in ex['sets']):
            sets=None;identity='ambiguous'
        else:
            sets=[]
        decision=conn.execute('SELECT record FROM advisory_decisions WHERE id=?',(link['decision_id'],)).fetchone() if link.get('decision_id') else None
        decision=json.loads(decision['record']) if decision else None
        intended=decision['dose'] if decision else None
        outcome=dict(recommendation_id=row['id'],title=json.loads(row['snapshot'])['title'],decision=decision,intended=intended,
            actual=dict(working_sets=len(sets) if sets is not None else None,
                        total_reps=sum(s['reps'] for s in sets) if sets is not None and all(s.get('reps') is not None for s in sets) else None,
                        sets=sets,performed=bool(sets) if sets is not None else None,identity=identity,
                        suggestion_after_recorded_set=any(stamp((s.get('review') or {}).get('completed_at')) and
                            stamp((s.get('review') or {})['completed_at'])<stamp(row['created_at']) for s in sets or []),
                        decision_after_recorded_set=bool(decision and any(stamp((s.get('review') or {}).get('completed_at')) and
                            stamp((s.get('review') or {})['completed_at'])<stamp(decision['recorded_at']) for s in sets or []))),
            matched_intended_sets=len(sets)==intended['working_sets'] if intended and sets is not None else None,
            matched_intended_reps=all(s['reps']==intended['reps'] for s in sets) if intended and intended.get('reps') is not None and sets and all(s.get('reps') is not None for s in sets) else None,
            matched_intended_rpe=all(s['rpe']==intended['target_rpe'] for s in sets) if intended and intended.get('target_rpe') is not None and sets and all((s.get('review') or {}).get('rpe_source')=='entered' and s.get('rpe') is not None for s in sets) else None)
        conn.execute('INSERT INTO advisory_outcomes (recommendation_id,hevy_workout_id,local_date,outcome) VALUES (?,?,?,?)',
            (row['id'],workout_id,row['local_date'],json.dumps(outcome,allow_nan=False)))


def outcomes(workout_id):
    with closing(get_db()) as conn:
        rows=conn.execute('SELECT local_date,outcome FROM advisory_outcomes WHERE hevy_workout_id=? ORDER BY recommendation_id',(workout_id,)).fetchall()
    result=[]
    for row in rows:
        outcome=json.loads(row['outcome'])
        day=date.fromisoformat(row['local_date'])
        window_end=min(date.today(),day+timedelta(days=CHECKIN_DAYS-1))
        next_rows=host_context(window_end)['checkins'] if window_end>day else []
        outcome['next_checkin']=next((r for r in next_rows if str(r['date'])>day.isoformat()),None)
        result.append(outcome)
    return result
