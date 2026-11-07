"""Frozen daily interpretations in existing host Coach storage; no program writes."""
from datetime import date, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from database import DailyReadiness, CoachingConversation
import coaching


class DailyReviewInput(BaseModel):
    date: date


def observation(db, day):
    entry = db.query(DailyReadiness).filter_by(date=day).first()
    if entry is None:
        raise ValueError('No check-in exists for this date.')
    return dict(date=str(day), **{field:getattr(entry,field) for field in coaching.RATINGS})


def identity(observed, version=coaching.DAILY_RECOMMENDATION_VERSION):
    digest = sha256(coaching.encode(observed).encode()).hexdigest()
    return str(uuid5(NAMESPACE_URL, 'hevy-fatigue:daily-review:'+version+':'+digest))


def current(db, day):
    observed = observation(db, day)
    review_id = identity(observed)
    if db.get(CoachingConversation, review_id):
        return coaching.conversation(db, review_id)
    # Let an existing in-flight review finish or be retried explicitly before
    # starting a recommendation for the same saved ratings.
    legacy_id = identity(observed, 'v1')
    if db.get(CoachingConversation, legacy_id):
        legacy = coaching.conversation(db, legacy_id)
        if any(turn['status'] == 'pending' for turn in legacy['turns']):
            return legacy
    return None


def prepare(db, day, history):
    if day > date.today():
        raise ValueError('Future check-ins cannot receive a daily interpretation.')
    observed = observation(db,day)
    review_id = identity(observed)
    if db.get(CoachingConversation,review_id):
        return coaching.conversation(db,review_id)
    # Daily readiness keeps the existing same-day training cutoff. Current ratings
    # are supplied explicitly; completed training context ends the previous day.
    report = coaching.build_report(db,today=day-timedelta(days=1))
    # Raw monitoring stays in the dashboard API. The AI does not see fixed-rule advice.
    history = [{key: value for key, value in row.items() if not key.startswith('recommendation')}
               for row in history]
    daily = next((r for r in history if r['date']==str(day)),None)
    recent_exercises=[]
    for ex in report['exercises']:
        if ex['days_since_last'] > 28: continue
        recent_exercises.append({k:v for k,v in ex.items() if k!='recent_exposures'})
    evidence=dict(version=coaching.DAILY_RECOMMENDATION_VERSION, captured_at=coaching.now_iso(),
        window=report['window'],coverage=report['coverage'],references=report['references']+[
            dict(id='SAW2016',title='Saw et al.: Monitoring the athlete training response: subjective self-reported measures trump commonly used objective measures: a systematic review',
                 url='https://pmc.ncbi.nlm.nih.gov/articles/PMC4789708/',year=2016,
                 principle='Repeated subjective monitoring can track athlete well-being; individual baselines help interpret changes.',
                 limitation='Does not validate this app score, the 84-day window, percentile range or individual programming decisions.')],
        daily_context=dict(label='Daily check-in · '+str(day),observation=observed,
                           scores=daily, recent_daily_scores=history[-14:],
                           training_cutoff=str(day),training_cutoff_exclusive=True),
        recent_sessions=report['recent_sessions'][-4:],exercises=recent_exercises,
        daily_checkins=report['daily_checkins'][-14:],
        motivation_checkins=report['motivation_checkins'][-6:],
        confirmed_session_checkins=report['confirmed_session_checkins'][-6:],
        saved_plans=report['saved_plans'][:3],
        prior_review_excerpts=[dict(id=r['id'],evidence_date=r['evidence_date'],
            turns=[dict(message=t['message'][:2000],response=t['response'][:2000]) for t in r['turns'][-2:]])
            for r in report['prior_review_excerpts'] if r['evidence_date'][:10]<str(day)][:2],
        limitations=report['limitations']+[
            'Daily context is a brief interpretation, not a six-month programming review. Training ends before the check-in date; no same-day performance is used.',
            'Historical range uses prior eligible smoothed scores, not a validated optimal zone. Being typical does not prove good recovery; low fatigue does not require extra training.',
            'Recent detail: four sessions, exercises seen within 28 days (full-window exposure summaries), 14 prior daily check-ins, six motivation/confirmation records, three saved plans and up to two prior programming reviews with two completed turns each (2000 characters per message). Saved plans are current intent at capture, not historical execution. Prior AI advice is not proof of execution or benefit.',
            'Missing observations remain unknown. A gap in stored training is not proof of poor recovery or of no unrecorded training.'
        ])
    # Bounded context with explicit omissions; always retain current ratings/range.
    for section in ('prior_review_excerpts','saved_plans','recent_sessions','exercises','confirmed_session_checkins','motivation_checkins'):
        while len(coaching.encode(evidence))>36000 and evidence[section]:
            evidence[section].pop()
            note=section+': detail omitted for daily context budget.'
            if note not in evidence['limitations']: evidence['limitations'].append(note)
    if len(coaching.encode(evidence))>36000:
        raise ValueError('Daily context is too large. The check-in remains saved.')
    db.add(CoachingConversation(id=review_id,created_at=evidence['captured_at'],evidence=coaching.encode(evidence)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not db.get(CoachingConversation,review_id): raise
    return coaching.conversation(db,review_id)
