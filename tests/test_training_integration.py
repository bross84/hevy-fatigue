"""Combined workflow and recovery, using disposable SQLite and mocked Hevy."""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rackbook import main as training, workout_saves as saves
from rackbook.database import get_db


def entry():
    return training.WorkoutEntry(client_workout_id=uuid4(), title='ST Test',
        weight_unit='lb', start_time='2026-10-29T10:00:00Z', end_time='2026-10-29T11:00:00Z',
        exercises=[dict(exercise_template_id='sq', title='Squat', sets=[
            dict(weight_kg=100, reps=1, rpe=8, ts=True), dict(weight_kg=80, reps=5, rpe=5)])],
        soreness={'squat': {'level': 2}})


class SaveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.tmp.name)/'rack.db'))
        env.start(); self.addCleanup(env.stop)
        training.initialize()
        sync = patch('training_integration.request_monitoring_refresh', return_value='pending')
        self.sync = sync.start(); self.addCleanup(sync.stop)
        self.remote = Mock()
        self.remote.create_workout.return_value = {'id': 'remote-1'}
        self.factory = Mock(return_value=self.remote)
        self.data = entry()

    def counts(self):
        with closing(get_db()) as db:
            return tuple(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                         for table in ('logged_sets','training_max_history','session_soreness','mesocycle_completions'))

    def test_review_and_original_prescription_commit_once_with_recovery(self):
        from rackbook.tests.test_session_review import captured_payload
        payload=captured_payload()
        payload['client_workout_id']=str(uuid4())
        data=training.WorkoutEntry(**payload)
        with patch('rackbook.training_max.record',side_effect=RuntimeError('disk')):
            with self.assertLogs('rackbook.workout_saves',level='ERROR'):
                self.assertEqual(saves.save(data,self.factory)['state'],'remote_saved')
        self.assertEqual(self.counts(),(0,0,0,0))
        with closing(get_db()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM session_reviews').fetchone()[0],0)
        self.assertEqual(saves.save(data,self.factory)['state'],'complete')
        self.assertEqual(saves.save(data,self.factory)['state'],'complete')
        self.remote.create_workout.assert_called_once()
        from rackbook.session_review import read
        review=read('remote-1')
        self.assertTrue(review['available'])
        self.assertEqual(review['prescription']['plan_revision'],3)
        self.assertEqual(review['review']['movements'][0]['omitted_sets'],1)
        with closing(get_db()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM session_reviews').fetchone()[0],1)
        changed=data.model_copy(deep=True)
        changed.prescription.exercises[0].sets[0].reps=8
        with self.assertRaises(HTTPException):saves.save(changed,self.factory)

    def test_review_endpoint_is_read_only_and_legacy_history_is_unavailable(self):
        from rackbook.tests.test_session_review import captured_payload
        client=TestClient(training.app)
        self.addCleanup(client.close)
        missing=client.get('/session-reviews/legacy').json()
        self.assertFalse(missing['available'])
        data=training.WorkoutEntry(client_workout_id=uuid4(),**captured_payload())
        saves.save(data,self.factory)
        first=client.get('/session-reviews/remote-1')
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json(),client.get('/session-reviews/remote-1').json())
        self.remote.create_workout.assert_called_once()

    def test_ambiguous_snapshot_links_rejected_before_remote_io(self):
        from rackbook.tests.test_session_review import captured_payload
        from pydantic import ValidationError
        payload=captured_payload()
        payload['exercises'][0]['sets'][1]['review']['set_id']='a'
        with self.assertRaises(ValidationError):training.WorkoutEntry(**payload)
        self.factory.assert_not_called()

    def test_prescribed_and_actual_rpe_survive_local_recovery(self):
        self.data.exercises[0].sets[0].target_rpe = 7
        self.data.exercises[0].sets[1].target_rpe = 6
        with patch('rackbook.set_log.record', side_effect=RuntimeError('disk')):
            with self.assertLogs('rackbook.workout_saves', level='ERROR'):
                self.assertEqual(saves.save(self.data, self.factory)['state'], 'remote_saved')
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        self.assertEqual(saves.save(self.data, self.factory)['state'], 'complete')
        self.assertEqual(saves.save(self.data, self.factory)['state'], 'complete')
        self.remote.create_workout.assert_called_once()
        with closing(get_db()) as db:
            rows = db.execute('SELECT target_rpe, rpe FROM logged_sets ORDER BY id').fetchall()
        self.assertEqual([tuple(r) for r in rows], [(7, 8), (6, 5)])
        remote_sets = self.remote.create_workout.call_args.args[0]['workout']['exercises'][0]['sets']
        self.assertEqual([s['rpe'] for s in remote_sets], [8, None])
        self.assertTrue(all('target_rpe' not in s for s in remote_sets))
        changed = self.data.model_copy(deep=True)
        changed.exercises[0].sets[1].target_rpe = 7
        with self.assertRaises(HTTPException) as caught:
            saves.save(changed, self.factory)
        self.assertEqual(caught.exception.status_code, 409)

    def test_legacy_journal_payload_hash_stays_compatible(self):
        from hashlib import sha256
        saves.prepare(self.data)
        old_payload = self.data.model_dump(mode='json')
        old_payload.pop('client_workout_id')
        old_payload.pop('prescription')
        for ex in old_payload['exercises']:
            for s in ex['sets']:
                s.pop('target_rpe')
                s.pop('review')
        frozen = saves.canonical(old_payload)
        self.assertEqual(saves.read(self.data.client_workout_id)['request_payload'], frozen)
        with closing(get_db()) as db, db:
            db.execute('UPDATE workout_saves SET request_payload=?,payload_hash=? WHERE client_workout_id=?',
                       (frozen, sha256(frozen.encode()).hexdigest(), str(self.data.client_workout_id)))
        self.assertEqual(saves.save(self.data, self.factory)['state'], 'complete')

    def test_target_rpe_migration_preserves_history_without_inventing_targets(self):
        from rackbook.database import init_db
        saves.save(self.data, self.factory)
        with closing(get_db()) as db, db:
            before = [dict(r) for r in db.execute('SELECT * FROM logged_sets ORDER BY id')]
            self.assertIn('target_rpe', {r[1] for r in db.execute('PRAGMA table_info(logged_sets)')})
            db.execute('ALTER TABLE logged_sets DROP COLUMN target_rpe')
        init_db()
        init_db()
        with closing(get_db()) as db:
            after = [dict(r) for r in db.execute('SELECT * FROM logged_sets ORDER BY id')]
        self.assertEqual(after, before)

    def test_target_rpe_validation_rejects_out_of_range_and_nonfinite(self):
        from pydantic import ValidationError
        for value in (-1, 11, float('nan'), float('inf')):
            with self.assertRaises(ValidationError):
                training.EntrySet(target_rpe=value)

    def test_freeform_retry_and_conflicting_payload(self):
        first = saves.save(self.data, self.factory)
        self.assertEqual(first['state'], 'complete')
        self.assertEqual(saves.save(self.data, self.factory)['id'], 'remote-1')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(), (2,1,1,0))
        with closing(get_db()) as db:
            self.assertEqual(db.execute('SELECT rpe FROM logged_sets ORDER BY id DESC').fetchone()[0], 5)
        changed = self.data.model_copy(update={'title': 'Changed'})
        with self.assertRaises(HTTPException) as caught: saves.save(changed, self.factory)
        self.assertEqual(caught.exception.status_code, 409)

    def test_stale_plan_rejection_is_durable_and_can_be_corrected_with_new_identity(self):
        from rackbook.mesocycles import PlanLink
        self.data.planned_session=PlanLink(mesocycle_id='missing',session_id='missing')
        rejected=saves.save(self.data,self.factory)
        self.assertEqual(rejected['state'],'rejected')
        self.assertEqual(saves.status(self.data.client_workout_id)['state'],'rejected')
        self.factory.assert_not_called()
        self.assertEqual(saves.save(self.data,self.factory)['state'],'rejected')
        corrected=self.data.model_copy(update={'planned_session':None})
        with self.assertRaises(HTTPException) as conflict:saves.save(corrected,self.factory)
        self.assertEqual(conflict.exception.status_code,409)
        corrected.client_workout_id=uuid4()
        self.assertEqual(saves.save(corrected,self.factory)['state'],'complete')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_ts_validation_rejection_never_attempts_remote_save(self):
        self.data.exercises[0].sets[0].rpe=None
        result=saves.save(self.data,self.factory)
        self.assertEqual(result['state'],'rejected')
        self.assertIn('TS',result['failure_reason'])
        self.assertEqual(saves.read(self.data.client_workout_id)['state'],'rejected')
        self.factory.assert_not_called()
        self.assertEqual(self.counts(),(0,0,0,0))

    def test_request_model_rejection_precedes_route_and_journal(self):
        from fastapi import FastAPI
        mounted=FastAPI();mounted.mount('/training',training.app)
        client=TestClient(mounted);self.addCleanup(client.close)
        payload=self.data.model_dump(mode='json')
        payload['exercises'][0]['notes']={'invalid':'not a string'}
        with patch('rackbook.hevy_client.HevyClient') as remote:
            response=client.post('/training/hevy/workouts',json=payload)
        self.assertEqual(response.status_code,422)
        self.assertIsInstance(response.json()['detail'],list)
        remote.assert_not_called()
        self.assertEqual(client.get('/training/workout-saves/'+str(self.data.client_workout_id)).status_code,404)

    def test_rejection_reason_preserves_validation_detail_without_credential(self):
        self.remote.api_key='fake-private-key'
        request=httpx.Request('POST','https://example.invalid')
        self.remote.create_workout.side_effect=httpx.HTTPStatusError('rejected',request=request,
            response=httpx.Response(422,request=request,json={'error':'Invalid exercise_template_id; fake-private-key'}))
        result=saves.save(self.data,self.factory)
        self.assertIn('Invalid exercise_template_id',result['failure_reason'])
        self.assertNotIn('fake-private-key',result['failure_reason'])

    def test_disabled_writes_remain_prepared_and_resume_with_same_identity(self):
        from rackbook.hevy_client import HevyClient
        with patch.dict(os.environ,HEVY_WRITES_ENABLED='0'),patch('rackbook.hevy_client.httpx.Client') as http:
            result=saves.save(self.data,lambda:HevyClient(api_key='test-fake'))
        self.assertEqual(result['state'],'prepared')
        self.assertIn('disabled',result['failure_reason'])
        http.assert_not_called()
        frozen=saves.read(self.data.client_workout_id)['hevy_payload']
        with patch.dict(os.environ,HEVY_WRITES_ENABLED='1'):
            self.assertEqual(saves.save(self.data,self.factory)['state'],'complete')
        self.remote.create_workout.assert_called_once_with(json.loads(frozen))

    def test_missing_credential_is_preflight_failure_not_ambiguous_delivery(self):
        from rackbook.hevy_client import HevyClient
        client=HevyClient.__new__(HevyClient);client.api_key=None
        with patch.dict(os.environ,HEVY_WRITES_ENABLED='1'),patch('rackbook.hevy_client.httpx.Client') as http:
            result=saves.save(self.data,lambda:client)
        self.assertEqual(result['state'],'prepared')
        self.assertIn('credential',result['failure_reason'])
        http.assert_not_called()
        self.assertEqual(saves.save(self.data,self.factory)['state'],'complete')
        self.remote.create_workout.assert_called_once()

    def test_generic_value_error_remains_uncertain_and_cannot_be_reposted(self):
        self.remote.create_workout.side_effect=ValueError('malformed response after POST')
        self.assertEqual(saves.save(self.data,self.factory)['state'],'uncertain')
        self.assertEqual(saves.save(self.data,self.factory)['state'],'uncertain')
        self.remote.create_workout.assert_called_once()

    def test_legacy_callers_get_http_errors_unless_a_remote_save_is_known(self):
        from fastapi import FastAPI
        from rackbook.hevy_client import WorkoutNotSent
        mounted=FastAPI();mounted.mount('/training',training.app)
        client=TestClient(mounted);self.addCleanup(client.close)
        payload=self.data.model_dump(mode='json');payload.pop('client_workout_id')
        request=httpx.Request('POST','https://example.invalid')
        cases=[(httpx.HTTPStatusError('rejected',request=request,response=httpx.Response(422,request=request)),502),
               (httpx.ReadTimeout('lost response'),502),(WorkoutNotSent('Writes disabled'),400)]
        for error,expected in cases:
            self.remote.create_workout.side_effect=error
            with patch('rackbook.hevy_client.HevyClient',return_value=self.remote):
                response=client.post('/training/hevy/workouts',json=payload)
            self.assertEqual(response.status_code,expected,response.text)
            self.assertIn('detail',response.json())
        self.remote.create_workout.side_effect=None
        with patch('rackbook.hevy_client.HevyClient',return_value=self.remote),patch('rackbook.set_log.record',side_effect=RuntimeError('disk')):
            response=client.post('/training/hevy/workouts',json=payload)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['id'],'remote-1')
        self.assertEqual(response.json()['state'],'remote_saved')

    def test_repeated_finalize_releases_lock_before_refresh_status_update(self):
        self.assertEqual(saves.save(self.data,self.factory)['state'],'complete')
        original=saves.get_db
        def short_timeout():
            db=original();db.execute('PRAGMA busy_timeout=50');return db
        with patch.object(saves,'get_db',short_timeout),patch('training_integration.monitoring_visible',return_value=True):
            # The previous implementation silently timed out writing refresh
            # metadata from status() while holding its own BEGIN IMMEDIATE.
            self.assertEqual(saves.finalize(self.data.client_workout_id)['monitoring_refresh'],'complete')
        self.assertEqual(saves.read(self.data.client_workout_id)['monitoring_refresh'],'complete')
        self.assertEqual(self.counts(),(2,1,1,0))
        self.remote.create_workout.assert_called_once()

    def test_concurrent_claim_produces_one_post(self):
        started, release = threading.Event(), threading.Event()
        def slow(body):
            started.set(); self.assertTrue(release.wait(5)); return {'id':'remote-1'}
        self.remote.create_workout.side_effect=slow
        with ThreadPoolExecutor(2) as pool:
            first=pool.submit(saves.save,self.data,self.factory)
            self.assertTrue(started.wait(5))
            second=pool.submit(saves.save,self.data,self.factory).result(5)
            self.assertEqual(second['state'],'sending')
            release.set(); self.assertEqual(first.result(5)['state'],'complete')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_timeout_and_restart_never_repost(self):
        self.remote.create_workout.side_effect=httpx.ReadTimeout('lost response')
        self.assertEqual(saves.save(self.data,self.factory)['state'],'uncertain')
        training.initialize()
        self.assertEqual(saves.save(self.data,self.factory)['state'],'uncertain')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(),(0,0,0,0))

    def test_interrupted_sending_is_uncertain_at_restart(self):
        client_id=saves.prepare(self.data)
        saves.transition(client_id,'sending')
        training.initialize()
        self.assertEqual(saves.save(self.data,self.factory)['state'],'uncertain')
        self.remote.create_workout.assert_not_called()

    def test_remote_id_committed_and_local_transaction_rolls_back(self):
        with patch('rackbook.training_max.record', side_effect=RuntimeError('disk full')):
            result=saves.save(self.data,self.factory)
        self.assertEqual(result['state'],'remote_saved')
        self.assertEqual(result['id'],'remote-1')
        self.assertEqual(self.counts(),(0,0,0,0))
        self.assertEqual(saves.finalize(self.data.client_workout_id)['state'],'complete')
        saves.finalize(self.data.client_workout_id)
        self.assertEqual(self.counts(),(2,1,1,0))
        self.remote.create_workout.assert_called_once()

    def test_reconcile_normalized_rounding_omitted_rpe_and_mismatch(self):
        self.remote.create_workout.side_effect=httpx.ReadTimeout('lost')
        saves.save(self.data,self.factory)
        row=saves.read(self.data.client_workout_id)
        actual=json.loads(row['hevy_payload'])['workout']
        actual['id']='verified'
        actual['start_time']='2026-10-29T06:00:00-04:00'
        del actual['exercises'][0]['sets'][1]['rpe']
        bad=copy.deepcopy(actual);bad['exercises'][0]['sets'][0]['reps']=2
        self.remote.get_workout.return_value=bad
        with self.assertRaises(HTTPException) as caught:
            saves.reconcile(self.data.client_workout_id,'verified',self.factory)
        self.assertEqual(caught.exception.status_code,409)
        self.assertEqual(self.counts(),(0,0,0,0))
        self.remote.get_workout.return_value=actual
        self.assertEqual(saves.reconcile(self.data.client_workout_id,'verified',self.factory)['state'],'complete')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_rejected_is_retained_and_not_reposted(self):
        request=httpx.Request('POST','https://example.invalid')
        self.remote.create_workout.side_effect=httpx.HTTPStatusError('invalid',request=request,response=httpx.Response(422,request=request))
        self.assertEqual(saves.save(self.data,self.factory)['state'],'rejected')
        self.assertEqual(saves.save(self.data,self.factory)['state'],'rejected')
        self.remote.create_workout.assert_called_once()

    def test_optional_failures_leave_required_records_complete(self):
        self.sync.side_effect=RuntimeError('sync unavailable')
        with patch('rackbook.fatigue_trial.complete_workout',side_effect=RuntimeError('trial unavailable')):
            result=saves.save(self.data,self.factory)
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['monitoring_refresh'],'failed')
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_late_results_and_optional_status_failure_never_reopen_completion(self):
        self.sync.side_effect=RuntimeError('sync unavailable')
        with patch('rackbook.workout_saves.monitoring_status',side_effect=RuntimeError('status unavailable')):
            result=saves.save(self.data,self.factory)
        self.assertEqual(result['state'],'complete')
        saves.transition(self.data.client_workout_id,'uncertain','late failure')
        saves.transition(self.data.client_workout_id,'remote_saved',remote_id='remote-1')
        self.assertEqual(saves.status(self.data.client_workout_id)['state'],'complete')
        saves.finalize(self.data.client_workout_id)
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_mounted_recovery_api_only_finalizes_known_remote_id(self):
        from fastapi import FastAPI
        mounted=FastAPI();mounted.mount('/training',training.app)
        client=TestClient(mounted)
        self.addCleanup(client.close)
        client_id=str(self.data.client_workout_id)
        self.assertEqual(client.get('/training/workout-saves/'+client_id).status_code,404)
        with patch('rackbook.hevy_client.HevyClient',return_value=self.remote), patch('rackbook.set_log.record',side_effect=RuntimeError('disk full')):
            result=client.post('/training/hevy/workouts',json=self.data.model_dump(mode='json'))
        self.assertEqual(result.json()['state'],'remote_saved')
        self.assertEqual(client.get('/training/workout-saves/'+client_id).json()['hevy_workout_id'],'remote-1')
        self.assertEqual(client.post('/training/workout-saves/'+client_id+'/finalize').json()['state'],'complete')
        self.assertEqual(client.post('/training/workout-saves/'+client_id+'/finalize').json()['state'],'complete')
        self.remote.create_workout.assert_called_once()
        self.assertEqual(self.counts(),(2,1,1,0))

    def test_consistent_wal_backup_and_existing_trial_copy_startup(self):
        from tools.backup_sqlite import backup
        from tools.data_inventory import inventory
        import sqlite3
        # Nonempty frozen payloads are opaque historical records, including
        # unavailable shadows; startup must never regenerate or rewrite them.
        with closing(get_db()) as db, db:
            self.assertTrue(db.execute('PRAGMA table_info(fatigue_trial_shadow)').fetchall())
            db.execute("INSERT INTO fatigue_trial_snapshots VALUES ('trial','session','sq','start','recorded','shared-trial-v0',1,0,?,NULL,NULL)", ('{"frozen":"original"}',))
            db.execute("INSERT INTO fatigue_trial_shadow VALUES ('trial','hf-recovery-shadow-v1',?)", ('{"status":"unavailable","frozen":true}',))
        source=Path(os.environ['RACKBOOK_DB_PATH'])
        with closing(sqlite3.connect(source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute("INSERT INTO app_settings(key,value) VALUES ('backup-fixture','committed WAL')")
            writer.commit()
            target=Path(self.tmp.name)/'copy.db'
            backup(source,target)
            before=inventory(target)
        with self.assertRaises(FileExistsError):backup(source,target)
        with patch.dict(os.environ,RACKBOOK_DB_PATH=str(target)):
            training.initialize();training.initialize()
        after=inventory(target)
        self.assertEqual(before,after)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute("SELECT value FROM app_settings WHERE key='backup-fixture'").fetchone()[0],'committed WAL')

    def test_planned_retry_advances_once_and_initialization_preserves_trial(self):
        from rackbook import mesocycles
        plan=mesocycles.save_plan(mesocycles.PlanInput(name='Plan',weeks=[{'name':'Week','sessions':[
            {'id':'one','name':'One','exercises':[{'exercise_template_id':'sq','title':'Squat','sets':[{'reps':1,'rpe':8}]}]},
            {'id':'two','name':'Two','exercises':[]}]}]))
        self.data.planned_session=mesocycles.PlanLink(mesocycle_id=plan['id'],session_id='one')
        self.assertEqual(saves.save(self.data,self.factory)['state'],'complete')
        saves.save(self.data,self.factory)
        self.assertEqual(self.counts(),(2,1,1,1))
        with closing(get_db()) as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fatigue_trial%'")]
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        training.initialize();training.initialize()
        with closing(get_db()) as db:
            after={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
        self.assertEqual(before,after)
        self.assertEqual(self.counts(),(2,1,1,1))

    def test_host_tables_are_absent_and_preview_blocks_client(self):
        from rackbook.hevy_client import HevyClient
        with closing(get_db()) as db:
            names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('daily_readiness',names)
        with patch.dict(os.environ,HEVY_WRITES_ENABLED='0'), patch('rackbook.hevy_client.httpx.Client') as http:
            with self.assertRaises(ValueError): HevyClient(api_key='fake').create_workout({})
            http.assert_not_called()


class CombinedStartupTests(unittest.TestCase):
    def test_mounted_preview_blocks_before_client_or_save_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'PYTHONIOENCODING':'utf-8','DB_PATH':str(Path(folder)/'host.db'),
                 'RACKBOOK_DB_PATH':str(Path(folder)/'rack.db'),
                 'FERNET_KEY_PATH':str(Path(folder)/'app.key'),
                 'HEVY_WRITES_ENABLED':'0','RACKBOOK_READ_ONLY_PREVIEW':'1',
                 'HEVY_FATIGUE_DB_PATH':str(Path(folder)/'host.db')}
            script='''
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch
from uuid import uuid4
import main
from rackbook.database import get_db
from rackbook import main as training
body={'client_workout_id':str(uuid4()),'title':'Preview regression',
      'start_time':'2026-10-31T10:00:00Z','end_time':'2026-10-31T11:00:00Z',
      'exercises':[{'exercise_template_id':'sq','sets':[{'type':'normal','weight_kg':100,'reps':5,'rpe':5}]}]}
with TestClient(main.app) as client, patch('rackbook.main.hevy_client.HevyClient') as hevy:
 for method in ('POST','PUT','PATCH','DELETE'):
  for payload in (body, {}):
   response=client.request(method,'/training/hevy/workouts',json=payload)
   assert response.status_code==403,(method,response.status_code)
 hevy.assert_not_called()
 assert client.get('/training/log').status_code==200
 assert client.get('/api/sync/status').status_code==200
 with patch.object(training.hevy_client,'HevyClient') as reader:
  reader.return_value.list_workouts.return_value={'page':1,'page_count':1,'workouts':[]}
  assert client.get('/training/hevy/workouts').status_code==200
  reader.return_value.list_workouts.assert_called_once()
 # Match nested mounts as well as /training and standalone logging.
 nested=FastAPI(); nested.mount('/outer',main.app)
 with TestClient(nested) as nested_client:
  assert nested_client.post('/outer/training/hevy/workouts',json=body).status_code==403
 assert TestClient(training.app).post('/hevy/workouts',json=body).status_code==403
 with get_db() as db:
  assert db.execute('SELECT COUNT(*) FROM workout_saves').fetchone()[0]==0
  assert db.execute('SELECT COUNT(*) FROM logged_sets').fetchone()[0]==0
'''
            result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_monitoring_sync_guard_and_failure_status_use_existing_pipeline(self):
        import main
        import training_integration
        lock=threading.Lock()
        with patch.object(training_integration,'_host_started',True), patch.object(main,'_sync_lock',lock), patch('training_integration.threading.Thread') as thread:
            lock.acquire()
            try:self.assertEqual(training_integration.request_monitoring_refresh('saved'),'pending')
            finally:lock.release()
            thread.assert_not_called()
        for last_result,exception,expected in [({'error':'mock failure'},None,'failed'), ({},HTTPException(409,'running'),'pending')]:
            with patch.object(training_integration,'_host_started',True), patch.object(main,'_sync_lock',threading.Lock()), \
                 patch('training_integration.threading.Thread') as thread, patch.object(main,'trigger_sync',side_effect=exception), \
                 patch.object(main,'_sync_status',{'last_result':last_result}), patch('database.SessionLocal') as session, \
                 patch('rackbook.workout_saves.monitoring_status') as update:
                session.return_value.__enter__.return_value.query.return_value.filter_by.return_value.first.return_value=None
                training_integration.request_monitoring_refresh('saved')
                thread.call_args.kwargs['target']()
                update.assert_called_once_with('saved',expected)

    def test_daily_and_pattern_fixture_matches_recorded_remote_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'DB_PATH':str(Path(folder)/'host.db'),'RACKBOOK_DB_PATH':str(Path(folder)/'rack.db'),
                 'TZ':'America/New_York','PYTHONIOENCODING':'utf-8'}
            code=Path('tools/monitoring_fixture.py').read_text(encoding='utf-8')
            result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            expected=json.loads(Path('tests/fixtures/monitoring-baseline.json').read_text())
            self.assertEqual(json.loads(result.stdout.splitlines()[-1]),expected)

    def test_normal_and_full_sync_cannot_replace_exact_local_rpe(self):
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'DB_PATH':str(Path(folder)/'host.db'),'RACKBOOK_DB_PATH':str(Path(folder)/'rack.db'),
                 'PYTHONIOENCODING':'utf-8','FERNET_KEY_PATH':str(Path(folder)/'key')}
            script='''
from unittest.mock import Mock,patch
from uuid import uuid4
import main
from database import SessionLocal, WorkoutLog
from rackbook import main as training, workout_saves
from rackbook.database import get_db
main.startup()
remote=Mock();remote.create_workout.return_value={'id':'saved'}
entry=training.WorkoutEntry(client_workout_id=uuid4(),title='ST Test',start_time='2026-10-29T10:00:00Z',end_time='2026-10-29T11:00:00Z',exercises=[dict(exercise_template_id='sq',title='Squat',sets=[dict(weight_kg=80,reps=5,rpe=5)])])
with patch('training_integration.request_monitoring_refresh',return_value='pending'):
 assert workout_saves.save(entry,lambda:remote)['state']=='complete'
raw={**entry.model_dump(),'id':'saved'}
raw['exercises'][0]['sets'][0]['rpe']=None
client=Mock();client.test_connection.return_value=True
client.get_workouts.return_value={'workouts':[raw],'page_count':1}
client.get_workout_events.return_value={'events':[{'type':'updated','workout':raw}],'page_count':1}
with patch('importer.HevyClient',return_value=client), SessionLocal() as db:
 main.trigger_sync(db=db)
 main.trigger_sync(db=db)
 main.trigger_sync_full(db=db)
 assert db.query(WorkoutLog).count()==1
 assert db.query(WorkoutLog).first().rpe != 5
with get_db() as db:
 assert db.execute('SELECT rpe FROM logged_sets').fetchone()[0]==5
 assert db.execute('SELECT COUNT(*) FROM logged_sets').fetchone()[0]==1
'''
            result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_startup_twice_navigation_assets_and_separate_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            env={**os.environ,'PYTHONIOENCODING':'utf-8','DB_PATH':str(Path(folder)/'host.db'),'RACKBOOK_DB_PATH':str(Path(folder)/'rack.db'),
                 'FERNET_KEY_PATH':str(Path(folder)/'app.key'),'HEVY_WRITES_ENABLED':'0','HEVY_FATIGUE_DB_PATH':str(Path(folder)/'host.db')}
            script='''
from fastapi.testclient import TestClient
import main, sqlite3, os
for i in range(2):
 with TestClient(main.app) as c:
  for path in ('/','/training/log','/training/microcycles','/training/mesocycles','/training/recent','/training/progress','/training/rpe-charts','/training/stress','/training/stress/details','/training/trial','/training/legacy'):
   r=c.get(path); assert r.status_code==200,(path,r.status_code)
  for path in ('/training/static/training.js','/training/static/draft-transfer.js','/training/static/save-recovery.js','/training/static/vendor/chart-4.4.0.umd.js','/training/sw.js'):
   assert c.get(path).status_code==200,path
  manifest=c.get('/training/manifest.webmanifest').json()
  assert manifest['scope']=='/training/' and manifest['start_url']=='/training/log'
  for icon in manifest['icons']: assert c.get(icon['src']).status_code==200
  assert '/training/log' in c.get('/').text and 'Check-in History' in c.get('/').text
  assert '/#settings' in c.get('/training/log').text
with sqlite3.connect(os.environ['DB_PATH']) as db:
 assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='logged_sets'").fetchone()
with sqlite3.connect(os.environ['RACKBOOK_DB_PATH']) as db:
 assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='daily_readiness'").fetchone()
'''
            result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            env['RACKBOOK_DB_PATH']=env['DB_PATH']
            result=subprocess.run([sys.executable,'-c','import main; main.startup()'],env=env,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('must identify different SQLite files',result.stderr)
