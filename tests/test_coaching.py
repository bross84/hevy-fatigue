"""Coaching evidence and provider integration on isolated databases; no real API calls."""
from contextlib import closing
from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
import main
from database import Base, DailyReadiness, WorkoutLog, WorkoutSession, CoachingConversation, CoachingTurn
from rackbook import database as logger

DAY = date(2026,11,5)


class CoachingTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'logging.db'
        self.env=patch.dict(os.environ,RACKBOOK_DB_PATH=str(self.path))
        self.env.start()
        logger.init_db()
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        self.db=self.sessions()
        def dependency():
            with self.sessions() as db: yield db
        main.app.dependency_overrides[main.get_db]=dependency
        self.client=TestClient(main.app)
        self.persist=patch.object(main,'SessionLocal',self.sessions)
        self.persist.start()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.persist.stop()
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def imported(self, identity, day, reps=5):
        self.db.add(WorkoutSession(hevy_workout_id=identity,workout_date=day,workout_title='Strength'))
        self.db.add(WorkoutLog(workout_id=identity,date=day,exercise_id='sq',exercise_title='Squat',
                               set_number=1,weight_lbs=220.462262185,reps=reps,rpe=7))
        self.db.commit()

    def exact(self, identity, day, *, reps=5, rpe=7, kg=100, basis='e1rm', source='entered'):
        at=str(day)+'T12:00:00Z'
        raw=dict(exercise_template_id='sq',sets=[dict(review=dict(basis=basis,rpe_source=source))])
        with logger.get_db() as conn:
            conn.execute('INSERT INTO logged_sets (hevy_workout_id,workout_start,exercise_template_id,exercise_title,set_number,set_type,weight_kg,reps,rpe,is_ts,target_rpe) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (identity,at,'sq','Squat',1,'normal',kg,reps,rpe,1,6))
            conn.execute('INSERT INTO session_reviews VALUES (?,?,?,?,?)',(identity,at,json.dumps(dict(source='plan')),json.dumps([raw]),json.dumps(dict(title='Local session'))))

    def test_all_history_deduplicated_local_precedence_and_sparse_monitoring(self):
        for i in range(12): self.imported(str(i),DAY-timedelta(days=i*10))
        self.exact('0',DAY,kg=102.5)
        self.db.add(DailyReadiness(date=DAY,tiredness=0,perceived_recovery=None))
        self.db.commit()
        before=self.path.read_bytes()
        report=coaching.build_report(self.db,today=DAY)
        self.assertEqual(report['coverage']['sessions'],12)
        self.assertEqual(report['coverage']['training_span_days'],110)
        self.assertEqual(report['coverage']['complete_daily_checkins'],0)
        self.assertEqual(report['coverage']['missing_checkin_dates'],report['window']['calendar_days']-1)
        ex=report['exercises'][0]
        self.assertEqual(ex['exposure_count'],12)
        self.assertEqual(ex['median_interval_days'],10)
        self.assertEqual(ex['known_working_sets'],1)
        self.assertEqual(ex['unknown_role_sets'],11)
        self.assertEqual(ex['recent_exposures'][-1]['sets'][0]['weight_kg'],102.5)
        self.assertEqual(ex['recent_exposures'][-1]['sets'][0]['target_rpe'],6)
        self.assertEqual(ex['entered_target_comparisons']['mean_rpe_error'],1)
        self.assertEqual(report['recent_sessions'][-2]['sets'][0]['target_rpe'],None)
        self.assertEqual(report['coverage']['local_source'],'available')
        self.assertEqual(self.path.read_bytes(),before)

    def test_comparisons_require_same_reps_effort_role_and_known_basis(self):
        for i,opts in enumerate([{},dict(kg=105),dict(reps=3),dict(rpe=8),dict(basis='manual'),dict(source='copied_target')]):
            self.exact(str(i),DAY-timedelta(days=20-i*3),**opts)
        ex=coaching.build_report(self.db,today=DAY)['exercises'][0]
        self.assertEqual(ex['exposure_count'],6)
        self.assertEqual(len(ex['matched_load_comparisons']),1)
        self.assertEqual(ex['matched_load_comparisons'][0]['load_change_pct'],5)
        self.assertEqual(ex['matched_load_comparisons'][0]['exposures'],2)
        self.assertEqual(ex['sets_by_reps'],{'5':5,'3':1})
        self.assertNotIn('e1rm',ex)

    def test_window_and_missing_logger_do_not_create_database(self):
        self.imported('old',DAY-timedelta(days=200))
        self.imported('future',DAY+timedelta(days=1))
        absent=Path(self.temp.name)/'absent.db'
        with patch.dict(os.environ,RACKBOOK_DB_PATH=str(absent)):
            report=coaching.build_report(self.db,today=DAY)
        self.assertEqual(report['coverage']['sessions'],0)
        self.assertEqual(report['coverage']['local_source'],'unavailable_or_incomplete')
        self.assertFalse(absent.exists())

    def test_plan_pretraining_and_feedback_are_context_not_writes(self):
        with logger.get_db() as conn:
            conn.execute('INSERT INTO mesocycles(id,document,active) VALUES (?,?,1)',('plan',json.dumps(dict(name='My program',notes='Goal: strength',weeks=[]))))
            conn.execute('INSERT INTO session_soreness(hevy_workout_id,workout_start,squat,squat_pain) VALUES (?,?,?,?)',('w',str(DAY),0,0))
        report=coaching.build_report(self.db,today=DAY)
        self.assertEqual(report['saved_plans'][0]['document']['notes'],'Goal: strength')
        self.assertEqual(report['pretraining_checkins'][0]['squat'],0)
        self.assertEqual(len(report['references']),3)
        self.assertTrue(all(r['url'].endswith('/') and 'pubmed.ncbi.nlm.nih.gov/' in r['url'] for r in report['references']))

    def create(self):
        identity=str(uuid4())
        with patch.object(coaching,'build_report',return_value=dict(captured_at=coaching.now_iso(),version=coaching.VERSION,references=coaching.REFERENCES)):
            result=self.client.post('/api/ai/conversations',json=dict(id=identity))
        self.assertEqual(result.status_code,200,result.text)
        return identity,result.json()

    def provider(self, chunks):
        client=MagicMock()
        response=client.send.return_value
        response.status_code=200
        response.iter_text.return_value=iter(chunks)
        return patch.object(main.httpx,'Client',return_value=client),client

    def send(self, identity, seq=0, turn=None, message='Review my training'):
        return self.client.post('/api/ai/conversations/'+identity+'/messages',json=dict(id=turn or str(uuid4()),message=message,model='test/model',expected_sequence=seq))

    def test_stream_and_followup_persist_with_frozen_evidence_and_selected_model(self):
        identity,view=self.create()
        provider,remote=self.provider(['data: {"choices":[{"delta":{"content":"Keep the current plan."}}]}\n\ndata: [DONE]\n\n'])
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),provider:
            result=self.send(identity)
        self.assertEqual(result.status_code,200)
        self.assertIn('[DONE]',result.text)
        saved=self.client.get('/api/ai/conversations/'+identity).json()
        self.assertEqual(saved['turns'][0]['status'],'complete')
        self.assertEqual(saved['turns'][0]['response'],'Keep the current plan.')
        self.assertEqual(saved['evidence'],view['evidence'])
        req=remote.build_request.call_args.kwargs['json']
        self.assertEqual(req['model'],'test/model')
        self.assertIn('AI-assisted program creation',req['messages'][0]['content'])
        provider,remote=self.provider(['data: {"choices":[{"delta":{"content":"Let us discuss the goal."}}]}\n\ndata: [DONE]\n\n'])
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),provider:
            self.assertEqual(self.send(identity,1,message='Could we change phases?').status_code,200)
        req=remote.build_request.call_args.kwargs['json']
        self.assertEqual(req['messages'][2]['content'],'Keep the current plan.')
        self.assertEqual(len(self.client.get('/api/ai/conversations/'+identity).json()['turns']),2)
        self.assertEqual(self.client.get('/api/ai/conversations').json()[0]['id'],identity)

    def test_idempotent_snapshot_and_prior_review_excerpts(self):
        identity,view=self.create()
        with patch.object(coaching,'build_report',side_effect=AssertionError('must not recapture')):
            repeated=self.client.post('/api/ai/conversations',json=dict(id=identity))
        self.assertEqual(repeated.json()['evidence'],view['evidence'])
        self.db.add(CoachingTurn(id=str(uuid4()),conversation_id=identity,sequence=1,message='Goal: strength',response='Proposed next phase',status='complete',model='test/model',created_at=coaching.now_iso()))
        self.db.commit()
        report=coaching.build_report(self.db,today=DAY)
        self.assertEqual(report['prior_review_excerpts'][0]['turns'][0]['message'],'Goal: strength')

    def test_failed_and_interrupted_responses_are_durable_and_not_reposted(self):
        identity,_=self.create()
        provider,remote=self.provider(['data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n'])
        turn=str(uuid4())
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),provider:
            result=self.send(identity,turn=turn)
            repeated=self.send(identity,turn=turn)
        self.assertIn('interrupted',result.text)
        self.assertEqual(repeated.status_code,409)
        self.assertEqual(remote.send.call_count,1)
        saved=self.client.get('/api/ai/conversations/'+identity).json()
        self.assertEqual(saved['turns'][0]['response'],'Partial')
        self.assertEqual(saved['turns'][0]['status'],'interrupted')
        self.assertEqual(self.client.get('/training/log').status_code,200)

    def test_missing_key_pending_and_stale_conversation_are_explicit(self):
        identity,_=self.create()
        with patch.object(main,'_get_ai_api_key',return_value=None):
            self.assertEqual(self.send(identity).status_code,422)
        self.assertEqual(self.client.get('/api/ai/conversations/'+identity).json()['turns'],[])
        self.db.add(CoachingTurn(id=str(uuid4()),conversation_id=identity,sequence=1,message='test',response=None,status='pending',model='test/model',created_at=coaching.now_iso()))
        self.db.commit()
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),patch.object(main,'_stream_openrouter') as remote:
            self.assertEqual(self.send(identity,1).status_code,409)
            remote.assert_not_called()

    def test_provider_setup_failure_recorded_without_program_changes(self):
        identity,_=self.create()
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),patch.object(main,'_stream_openrouter',side_effect=main.HTTPException(502,'Provider unavailable')):
            self.assertEqual(self.send(identity).status_code,502)
        saved=self.client.get('/api/ai/conversations/'+identity).json()
        self.assertEqual(saved['turns'][0]['status'],'failed')
        with logger.get_db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM logged_sets').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM mesocycles').fetchone()[0],0)

    def test_stale_sequence_rejected_and_partial_response_labelled_in_context(self):
        identity,_=self.create()
        self.db.add(CoachingTurn(id=str(uuid4()),conversation_id=identity,sequence=1,message='First',response='Incomplete claim',status='interrupted',model='test/model',created_at=coaching.now_iso()))
        self.db.commit()
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),patch.object(main,'_stream_openrouter') as remote:
            self.assertEqual(self.send(identity,0).status_code,409)
            remote.assert_not_called()
        view=self.client.get('/api/ai/conversations/'+identity).json()
        self.assertIn('Recorded partial response',coaching.messages(view,'Next question')[2]['content'])

    def test_context_size_omissions_are_explicit_and_totals_survive(self):
        self.imported('w',DAY)
        with logger.get_db() as conn:
            conn.execute('INSERT INTO mesocycles(id,document,active) VALUES (?,?,1)',('p',json.dumps(dict(notes='x'*5000))))
        baseline=coaching.build_report(self.db,today=DAY)
        with patch.object(coaching,'MAX_CONTEXT_CHARS',len(coaching.encode(baseline))-4000):
            report=coaching.build_report(self.db,today=DAY)
        self.assertEqual(report['coverage']['sessions'],1)
        self.assertEqual(report['exercises'][0]['exposure_count'],1)
        self.assertEqual(report['saved_plans'],[])
        self.assertTrue(any('saved_plans' in note and 'omitted' in note for note in report['limitations']))

    def test_provider_error_event_is_failed_not_complete(self):
        identity,_=self.create()
        provider,_=self.provider(['data: {"error":{"message":"Mock provider failure"}}\n\ndata: [DONE]\n\n'])
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),provider:
            self.assertEqual(self.send(identity).status_code,200)
        saved=self.client.get('/api/ai/conversations/'+identity).json()
        self.assertEqual(saved['turns'][0]['status'],'failed')
