"""Personal ranges and saved daily coaching, using only temporary databases/providers."""
from datetime import date, datetime, timedelta, timezone
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
import daily_coaching
import main
from database import Base, DailyReadiness, WorkoutSession, WorkoutLog, CoachingConversation, CoachingTurn
from rackbook import database as logger
from readiness_context import historical_ranges

DAY=date.today()


class HistoricalRangeTests(TestCase):
    def rows(self, count=40):
        return [dict(date=str(DAY-timedelta(days=count-i-1)),data_sufficient=True,
                     smoothed_score=float(i%5+5),combined_score=float(i%5+4)) for i in range(count)]

    def test_prior_only_percentiles_and_no_score_mutation(self):
        rows=self.rows();before=json.dumps(rows)
        result=historical_ranges(rows)
        expected=sorted(r['smoothed_score'] for r in rows[:-1])
        ref=result[-1]['historical_range']
        self.assertTrue(ref['sufficient']);self.assertEqual(ref['observations'],39)
        self.assertEqual((ref['lower'],ref['upper']),(5,9))
        self.assertEqual(ref['end'],str(DAY-timedelta(days=1)))
        rows[-1]['smoothed_score']=20
        future=dict(date=str(DAY+timedelta(days=1)),data_sufficient=True,smoothed_score=0)
        updated=historical_ranges(rows+[future])
        self.assertEqual(updated[-2]['historical_range'],ref)
        self.assertEqual(updated[-2]['historical_position'],'above_usual')
        self.assertEqual(json.dumps(self.rows()),before)
        self.assertEqual([r['combined_score'] for r in result],[r['combined_score'] for r in self.rows()])

    def test_missing_ineligible_sparse_and_window_expiry(self):
        rows=self.rows(100)
        for i in range(10,90): rows[i]['data_sufficient']=False
        rows[90]['smoothed_score']=None
        result=historical_ranges(rows)
        ref=result[-1]['historical_range']
        self.assertEqual(ref['observations'],8)
        self.assertFalse(ref['sufficient']);self.assertIsNone(ref['lower'])
        self.assertEqual(ref['missing_or_ineligible_days'],76)
        self.assertFalse(historical_ranges(self.rows(20))[-1]['historical_range']['sufficient'])
        sparse=[dict(date=str(DAY-timedelta(days=84-i*6)),data_sufficient=True,smoothed_score=8) for i in range(14)]
        sparse.append(dict(date=str(DAY),data_sufficient=False,smoothed_score=None))
        ref=historical_ranges(sparse)[-1]
        self.assertTrue(ref['historical_range']['sufficient'])
        self.assertEqual(ref['historical_range']['lower'],8)
        self.assertEqual(ref['historical_position'],'unavailable')


class DailyCoachingTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,RACKBOOK_DB_PATH=str(Path(self.temp.name)/'logging.db'));self.env.start()
        logger.init_db()
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.sessions=sessionmaker(bind=self.engine);self.db=self.sessions()
        def dependency():
            with self.sessions() as db: yield db
        main.app.dependency_overrides[main.get_db]=dependency
        self.persist=patch.object(main,'SessionLocal',self.sessions);self.persist.start()
        self.client=TestClient(main.app)
        for offset in range(1,45):
            self.db.add(DailyReadiness(date=DAY-timedelta(days=offset),**{k:offset%3 for k in coaching.RATINGS}))
        for offset in (60,50,40,30,20,10,2,0):
            day=DAY-timedelta(days=offset);key='workout-'+str(offset)
            self.db.add(WorkoutSession(hevy_workout_id=key,workout_date=day,workout_title='Test strength'))
            self.db.add(WorkoutLog(workout_id=key,date=day,exercise_id='pull',exercise_title='Weighted pull-up',set_number=1,weight_lbs=25,reps=5,rpe=7))
        self.db.commit()

    def tearDown(self):
        self.client.close();main.app.dependency_overrides.clear();self.persist.stop()
        self.db.close();self.engine.dispose();self.env.stop();self.temp.cleanup()

    def submit(self):
        ratings={k:0 for k in coaching.RATINGS};ratings['tiredness']=2
        result=self.client.post('/api/readiness',json=dict(date=str(DAY),**ratings))
        self.assertEqual(result.status_code,200,result.text)

    def prepare(self, day=DAY):
        result=self.client.post('/api/ai/daily-reviews',json=dict(date=str(day)))
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def test_save_independent_capture_cutoff_range_and_immutable_revision(self):
        with patch.object(main,'_stream_openrouter',side_effect=AssertionError('Save cannot call AI')):
            self.submit()
        monitoring=main._build_diagnostics_snapshot(self.db)
        before=Path(os.environ['RACKBOOK_DB_PATH']).read_bytes()
        view=self.prepare();context=view['evidence']['daily_context']
        self.assertEqual(context['observation']['tiredness'],2)
        self.assertEqual(context['observation']['perceived_recovery'],0)
        self.assertTrue(context['scores']['historical_range']['sufficient'])
        self.assertEqual(view['evidence']['coverage']['sessions'],7)
        self.assertTrue(all(s['date']<str(DAY) for s in view['evidence']['recent_sessions']))
        self.assertNotIn('workout-0',json.dumps(view['evidence']))
        self.assertEqual(self.prepare(),view)
        self.assertEqual(main._build_diagnostics_snapshot(self.db),monitoring)
        self.assertEqual(Path(os.environ['RACKBOOK_DB_PATH']).read_bytes(),before)
        self.assertEqual(self.client.get('/api/ai/daily-reviews/'+str(DAY)).json(),view)
        self.client.put('/api/readiness/'+str(DAY),json={k:1 for k in coaching.RATINGS})
        self.assertIsNone(self.client.get('/api/ai/daily-reviews/'+str(DAY)).json())
        revised=self.prepare();self.assertNotEqual(view['id'],revised['id'])
        self.assertEqual(self.client.get('/api/ai/conversations/'+view['id']).json()['evidence'],view['evidence'])
        self.assertIn('Daily check-in',self.client.get('/api/ai/conversations').json()[0]['label'])
        self.client.delete('/api/readiness/'+str(DAY))
        self.assertIsNone(self.client.get('/api/ai/daily-reviews/'+str(DAY)).json())
        self.assertEqual(self.client.get('/api/ai/conversations/'+view['id']).status_code,200)

    def test_raw_scores_and_ranges_agree_across_chart_windows(self):
        self.submit()
        short=self.client.get('/api/readiness/combined-history?days=7').json()
        long=self.client.get('/api/readiness/combined-history?days=90').json()
        self.assertEqual(short,long[-7:])
        raw=main._recommendation_history(self.db,DAY)[-1]
        for key,value in raw.items():self.assertEqual(short[-1][key],value,key)
        view=self.prepare()
        self.assertEqual(view['evidence']['daily_context']['scores'],
                         {k:v for k,v in short[-1].items() if not k.startswith('recommendation')})
        self.assertTrue(all(not any(k.startswith('recommendation') for k in row)
                            for row in view['evidence']['daily_context']['recent_daily_scores']))

    def test_mocked_interpretation_and_followup_persist_with_exact_context(self):
        self.submit();view=self.prepare()
        remote=MagicMock();response=remote.send.return_value;response.status_code=200
        def send(seq,message):
            content = (json.dumps(dict(action='continue', reason='Recent effort is steady.')) if seq == 0
                       else 'Watch how your working sets feel.')
            event = json.dumps(dict(choices=[dict(delta=dict(content=content))]))
            response.iter_text.return_value=iter(['data: '+event+'\n\ndata: [DONE]\n\n'])
            return self.client.post('/api/ai/conversations/'+view['id']+'/messages',json=dict(id=str(uuid4()),message=message,model='test/value-model',expected_sequence=seq))
        with patch.object(main,'_get_ai_api_key',return_value='mock-only'),patch.object(main.httpx,'Client',return_value=remote):
            self.assertEqual(send(0,'Interpret today').status_code,200)
            supplied=json.loads(remote.build_request.call_args.kwargs['json']['messages'][0]['content'].split('FROZEN TRAINING REPORT:\n')[1])
            self.assertEqual(supplied,view['evidence'])
            self.assertIn('SAW2016',{r['id'] for r in supplied['references']})
            self.assertEqual(send(0,'Accidental duplicate').status_code,409)
            self.assertEqual(send(1,'What should I watch during training?').status_code,200)
        saved=self.client.get('/api/ai/daily-reviews/'+str(DAY)).json()
        self.assertEqual(len(saved['turns']),2);self.assertEqual(saved['turns'][0]['status'],'complete')
        self.assertEqual(saved['turns'][0]['model'],'test/value-model')
        self.assertEqual(saved['daily_recommendation'], dict(action='continue', label='Continue as planned',
                                                            reason='Recent effort is steady.'))
        self.assertEqual(saved['turns'][1]['response'], 'Watch how your working sets feel.')
        self.assertEqual(remote.send.call_count,2)
        # Daily snippets must not crowd previous programming discussions out of full reviews.
        self.assertEqual(coaching.build_report(self.db,today=DAY)['prior_review_excerpts'],[])

    def test_retry_stale_pending_reuses_checkin_and_fences_late_response(self):
        self.submit()
        view = self.prepare()
        path = '/api/ai/conversations/' + view['id']
        finish_callbacks = []

        def provider(model, api_key, messages, on_finish):
            finish_callbacks.append(on_finish)
            if len(finish_callbacks) == 2:
                on_finish(json.dumps(dict(action='reduce', reason='Repeated overshoots support backing off.')), 'complete')
            return {'mock': 'accepted'}

        def send(sequence, pending_id=None):
            turn_id = str(uuid4())
            response = self.client.post(path + '/messages', json=dict(
                id=turn_id, message='Interpret today', model='test/model',
                expected_sequence=sequence, retry_pending_turn_id=pending_id,
            ))
            return turn_id, response

        with patch.object(main, '_get_ai_api_key', return_value='mock-only'), patch.object(
            main, '_stream_openrouter', side_effect=provider
        ) as remote:
            original, response = send(0)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('retry_pending_turn_id', self.client.get(path).json())
            self.assertEqual(send(1, original)[1].status_code, 409)

            with self.sessions() as db:
                db.get(CoachingTurn, original).created_at = (
                    datetime.now(timezone.utc) - timedelta(minutes=6)
                ).isoformat()
                db.commit()

            pending = self.client.get(path).json()
            self.assertEqual(pending['retry_pending_turn_id'], original)
            self.assertEqual(pending['turns'][0]['status'], 'pending')
            self.assertEqual(send(1)[1].status_code, 409)
            self.assertEqual(send(1, str(uuid4()))[1].status_code, 409)
            remote.assert_called_once()

            _, response = send(1, original)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(send(1, original)[1].status_code, 409)
            finish_callbacks[0]('Late response from the earlier request.', 'complete')
            self.assertEqual(remote.call_count, 2)

        saved = self.client.get('/api/ai/daily-reviews/' + str(DAY)).json()
        self.assertEqual(saved['id'], view['id'])
        self.assertEqual(saved['evidence'], view['evidence'])
        self.assertEqual([t['status'] for t in saved['turns']], ['interrupted', 'complete'])
        self.assertIsNone(saved['turns'][0]['response'])
        self.assertEqual(saved['daily_recommendation']['action'], 'reduce')
        self.assertNotIn('retry_pending_turn_id', saved)
        self.assertEqual(self.client.get('/api/readiness/today').json()['tiredness'], 2)

    def test_verbose_response_fails_and_legacy_review_remains_accessible(self):
        self.submit()
        legacy_id = daily_coaching.identity(daily_coaching.observation(self.db, DAY), 'v1')
        self.db.add(CoachingConversation(id=legacy_id, created_at=coaching.now_iso(),
                                         evidence=coaching.encode({'version':'daily-interpretation-v1'})))
        self.db.add(CoachingTurn(id=str(uuid4()), conversation_id=legacy_id, sequence=1,
                                 message='Interpret today', model='test/model', status='complete',
                                 response='Existing long review.', created_at=coaching.now_iso()))
        self.db.commit()
        current = self.prepare()
        self.assertNotEqual(current['id'], legacy_id)
        path = '/api/ai/conversations/'
        self.assertEqual(self.client.get(path + legacy_id).json()['turns'][0]['response'],
                         'Existing long review.')

        def provider(model, api_key, messages, on_finish):
            on_finish('## Long report instead of a recommendation', 'complete')
            return {'mock': 'done'}

        with patch.object(main, '_get_ai_api_key', return_value='mock-only'), patch.object(
            main, '_stream_openrouter', side_effect=provider
        ):
            response = self.client.post(path + current['id'] + '/messages', json=dict(
                id=str(uuid4()), message='What should I do next session?', model='test/model',
                expected_sequence=0,
            ))
        self.assertEqual(response.status_code, 200)
        failed = self.client.get(path + current['id']).json()
        self.assertEqual(failed['turns'][0]['status'], 'failed')
        self.assertNotIn('daily_recommendation', failed)

    def test_missing_key_history_and_future_do_not_block_daily_logging(self):
        self.submit();view=self.prepare()
        with patch.object(main,'_get_ai_api_key',return_value=None):
            response=self.client.post('/api/ai/conversations/'+view['id']+'/messages',json=dict(id=str(uuid4()),message='Interpret',model='test/model',expected_sequence=0))
            self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.get('/api/readiness/today').status_code,200)
        self.assertEqual(self.prepare()['turns'],[])
        self.assertEqual(self.client.post('/api/ai/daily-reviews',json=dict(date='2000-01-01')).status_code,422)
        future=DAY+timedelta(days=1)
        self.db.add(DailyReadiness(date=future,tiredness=0));self.db.commit()
        self.assertEqual(self.client.post('/api/ai/daily-reviews',json=dict(date=str(future))).status_code,422)
        # Missing component stays unavailable, even when other historical scores exist.
        self.client.put('/api/readiness/'+str(DAY),json=dict(tiredness=0))
        partial=self.prepare()['evidence']['daily_context']
        self.assertIsNone(partial['scores']['combined_score'])
        self.assertIsNone(partial['observation']['perceived_recovery'])
