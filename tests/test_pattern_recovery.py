from datetime import date,timedelta
from unittest import TestCase
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base,DailyReadiness,WorkoutLog,WorkoutSession,ExerciseMapping
import main
from pattern_recovery import build_pattern_history,load_signal

DAY=date(2026,10,30)


def load_history(days=60, target_stress=0):
    start=DAY-timedelta(days=days-1)
    history=[]; atl=ctl=0.
    for i in range(days):
        stress=20 if i in (0,7,14,21,28,35,42) else target_stress if i==days-1 else 0
        atl=.25*stress+.75*atl;ctl=(2/43)*stress+(41/43)*ctl
        values=dict(atl=atl,ctl=ctl,stress=stress)
        history.append(dict(date=(start+timedelta(days=i)).isoformat(),pattern_loads={p:dict(values) for p in ('knee','hip','push','pull')}))
    return history


def checkins(history,rating=0):
    return [dict(date=r['date'],sore_quad_dom=rating,sore_posterior=rating,sore_upper_push=rating,sore_upper_pull=rating) for r in history]


class PatternRecoveryTests(TestCase):
    def test_residual_load_does_not_switch_off_at_balance(self):
        self.assertEqual(load_signal(10,10),.5)
        self.assertEqual(load_signal(5,10),.25)
        self.assertGreater(load_signal(1,10),0)
        self.assertIsNone(load_signal(0,0))

    def test_rest_days_decay_gradually_without_fresh_checkins(self):
        rows=build_pattern_history(load_history(),[])
        values=[r['patterns']['knee']['load_signal'] for r in rows[-10:]]
        self.assertTrue(all(a>b>0 for a,b in zip(values,values[1:])))
        self.assertIsNone(rows[-1]['patterns']['knee']['combined_signal'])
        self.assertTrue(rows[-1]['patterns']['knee']['load_data_sufficient'])

    def test_all_five_soreness_levels_preserve_the_entered_rating(self):
        history=load_history()
        for rating in range(5):
            with self.subTest(rating=rating):
                p=build_pattern_history(history,checkins(history,rating))[-1]['patterns']['knee']
                self.assertEqual(p['soreness_rating'],rating)
                self.assertEqual(p['soreness_dots'],rating+1)
                self.assertEqual(p['soreness_signal'],rating/4)

    def test_soreness_recovery_is_observed_immediately_but_trend_retains_memory(self):
        history=load_history();inputs=checkins(history)
        inputs[-2]['sore_quad_dom']=4
        result=build_pattern_history(history,inputs)
        yesterday=result[-2]['patterns']['knee'];today=result[-1]['patterns']['knee']
        self.assertEqual(yesterday['combined_signal'],1)
        self.assertEqual(today['soreness_signal'],0)
        self.assertGreater(today['combined_signal'],today['load_signal'])
        self.assertAlmostEqual(today['combined_signal'],.65+.35*today['load_signal'],places=3)

    def test_partial_regions_and_long_monitoring_gaps_are_unknown_not_fresh(self):
        history=load_history();inputs=checkins(history)
        partial=[dict(r) for r in inputs];partial[-1]['sore_quad_dom']=None
        row=build_pattern_history(history,partial)[-1]['patterns']
        self.assertIsNone(row['knee']['combined_signal'])
        self.assertIsNone(row['knee']['soreness_dots'])
        self.assertTrue(row['hip']['data_sufficient'])
        inputs=inputs[:-15]+inputs[-2:]
        row=build_pattern_history(history,inputs)[-1]['patterns']['knee']
        self.assertFalse(row['data_sufficient'])
        self.assertIsNone(row['combined_signal'])
        self.assertIsNotNone(row['load_signal'])

    def test_same_day_workout_does_not_leak_into_morning_signal(self):
        base=load_history();extra=load_history(target_stress=200)
        p1=build_pattern_history(base,checkins(base))[-1]['patterns']['knee']
        p2=build_pattern_history(extra,checkins(extra))[-1]['patterns']['knee']
        self.assertEqual(p1,p2)

    def test_training_during_a_monitoring_gap_is_not_treated_as_rest(self):
        engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        with Session(engine) as db:
            db.add(ExerciseMapping(exercise_title='Squat',pct_quad_dom=1.0))
            db.add(DailyReadiness(date=DAY-timedelta(days=40)))
            for i in (35,28,20,5,1):
                day=DAY-timedelta(days=i);key=str(i)
                db.add(WorkoutSession(hevy_workout_id=key,workout_date=day,verification_status='verified',modality='strength'))
                db.add(WorkoutLog(workout_id=key,date=day,exercise_title='Squat',set_number=0,weight_lbs=100,reps=10,rpe=8))
            db.commit()
            class FrozenDate(date):
                @classmethod
                def today(cls): return cls(DAY.year,DAY.month,DAY.day)
            with patch.object(main,'date_type',FrozenDate):
                before=main._compute_training_load(60,db)[0]
                self.assertGreater(before[-2]['stress'],0)
                self.assertGreater(before[-1]['pattern_loads']['knee']['atl'],0)
                db.add(DailyReadiness(date=DAY));db.commit()
                after=main._compute_training_load(60,db)[0]
                self.assertEqual(before,after)
