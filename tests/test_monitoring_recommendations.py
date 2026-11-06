"""Monitoring continuity, causal inputs and API agreement on isolated databases."""
from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import main
from database import Base, DailyReadiness, WorkoutLog, WorkoutSession
from recommendations import (FALLBACK_LABEL, RATING_FIELDS, RecommendationState,
                             build_history, objective_load)

DAY = date(2026, 10, 30)


def entry(day, rating=2):
    return dict(date=day, **{k:rating for k in RATING_FIELDS})


def workouts():
    return {DAY-timedelta(days=i):1000. for i in (50, 40, 30, 10, 6, 3)}


class MonitoringTests(TestCase):
    def test_no_data_and_no_today_checkin_use_exact_fallback(self):
        for checkins in ([], [entry(DAY-timedelta(days=1))]):
            row=build_history(checkins,workouts(),DAY)[-1]
            self.assertEqual(row['recommendation_label'],FALLBACK_LABEL)
            self.assertFalse(row['data_sufficient'])
            self.assertIsNone(row['smoothed_score'])

    def test_three_consecutive_complete_checkins_required_at_startup(self):
        start=DAY-timedelta(days=2)
        rows=build_history([entry(start+timedelta(days=i)) for i in range(3)],workouts(),DAY)
        self.assertEqual([r['data_sufficient'] for r in rows],[False,False,True])
        self.assertEqual([r['consecutive_checkins'] for r in rows],[1,2,3])

    def test_high_and_low_scores_both_fall_back_during_reacquisition(self):
        for rating in (0,4):
            with self.subTest(rating=rating):
                checks=[entry(DAY-timedelta(days=i),4) for i in (60,59,58)]
                checks += [entry(DAY-timedelta(days=1),rating),entry(DAY,rating)]
                row=build_history(checks,workouts(),DAY)[-1]
                self.assertEqual(row['recommendation_label'],FALLBACK_LABEL)
                self.assertEqual(row['consecutive_checkins'],2)

    def test_long_gap_keeps_training_and_restarts_monitoring_only(self):
        checks=[entry(DAY-timedelta(days=i),4) for i in (60,59,58)]
        checks += [entry(DAY-timedelta(days=i),0) for i in (2,1,0)]
        rows=build_history(checks,workouts(),DAY)
        self.assertEqual([r['data_sufficient'] for r in rows[-3:]],[False,False,True])
        self.assertEqual(rows[-3]['smoothed_score'],rows[-3]['combined_score'])
        self.assertEqual(rows[-1]['workout_dates'],6)
        self.assertEqual(rows[-1]['baseline_weekly_volume'],6000/26)

    def test_missing_day_breaks_initial_collection(self):
        rows=build_history([entry(DAY-timedelta(days=i)) for i in (3,2,0)],workouts(),DAY)
        self.assertFalse(rows[-1]['data_sufficient'])
        self.assertEqual(rows[-1]['consecutive_checkins'],1)

    def test_short_gap_does_not_reset_established_fatigue(self):
        state=RecommendationState()
        for i in range(3):
            state.update(DAY+timedelta(days=i),16)
        missing=state.update(DAY+timedelta(days=3),None)
        self.assertEqual(missing['recommendation'],'insufficient_data')
        resumed=state.update(DAY+timedelta(days=4),2)
        self.assertTrue(resumed['monitoring_ready'])
        self.assertAlmostEqual(resumed['smoothed_score'],11.1)
        self.assertEqual(resumed['recommendation'],'large_decrease')

    def test_seven_day_gap_retains_state_eight_day_gap_resets(self):
        for gap,ready in ((7,True),(8,False)):
            state=RecommendationState()
            for i in range(3):
                state.update(DAY-timedelta(days=2-i),16)
            result=state.update(DAY+timedelta(days=gap),2)
            self.assertEqual(result['monitoring_ready'],ready)
            self.assertEqual(result['consecutive_checkins'],1)

    def test_partial_checkin_is_missing_not_fresh(self):
        checks=[entry(DAY-timedelta(days=i)) for i in (2,1,0)]
        checks[-1]['tiredness']=None
        row=build_history(checks,workouts(),DAY)[-1]
        self.assertFalse(row['data_sufficient'])
        self.assertIsNone(row['subjective_score'])
        self.assertIsNone(row['combined_score'])

    def test_workout_baseline_gates_and_boundary(self):
        for offsets,sufficient in (((28,20,1),True),((27,20,1),False),((50,1),False), ((),False)):
            with self.subTest(offsets=offsets):
                volumes={DAY-timedelta(days=i):1000 for i in offsets}
                self.assertEqual(objective_load(DAY,volumes)['workout_data_sufficient'],sufficient)
        self.assertFalse(objective_load(DAY,{d:0 for d in workouts()})['workout_data_sufficient'])

    def test_no_baseline_never_issues_directional_advice(self):
        for rating in (0,4):
            row=build_history([entry(DAY-timedelta(days=i),rating) for i in (2,1,0)],{},DAY)[-1]
            self.assertEqual(row['recommendation_label'],FALLBACK_LABEL)
            self.assertIsNone(row['objective_score'])

    def test_future_and_target_day_training_do_not_change_prior_results(self):
        checks=[entry(DAY-timedelta(days=i)) for i in (2,1,0)]
        expected=build_history(checks,workouts(),DAY)
        volumes=workouts() | {DAY:1000000,DAY+timedelta(days=1):1000000}
        self.assertEqual(expected,build_history(checks+[entry(DAY+timedelta(days=1),4)],volumes,DAY))

    def test_immediate_worsening_but_confirmed_single_level_recovery(self):
        state=RecommendationState()
        for i in range(3):
            state.update(DAY+timedelta(days=i),2)
        self.assertEqual(state.update(DAY+timedelta(days=3),16)['recommendation'],'large_decrease')
        self.assertEqual(state.update(DAY+timedelta(days=4),2)['recommendation'],'large_decrease')
        self.assertEqual(state.update(DAY+timedelta(days=5),2)['recommendation'],'decrease')
        self.assertEqual(state.update(DAY+timedelta(days=6),2)['recommendation'],'decrease')
        self.assertEqual(state.update(DAY+timedelta(days=7),2)['recommendation'],'continue')


