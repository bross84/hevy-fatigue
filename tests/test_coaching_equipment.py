"""Available equipment for the AI coach: storage, API, report and brief. Isolated databases only."""
from datetime import date
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import coaching
import coaching_equipment
import main
from database import AppSetting, Base, CoachingConversation
from rackbook import database as logger

DAY = date(2026, 11, 5)


class CoachingEquipmentTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, RACKBOOK_DB_PATH=str(Path(self.temp.name) / 'logging.db'))
        self.env.start()
        logger.init_db()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.db = self.sessions()

        def dependency():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[main.get_db] = dependency
        self.client = TestClient(main.app)
        self.persist = patch.object(main, 'SessionLocal', self.sessions)
        self.persist.start()

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.persist.stop()
        self.db.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def test_not_set_is_unknown_in_api_and_report(self):
        body = self.client.get('/api/ai/equipment').json()
        self.assertFalse(body['configured'])
        self.assertEqual([], body['items'])
        self.assertEqual({'status': 'not_set'}, coaching.build_report(self.db, today=DAY)['available_equipment'])
        self.assertIn('barbell', [c['id'] for c in body['catalog']])

    def test_save_normalizes_order_and_duplicates_and_reaches_the_report(self):
        res = self.client.put('/api/ai/equipment', json=dict(items=['dumbbells', 'barbell', 'dumbbells'],
                                                              notes='  dumbbells to 50 lb  '))
        self.assertEqual(200, res.status_code)
        self.assertEqual(['barbell', 'dumbbells'], res.json()['items'])
        self.assertEqual('dumbbells to 50 lb', res.json()['notes'])
        block = coaching.build_report(self.db, today=DAY)['available_equipment']
        self.assertEqual('set', block['status'])
        self.assertEqual(['Barbell and plates', 'Dumbbells'], block['items'])
        self.assertEqual('dumbbells to 50 lb', block['notes'])
        self.assertTrue(block['saved_at'])
        self.assertIn(coaching_equipment.LIMITATION, coaching.build_report(self.db, today=DAY)['limitations'])

    def test_notes_alone_count_as_set(self):
        self.client.put('/api/ai/equipment', json=dict(items=[], notes='Bodyweight and a doorway bar only'))
        block = coaching.build_report(self.db, today=DAY)['available_equipment']
        self.assertEqual('set', block['status'])
        self.assertEqual([], block['items'])

    def test_empty_save_clears_back_to_not_set(self):
        self.client.put('/api/ai/equipment', json=dict(items=['barbell'], notes=''))
        res = self.client.put('/api/ai/equipment', json=dict(items=[], notes='  '))
        self.assertFalse(res.json()['configured'])
        self.assertIsNone(self.db.query(AppSetting).filter_by(key=coaching_equipment.SETTING_KEY).first())
        self.assertEqual('not_set', coaching.build_report(self.db, today=DAY)['available_equipment']['status'])

    def test_invalid_input_is_rejected_and_keeps_the_saved_list(self):
        self.client.put('/api/ai/equipment', json=dict(items=['barbell'], notes='keep'))
        unknown = self.client.put('/api/ai/equipment', json=dict(items=['barbell', 'jetpack'], notes=''))
        self.assertEqual(422, unknown.status_code)
        self.assertIn('jetpack', unknown.json()['detail'])
        long_notes = self.client.put('/api/ai/equipment', json=dict(items=['barbell'], notes='x' * 1001))
        self.assertEqual(422, long_notes.status_code)
        kept = self.client.get('/api/ai/equipment').json()
        self.assertEqual(['barbell'], kept['items'])
        self.assertEqual('keep', kept['notes'])

    def test_corrupt_or_retired_stored_value_never_breaks_the_report(self):
        self.db.add(AppSetting(key=coaching_equipment.SETTING_KEY, value='not json'))
        self.db.commit()
        self.assertEqual('not_set', coaching.build_report(self.db, today=DAY)['available_equipment']['status'])
        row = self.db.query(AppSetting).filter_by(key=coaching_equipment.SETTING_KEY).first()
        row.value = '{"items":["barbell","retired_item"],"notes":"n"}'
        self.db.commit()
        block = coaching.build_report(self.db, today=DAY)['available_equipment']
        self.assertEqual(['Barbell and plates'], block['items'])

    def test_equipment_is_frozen_with_each_conversation(self):
        self.client.put('/api/ai/equipment', json=dict(items=['barbell'], notes=''))
        evidence = coaching.build_report(self.db, today=DAY)
        saved = coaching.save_conversation(self.db, '11111111-1111-1111-1111-111111111111', evidence)
        self.client.put('/api/ai/equipment', json=dict(items=['cable'], notes=''))
        row = self.db.query(CoachingConversation).first()
        frozen = coaching.parsed(row.evidence, {})['available_equipment']
        self.assertEqual(['Barbell and plates'], frozen['items'])
        self.assertIsNotNone(saved)

    def test_brief_tells_the_coach_how_to_use_it(self):
        for phrase in ('available_equipment', 'status is not_set', 'unknown, not', 'never', 'known_movements are past movements'):
            self.assertIn(phrase, coaching.BRIEF)

    def test_saving_does_not_touch_the_logging_database(self):
        path = Path(os.environ['RACKBOOK_DB_PATH'])
        before = path.read_bytes()
        self.client.put('/api/ai/equipment', json=dict(items=['barbell'], notes='n'))
        coaching.build_report(self.db, today=DAY)
        self.assertEqual(before, path.read_bytes())
