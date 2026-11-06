"""Causal replay and experimental transition rules, independent of live apps."""
from datetime import date, timedelta
import unittest

from tools.replay_recommendations import (RecoveryCandidate, band, metrics,
                                          prior_objective, replay, subjective)


class ReplayTests(unittest.TestCase):
    day = date(2026, 10, 1)

    def test_band_boundaries_match_dashboard(self):
        from main import _combined_recommendation
        for score in (0, 5.99, 6, 6.01, 8, 8.01, 13, 13.01, 14, 14.01, 20):
            with self.subTest(score=score):
                self.assertEqual(band(score),
                    ('large_increase','increase','continue','decrease','large_decrease').index(_combined_recommendation(score)[0]))

    def test_subjective_matches_dashboard_and_rejects_missing(self):
        from database import DailyReadiness
        from main import _subjective_fatigue
        entry=dict(tiredness=3,perceived_recovery=2,sore_quad_dom=1,
                   sore_posterior=2,sore_upper_push=4,sore_upper_pull=0)
        self.assertEqual(subjective(entry),round(_subjective_fatigue(DailyReadiness(**entry))*20,2))
        entry['sore_quad_dom']=None
        self.assertIsNone(subjective(entry))

    def test_current_and_future_workouts_are_excluded(self):
        rows=[dict(date=(self.day-timedelta(days=1)).isoformat(),volume=100)]
        expected=prior_objective(self.day,rows)
        rows += [dict(date=(self.day+timedelta(days=i)).isoformat(),volume=100000) for i in (0,1,30)]
        self.assertEqual(prior_objective(self.day,rows),expected)

    def test_prior_window_includes_seven_days_not_eight(self):
        rows=[dict(date=(self.day-timedelta(days=7)).isoformat(),volume=100),
              dict(date=(self.day-timedelta(days=8)).isoformat(),volume=10000)]
        self.assertEqual(prior_objective(self.day,rows),round(100/(10100/26)*10,2))

    def test_worsening_is_immediate(self):
        for guarded in (False, True):
            candidate=RecoveryCandidate(guarded)
            candidate.update(self.day,2)
            score,state,_=candidate.update(self.day+timedelta(days=1),16)
            self.assertEqual((score,state),(16,4))

    def test_recovery_is_slower_than_raw_signal(self):
        candidate=RecoveryCandidate()
        candidate.update(self.day,16)
        score,state,_=candidate.update(self.day+timedelta(days=1),2)
        self.assertEqual(score,11.1)
        self.assertEqual(state,2)

    def test_guarded_recovery_requires_confirmation_and_one_band(self):
        candidate=RecoveryCandidate(True)
        candidate.update(self.day,16)
        self.assertEqual(candidate.update(self.day+timedelta(days=1),2)[1],4)
        self.assertEqual(candidate.update(self.day+timedelta(days=2),2)[1],3)
        self.assertEqual(candidate.update(self.day+timedelta(days=3),2)[1],3)
        self.assertEqual(candidate.update(self.day+timedelta(days=4),2)[1],2)

    def test_missing_day_is_not_confirmation(self):
        candidate=RecoveryCandidate(True)
        candidate.update(self.day,16)
        candidate.update(self.day+timedelta(days=1),2)
        self.assertEqual(candidate.update(self.day+timedelta(days=2),None),(None,None,False))
        self.assertEqual(candidate.update(self.day+timedelta(days=3),2)[1],4)
        self.assertEqual(candidate.update(self.day+timedelta(days=4),2)[1],3)

    def test_upgrade_buffer_prevents_boundary_chatter(self):
        candidate=RecoveryCandidate(True)
        candidate.update(self.day,6.1)
        for i in range(1,15):
            self.assertEqual(candidate.update(self.day+timedelta(days=i),5.8)[1],1)

    def test_long_gap_starts_new_unconfirmed_segment(self):
        candidate=RecoveryCandidate(True)
        candidate.update(self.day,16)
        self.assertEqual(candidate.update(self.day+timedelta(days=8),2),(2,0,True))

    def test_no_candidate_is_less_conservative_than_current(self):
        for guarded in (False,True):
            candidate=RecoveryCandidate(guarded)
            for i,raw in enumerate((16,2,4,8,7,15,6,2,4,5,2,1,1,1)):
                _,state,_=candidate.update(self.day+timedelta(days=i),raw)
                self.assertGreaterEqual(state,band(raw))

    def test_metrics_do_not_bridge_missing_days(self):
        rows=[dict(current_band=x) for x in (0,None,4,2,4)]
        result=metrics(rows,'current_band')
        self.assertEqual(result['consecutive_pairs'],2)
        self.assertEqual(result['changes'],2)
        self.assertEqual(result['reversals_next_day'],1)

    def test_future_checkins_do_not_change_prior_predictions(self):
        entry=dict(tiredness=2,perceived_recovery=2,sore_quad_dom=2,
                   sore_posterior=2,sore_upper_push=2,sore_upper_pull=2)
        first=dict(entry,date=self.day.isoformat())
        rows=replay([first],[],[])
        future=dict(entry,date=(self.day+timedelta(days=1)).isoformat(),tiredness=4)
        self.assertEqual(rows,replay([first,future],[],[])[:1])

    def test_missing_calendar_days_are_explicit_gaps(self):
        entry=dict(tiredness=2,perceived_recovery=2,sore_quad_dom=2,
                   sore_posterior=2,sore_upper_push=2,sore_upper_pull=2)
        rows=replay([dict(entry,date=self.day.isoformat()),
                     dict(entry,date=(self.day+timedelta(days=2)).isoformat())],[],[])
        self.assertIsNone(rows[1]['guarded_band'])
        self.assertEqual(len(rows),3)


if __name__ == '__main__':
    unittest.main()
