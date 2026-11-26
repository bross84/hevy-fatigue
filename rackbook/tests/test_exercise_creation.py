"""No real account or DB: identity, retry, recovery and independent history."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
from pydantic import ValidationError
from rackbook import exercise_creation as service
from rackbook.database import init_db, get_db
from rackbook.hevy_client import HevyClient, WorkoutNotSent


class CreationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'RACKBOOK_DB_PATH':str(Path(self.tmp.name)/'test.db'), 'HEVY_WRITES_ENABLED':'1', 'RACKBOOK_READ_ONLY_PREVIEW':'0'})
        env.start(); self.addCleanup(env.stop)
        init_db()
        self.client = Mock()
        self.client.list_exercise_templates.return_value = []
        self.client.create_exercise_template.return_value = 'new-id'
        self.data = service.CreationInput(request_id=uuid4(), title='Low Pin Bench', exercise_type='weight_reps', equipment_category='barbell', muscle_group='chest', other_muscles=['triceps'])

    def test_success_is_idempotent_and_cached(self):
        result = service.create(self.data, self.client)
        self.assertEqual(result['state'], 'complete')
        self.assertEqual(service.create(self.data, self.client), result)
        self.client.create_exercise_template.assert_called_once()
        with get_db() as db:
            self.assertEqual(db.execute('SELECT title FROM hevy_exercise_cache WHERE id=?', ('new-id',)).fetchone()[0], 'Low Pin Bench')

    def test_duplicate_copies_only_preferences(self):
        self.data.source_id = 'original'
        self.client.get_exercise_template.return_value = {'title':'Bench', 'type':'weight_reps', 'equipment':'barbell'}
        with get_db() as db:
            db.execute("INSERT INTO exercise_refs(exercise_template_id,e1rm_lb,tm_lb,bar_kg,rest_sec,step_kg) VALUES('original',300,285,30,210,.5)")
        service.create(self.data, self.client)
        with get_db() as db:
            ref = db.execute("SELECT * FROM exercise_refs WHERE exercise_template_id='new-id'").fetchone()
            self.assertEqual((ref['bar_kg'],ref['rest_sec'],ref['step_kg']), (30,210,.5))
            self.assertIsNone(ref['e1rm_lb']); self.assertIsNone(ref['tm_lb'])
            self.assertEqual(db.execute('SELECT count(*) FROM training_max_history').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM logged_sets').fetchone()[0],0)

    def test_timeout_never_reposts_and_reconciles_full_match(self):
        self.client.create_exercise_template.side_effect = httpx.ReadTimeout('timeout')
        self.assertEqual(service.create(self.data,self.client)['state'],'uncertain')
        service.create(self.data,self.client)
        self.client.create_exercise_template.assert_called_once()
        match={'id':'remote','title':self.data.title,'type':'weight_reps','equipment':'barbell','primary_muscle_group':'chest','secondary_muscle_groups':['triceps'],'is_custom':True}
        self.client.list_exercise_templates.return_value=[{**match,'equipment':'dumbbell'}]
        self.assertEqual(service.reconcile(self.data.request_id,self.client)['state'],'uncertain')
        self.client.list_exercise_templates.return_value=[match]
        self.assertEqual(service.reconcile(self.data.request_id,self.client)['state'],'complete')
        self.client.create_exercise_template.assert_called_once()

    def test_uncertain_same_name_new_uuid_is_blocked(self):
        self.client.create_exercise_template.side_effect=httpx.ReadTimeout('timeout')
        service.create(self.data,self.client)
        self.data.request_id=uuid4()
        with self.assertRaises(ValueError):service.create(self.data,self.client)
        self.client.create_exercise_template.assert_called_once()

    def test_acknowledged_can_finalize_without_reposting(self):
        with patch.object(service,'_finish',side_effect=RuntimeError('local failure')):
            with self.assertRaises(RuntimeError):service.create(self.data,self.client)
        self.assertEqual(service.status(self.data.request_id)['state'],'acknowledged')
        self.assertEqual(service.reconcile(self.data.request_id,self.client)['state'],'complete')
        self.client.create_exercise_template.assert_called_once()

    def test_flags_block_service_and_client(self):
        for flags in ({'HEVY_WRITES_ENABLED':'0'}, {'RACKBOOK_READ_ONLY_PREVIEW':'1'}):
            with patch.dict(os.environ,flags):
                with self.assertRaises(PermissionError):service.create(self.data,self.client)
                with self.assertRaises(WorkoutNotSent):HevyClient('test').create_exercise_template({})
        self.client.create_exercise_template.assert_not_called()

    def test_validation(self):
        for change in ({'title':' '},{'equipment_category':'invented'},{'other_muscles':['chest']},{'other_muscles':['triceps','triceps']}):
            with self.assertRaises(ValidationError):service.CreationInput(**{**self.data.model_dump(),**change})

    def test_concurrent_request_observes_sending_and_never_posts_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        entered, release=Event(),Event()
        def remote(body):
            self.assertEqual(service.status(self.data.request_id)['state'],'sending')
            entered.set();release.wait(5);return 'new-id'
        self.client.create_exercise_template.side_effect=remote
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(service.create,self.data,self.client)
            self.assertTrue(entered.wait(5))
            try:self.assertEqual(service.create(self.data,self.client)['state'],'sending')
            finally:release.set()
            self.assertEqual(first.result()['state'],'complete')
        self.client.create_exercise_template.assert_called_once()

    def test_client_payload_matches_public_spec(self):
        response=Mock();response.json.return_value={'id':123}
        with patch('rackbook.hevy_client.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value=response
            body=self.data.model_dump(exclude={'request_id','source_id'})
            self.assertEqual(HevyClient('test').create_exercise_template(body),'123')
            self.assertEqual(client.return_value.__enter__.return_value.post.call_args.kwargs['json'],{'exercise':body})

    def test_routes_validate_block_and_create_with_mock_client(self):
        from fastapi.testclient import TestClient
        from rackbook import main
        with patch.object(main.hevy_client, 'HevyClient', return_value=self.client):
            with TestClient(main.app) as api:
                body=self.data.model_dump(mode='json')
                self.assertEqual(api.post('/exercise-creation',json={**body,'title':' '}).status_code,422)
                with patch.dict(os.environ,{'RACKBOOK_READ_ONLY_PREVIEW':'1'}):
                    self.assertFalse(api.get('/exercise-creation/options').json()['enabled'])
                    self.assertEqual(api.post('/exercise-creation',json=body).status_code,403)
                result=api.post('/exercise-creation',json=body)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['state'],'complete')
                self.assertEqual(api.get('/exercise-creation/'+str(self.data.request_id)).json()['exercise_id'],'new-id')
                self.assertIn('new-id',[e['id'] for e in api.get('/exercises').json()])
                listed={e['id']:e for e in api.get('/exercises').json()}
                self.assertEqual(listed['new-id']['local_id'],str(self.data.request_id))
                local=[e for e in api.get('/exercises/local').json() if e['id']==str(self.data.request_id)]
                self.assertEqual((local[0]['hevy_id'],local[0]['in_hevy'],local[0]['creation_state']),('new-id',True,'complete'))
                self.assertEqual(api.get('/static/exercise-create.js').headers['cache-control'],'no-cache')

    def test_local_record_is_committed_before_hevy_and_linked_after(self):
        def remote(body):
            with get_db() as db:
                row = db.execute('SELECT * FROM local_exercises WHERE id=?', (str(self.data.request_id),)).fetchone()
            self.assertIsNotNone(row); self.assertIsNone(row['hevy_id']); self.assertEqual(row['origin'], 'app')
            return 'new-id'
        self.client.create_exercise_template.side_effect = remote
        result = service.create(self.data, self.client)
        self.assertEqual(result['local_id'], str(self.data.request_id))
        with get_db() as db:
            from rackbook import local_exercises
            row = local_exercises.get(db, str(self.data.request_id))
        self.assertEqual((row['hevy_id'], row['title'], row['equipment'], row['other_muscles']), ('new-id', 'Low Pin Bench', 'barbell', ['triceps']))

    def test_rejected_keeps_local_copy_and_same_id_resend_updates_it(self):
        self.client.create_exercise_template.side_effect = WorkoutNotSent('no')
        self.assertEqual(service.create(self.data, self.client)['state'], 'rejected')
        with get_db() as db:
            row = db.execute('SELECT title,hevy_id FROM local_exercises WHERE id=?', (str(self.data.request_id),)).fetchone()
        self.assertEqual((row['title'], row['hevy_id']), ('Low Pin Bench', None))
        self.client.create_exercise_template.side_effect = None
        edited = service.CreationInput(**{**self.data.model_dump(), 'title': 'Low Pin Press'})
        self.assertEqual(service.create(edited, self.client)['state'], 'complete')
        self.assertEqual(self.client.create_exercise_template.call_count, 2)
        with get_db() as db:
            rows = db.execute("SELECT title,hevy_id FROM local_exercises WHERE origin='app'").fetchall()
        self.assertEqual([tuple(r) for r in rows], [('Low Pin Press', 'new-id')])

    def test_uncertain_keeps_local_copy_and_blocks_same_name(self):
        self.client.create_exercise_template.side_effect = httpx.ReadTimeout('timeout')
        service.create(self.data, self.client)
        with get_db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM local_exercises WHERE hevy_id IS NULL').fetchone()[0], 1)
        with self.assertRaises(ValueError):
            service.create(service.CreationInput(**{**self.data.model_dump(), 'request_id': uuid4()}), self.client)

    def test_catalog_sync_copies_everything_and_keeps_local_ids(self):
        from rackbook import local_exercises
        templates = [{'id': 'h1', 'title': 'Squat', 'type': 'weight_reps', 'equipment': 'barbell', 'primary_muscle_group': 'quadriceps', 'secondary_muscle_groups': ['glutes'], 'is_custom': False}]
        with get_db() as db:
            local_exercises.mirror_hevy(db, templates)
            first = db.execute("SELECT id FROM local_exercises WHERE hevy_id='h1'").fetchone()['id']
            local_exercises.mirror_hevy(db, [{**templates[0], 'title': 'Back Squat'}])
            row = db.execute("SELECT * FROM local_exercises WHERE hevy_id='h1'").fetchall()
        self.assertEqual(len(row), 1)
        self.assertEqual((row[0]['id'], row[0]['title'], row[0]['equipment'], row[0]['origin']), (first, 'Back Squat', 'barbell', 'hevy'))
        with self.assertRaises(ValueError):
            service.create(service.CreationInput(**{**self.data.model_dump(), 'title': 'back squat'}), self.client)

    def test_sync_copy_made_while_uncertain_is_folded_into_app_record(self):
        from rackbook import local_exercises
        self.client.create_exercise_template.side_effect = httpx.ReadTimeout('timeout')
        service.create(self.data, self.client)
        match = {'id': 'remote', 'title': self.data.title, 'type': 'weight_reps', 'equipment': 'barbell', 'primary_muscle_group': 'chest', 'secondary_muscle_groups': ['triceps'], 'is_custom': True}
        with get_db() as db:
            local_exercises.mirror_hevy(db, [match])
        self.client.list_exercise_templates.return_value = [match]
        with patch.object(service.time, 'time', return_value=service.time.time() + 600):
            self.assertEqual(service.reconcile(self.data.request_id, self.client)['state'], 'complete')
        with get_db() as db:
            rows = db.execute("SELECT id, origin FROM local_exercises WHERE hevy_id='remote'").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(str(self.data.request_id), 'app')])

    def test_init_backfills_existing_creations_and_cache(self):
        with get_db() as db:
            db.execute("INSERT INTO exercise_creations VALUES('old-1',?,'old press','complete','h9','[]','{}',1.0)",
                       ('{"title":"Old Press","exercise_type":"weight_reps","equipment_category":"barbell","muscle_group":"shoulders","other_muscles":[],"source_id":null}',))
            db.execute("INSERT INTO hevy_exercise_cache(id,title,primary_muscle) VALUES('h2','Deadlift','hamstrings')")
        init_db(); init_db()
        with get_db() as db:
            rows = {r['hevy_id']: (r['id'], r['origin']) for r in db.execute('SELECT * FROM local_exercises')}
        self.assertEqual(rows['h9'], ('old-1', 'app'))
        self.assertEqual(rows['h2'][1], 'hevy')
        self.assertEqual(len(rows), 2)

    def test_reconciliation_rejects_ambiguous_and_existing_matches(self):
        match={'id':'old','title':'Other','type':'weight_reps','equipment':'barbell','primary_muscle_group':'chest','secondary_muscle_groups':['triceps'],'is_custom':True}
        self.client.list_exercise_templates.return_value=[match]
        self.client.create_exercise_template.side_effect=httpx.ReadTimeout('timeout')
        service.create(self.data,self.client)
        self.client.list_exercise_templates.return_value=[{**match,'title':self.data.title}]
        self.assertEqual(service.reconcile(self.data.request_id,self.client)['state'],'uncertain')
        self.client.list_exercise_templates.return_value=[{**match,'id':identity,'title':self.data.title} for identity in ('new1','new2')]
        self.assertEqual(service.reconcile(self.data.request_id,self.client)['state'],'uncertain')


if __name__ == '__main__':unittest.main()