class RecommendationAPITests(TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for i, (day,volume) in enumerate(workouts().items()):
            key=f'workout-{i}'
            self.db.add(WorkoutSession(hevy_workout_id=key,workout_date=day,modality='strength',verification_status='verified'))
            self.db.add(WorkoutLog(date=day,workout_id=key,exercise_id='squat',exercise_title='Squat',set_number=0,weight_lbs=100,reps=10,rpe=8))
        for offset in range(10):
            self.db.add(DailyReadiness(**entry(DAY-timedelta(days=offset))))
        self.db.commit()
        class FrozenDate(date):
            @classmethod
            def today(cls):
                return cls(DAY.year,DAY.month,DAY.day)
        self.clock=patch.object(main,'date_type',FrozenDate)
        self.clock.start(); self.addCleanup(self.clock.stop)
        main.app.dependency_overrides[main.get_db]=lambda:self.db
        self.addCleanup(main.app.dependency_overrides.clear)
        self.client=TestClient(main.app)  # No context manager: do not run startup/migrations.
        self.addCleanup(self.client.close)

    def get(self,path):
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_dashboard_history_diagnostics_and_log_agree_across_ranges(self):
        today=self.get('/api/training-load?days=7')['today']
        rec=today['recommendation_v2']
        history=self.get('/api/readiness/combined-history?days=7')
        longer=self.get('/api/readiness/combined-history?days=30')
        diagnostic=self.get('/api/diagnostics/snapshot')
        log=self.get('/api/readiness/log')[0]
        self.assertTrue(rec['data_sufficient'])
        self.assertEqual(history,longer[-7:])
        self.assertEqual(rec,diagnostic['recommendation_v2'])
        self.assertEqual(rec['training_state'],history[-1]['recommendation'])
        self.assertEqual(rec['smoothed_score'],history[-1]['smoothed_score'])
        self.assertEqual(rec['combined_score'],diagnostic['combined_score']['combined_score'])
        self.assertEqual(rec['training_state'],log['recommendation_adjusted'])
        self.assertEqual(rec['training_state'],today['recommendation'])
        self.assertEqual(rec['training_state'],self.get('/api/training-load?days=30')['today']['recommendation_v2']['training_state'])

    def test_missing_today_and_long_gap_fallback_through_http(self):
        self.db.query(DailyReadiness).filter(DailyReadiness.date==DAY).delete()
        self.db.commit()
        rec=self.get('/api/training-load')['today']['recommendation_v2']
        self.assertEqual(rec['training_state_label'],FALLBACK_LABEL)
        self.assertIsNone(rec['combined_score'])
        # Continued training is retained, but two new check-ins cannot bridge a monitoring break.
        self.db.query(DailyReadiness).delete()
        for offset in (60,59,58,1,0):
            self.db.add(DailyReadiness(**entry(DAY-timedelta(days=offset),4)))
        self.db.commit()
        rec=self.get('/api/training-load')['today']['recommendation_v2']
        self.assertEqual(rec['training_state_label'],FALLBACK_LABEL)
        self.assertEqual(rec['consecutive_checkins'],2)
        self.assertFalse(rec['data_sufficient'])
        self.assertEqual(self.db.query(WorkoutSession).count(),6)
        self.assertIn('Continue Training as Normal',main._build_ai_system_prompt(self.db))

    def test_cold_database_and_joint_advisory_survive_fallback(self):
        self.db.query(WorkoutLog).delete();self.db.query(WorkoutSession).delete()
        self.db.query(DailyReadiness).filter(DailyReadiness.date==DAY).update({'joint_upper':4})
        self.db.commit()
        rec=self.get('/api/training-load')['today']['recommendation_v2']
        self.assertEqual(rec['training_state_label'],FALLBACK_LABEL)
        self.assertEqual(rec['joint_advisory']['upper']['level'],'warning')
        self.get('/api/diagnostics/snapshot')
        self.db.query(DailyReadiness).delete();self.db.commit()
        self.assertEqual(self.get('/api/training-load')['today']['recommendation_v2']['training_state_label'],FALLBACK_LABEL)
