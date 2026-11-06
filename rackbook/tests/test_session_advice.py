"""Provisional rules, read-only host bridge and decision provenance; disposable data only."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from rackbook import main, session_advice as advice
from rackbook.database import get_db

NOW=datetime(2026,11,5,15,tzinfo=timezone.utc)


class AdviceCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.host=Path(self.tmp.name)/'host.db'
        env=patch.dict(os.environ,RACKBOOK_DB_PATH=str(Path(self.tmp.name)/'logging.db'),HEVY_FATIGUE_DB_PATH=str(self.host))
        env.start();self.addCleanup(env.stop);main.initialize()
        with closing(sqlite3.connect(self.host)) as db, db:
            db.executescript('''CREATE TABLE daily_readiness(date TEXT PRIMARY KEY,tiredness INTEGER,perceived_recovery INTEGER,
                sore_quad_dom INTEGER,sore_posterior INTEGER,sore_upper_push INTEGER,sore_upper_pull INTEGER,joint_upper INTEGER,joint_lower INTEGER);
                CREATE TABLE workout_sessions(hevy_workout_id TEXT,start_time TEXT,workout_date TEXT);
                CREATE TABLE workout_logs(id INTEGER PRIMARY KEY,workout_id TEXT,set_number INTEGER,weight_lbs REAL,reps INTEGER,rpe REAL,exercise_id TEXT);''')
        self.data=advice.AdviceRequest(session_id=uuid4(),exercise_id='movement',exercise_template_id='sq',title='Squat',
            workout_start=NOW-timedelta(minutes=10),local_date=NOW.date(),sets=[dict(reps=5,rpe=6) for _ in range(3)])

    def checkin(self,tiredness,recovery,offset=0,joint=None):
        with closing(sqlite3.connect(self.host)) as db, db:
            db.execute('INSERT OR REPLACE INTO daily_readiness(date,tiredness,perceived_recovery,joint_upper) VALUES (?,?,?,?)',
                ((NOW.date()+timedelta(days=offset)).isoformat(),tiredness,recovery,joint))

    def seed_history(self,count=3,*,rpe=6,target=6,confirmed=False,future=False):
        for i in range(count):
            at=NOW+timedelta(days=1) if future else NOW-timedelta(days=count-i)
            workout_id=f'workout-{i}'
            with closing(get_db()) as db, db:
                for n in range(3):
                    db.execute('''INSERT INTO logged_sets(hevy_workout_id,workout_start,exercise_template_id,
                        exercise_title,set_number,set_type,weight_kg,reps,rpe,target_rpe) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (workout_id,at.isoformat(),'sq','Squat',n+1,'normal',100,5,rpe,target))
                if confirmed:
                    actual=[dict(exercise_template_id='sq',sets=[dict(review=dict(rpe_source='entered')) for _ in range(3)])]
                    db.execute('INSERT INTO session_reviews VALUES (?,?,?,?,?)',(workout_id,at.isoformat(),'{}',json.dumps(actual),'{}'))

    def test_sparse_history_can_offer_a_tentative_checkin_based_reduction(self):
        self.checkin(3,2)
        row=advice.create(self.data,now=NOW)
        self.assertEqual((row['action'],row['proposed']['working_sets'],row['confidence']),('reduce_set',2,'tentative'))
        self.assertEqual(row['evidence']['history_workouts'],0)
        self.assertEqual(row['evidence']['checkins'][0]['tiredness'],3)

    def test_missing_stale_and_future_checkins_are_not_zero_or_today(self):
        self.checkin(0,0,offset=-1);self.checkin(4,4,offset=1)
        row=advice.create(self.data,now=NOW)
        self.assertEqual(row['action'],'hold')
        self.assertEqual(len(row['evidence']['checkins']),1)
        self.assertTrue(any('missing or incomplete' in r for r in row['reasons']))

    def test_history_beyond_seven_is_available_and_future_training_excluded(self):
        self.seed_history(9)
        self.seed_history(1,future=True)
        row=advice.create(self.data,now=NOW)
        self.assertEqual(row['evidence']['history_workouts'],9)
        self.assertEqual(row['evidence']['comparable_exposures'],9)

    def test_host_history_pages_are_not_restricted_to_recent_dashboard_cards(self):
        with closing(sqlite3.connect(self.host)) as db, db:
            for i in range(10):
                at=NOW-timedelta(days=i+1)
                db.execute('INSERT INTO workout_sessions VALUES (?,?,?)',(str(i),at.isoformat(),at.date().isoformat()))
                db.execute('INSERT INTO workout_logs(workout_id,set_number,weight_lbs,reps,rpe,exercise_id) VALUES (?,1,200,5,6,?)',(str(i),'sq'))
        before=self.host.read_bytes()
        row=advice.create(self.data,now=NOW)
        self.assertEqual(row['evidence']['history_workouts'],10)
        self.assertEqual(self.host.read_bytes(),before,'Host bridge must never change monitoring storage')

    def test_optional_increase_requires_confirmed_effort_and_good_checkin(self):
        self.checkin(0,1);self.seed_history(3)
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'hold')
        self.data.session_id=uuid4();self.data.exercise_id='another'
        with closing(get_db()) as db, db:
            for i in range(3):
                actual=[dict(exercise_template_id='sq',sets=[dict(review=dict(rpe_source='entered')) for _ in range(3)])]
                db.execute('INSERT INTO session_reviews VALUES (?,?,?,?,?)',(f'workout-{i}',NOW.isoformat(),'{}',json.dumps(actual),'{}'))
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'optional_set')

    def test_overshoots_can_support_a_suggestion_without_a_complete_daily_rating(self):
        self.seed_history(2,rpe=7)
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'reduce_set')

    def test_pain_and_joint_flags_do_not_generate_increases(self):
        self.checkin(0,0,joint=3);self.seed_history(3,confirmed=True)
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'review')

    def test_snapshot_is_immutable_and_no_new_record_after_started(self):
        self.checkin(3,3)
        first=advice.create(self.data,now=NOW)
        self.checkin(0,0);self.data.started=True
        self.assertEqual(first,advice.create(self.data,now=NOW))
        self.data.session_id=uuid4()
        with self.assertRaises(advice.AdviceError):advice.create(self.data,now=NOW)

    def test_decisions_are_append_only_idempotent_and_concurrency_checked(self):
        row=advice.create(self.data,now=NOW)
        decision=advice.DecisionRequest(id=uuid4(),action='accept')
        first=advice.decide(row['id'],decision,now=NOW)
        self.assertEqual(first,advice.decide(row['id'],decision,now=NOW))
        with self.assertRaises(advice.AdviceError):
            advice.decide(row['id'],advice.DecisionRequest(id=uuid4(),action='dismiss'),now=NOW)
        modified=advice.DecisionRequest(id=uuid4(),action='modify',expected_decision_id=decision.id,
                                       modification=dict(working_sets=2,reps=4),reason='Time available')
        result=advice.decide(row['id'],modified,now=NOW)
        self.assertEqual(result['decision']['dose']['reps'],4)
        with closing(get_db()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM advisory_decisions').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM advisory_outcomes').fetchone()[0],0)
        self.assertEqual(first['message'],result['message'])
        self.data.session_id=uuid4()
        other=advice.create(self.data,now=NOW)
        with self.assertRaises(advice.AdviceError):advice.decide(other['id'],decision,now=NOW)

    def test_dismissal_suppresses_repetition_but_not_now_is_only_this_session(self):
        self.checkin(3,3)
        row=advice.create(self.data,now=NOW)
        advice.decide(row['id'],advice.DecisionRequest(id=uuid4(),action='dismiss',reason='Not useful'),now=NOW)
        self.data.session_id=uuid4()
        later=advice.create(self.data,now=NOW+timedelta(minutes=1))
        self.assertTrue(later['suppressed'])
        self.assertEqual(later['evidence']['feedback'][0]['reason'],'Not useful')
        self.data.exercise_template_id='pullup';self.data.session_id=uuid4()
        other=advice.create(self.data,now=NOW)
        self.assertFalse(other['suppressed'])
        advice.decide(other['id'],advice.DecisionRequest(id=uuid4(),action='not_now'),now=NOW)
        self.data.session_id=uuid4()
        self.assertFalse(advice.create(self.data,now=NOW)['suppressed'])

    def test_manual_sources_do_not_use_added_weight_as_capacity_trends(self):
        self.data.automatic_weights=False
        self.seed_history(3)
        row=advice.create(self.data,now=NOW)
        self.assertTrue(all(s['capacity'] is None for s in row['evidence']['recent_exposures']))

    def test_three_declining_matched_exposures_can_support_early_advice(self):
        self.seed_history(3)
        with closing(get_db()) as db, db:
            for i in range(3):
                db.execute('UPDATE logged_sets SET weight_kg=? WHERE hevy_workout_id=?',(100-5*i,f'workout-{i}'))
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'reduce_set')
        self.data.session_id=uuid4();self.data.automatic_weights=False
        self.assertEqual(advice.create(self.data,now=NOW)['action'],'hold')

    def test_later_daily_checkins_are_separate_from_the_frozen_snapshot(self):
        self.checkin(3,3);row=advice.create(self.data,now=NOW)
        with closing(get_db()) as db, db:
            db.execute('INSERT INTO advisory_outcomes VALUES (?,?,?,?)',(row['id'],'saved',NOW.date().isoformat(),
                json.dumps(dict(recommendation_id=row['id'],title='Squat',decision=None,intended=None,
                    actual=dict(working_sets=2),matched_intended_sets=None))))
        self.checkin(None,2,offset=1);self.checkin(0,0,offset=3)
        class Later(date):
            @classmethod
            def today(cls):return NOW.date()+timedelta(days=2)
        with patch.object(advice,'date',Later):
            observed=advice.outcomes('saved')[0]
        self.assertEqual(observed['next_checkin']['date'],(NOW.date()+timedelta(days=1)).isoformat())
        self.assertIsNone(observed['next_checkin']['tiredness'])
        self.assertEqual(row,advice.create(self.data,now=NOW))

    def test_local_exact_history_takes_precedence_over_imported_duplicates(self):
        self.seed_history(3)
        at=NOW-timedelta(days=3)
        with closing(sqlite3.connect(self.host)) as db, db:
            db.execute('INSERT INTO workout_sessions VALUES (?,?,?)',('workout-0',at.isoformat(),at.date().isoformat()))
            db.execute('INSERT INTO workout_logs(workout_id,set_number,weight_lbs,reps,rpe,exercise_id) VALUES (?,1,999,5,6,?)',('workout-0','sq'))
        row=advice.create(self.data,now=NOW)
        self.assertEqual(row['evidence']['history_workouts'],3)
        self.assertEqual(row['evidence']['recent_exposures'][0]['source'],'local_exact')
        self.assertEqual(row['evidence']['recent_exposures'][0]['capacity'],100)

    def test_modify_requires_a_dose_and_other_decisions_reject_it(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):advice.DecisionRequest(id=uuid4(),action='modify')
        with self.assertRaises(ValidationError):advice.DecisionRequest(id=uuid4(),action='dismiss',modification=dict(working_sets=2))
        self.assertEqual(advice.Dose(working_sets=0).working_sets,0,'A deliberate skipped movement can be recorded as modified intent')
