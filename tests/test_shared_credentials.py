"""Shared credentials use the host store only; all values below are test fakes."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import credentials
from database import Base,AppSetting
from rackbook import hevy_client as training_client
from rackbook.database import init_db,get_db


class SharedCredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'host.db'))
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session=sessionmaker(bind=self.engine)
        for target,value in [('SessionLocal',self.session),('_FERNET_KEY_PATH',str(Path(self.tmp.name)/'app.key')),('_fernet',None)]:
            mock=patch.object(credentials,target,value);mock.start();self.addCleanup(mock.stop)
        env=patch.dict(os.environ,RACKBOOK_DB_PATH=str(Path(self.tmp.name)/'rack.db'));env.start();self.addCleanup(env.stop)
        init_db()

    def test_logging_uses_host_encrypted_credential_and_leaves_old_rows_inactive(self):
        with get_db() as db:db.execute("INSERT INTO app_settings(key,value) VALUES ('hevy_api_key','inactive-old-logging-value')")
        training_client.save_api_key('fake-host-credential')
        self.assertEqual(training_client.HevyClient().api_key,'fake-host-credential')
        with self.session() as db:
            value=db.query(AppSetting).filter_by(key='hevy_api_key').one().value
            self.assertNotEqual(value,'fake-host-credential')
            self.assertEqual(credentials.get_db_api_key(db),'fake-host-credential')
        with get_db() as db:
            self.assertEqual(db.execute("SELECT value FROM app_settings WHERE key='hevy_api_key'").fetchone()[0],'inactive-old-logging-value')

    def test_original_plaintext_migration_and_file_environment_fallback(self):
        with self.session() as db:
            db.add(AppSetting(key='hevy_api_key',value='fake-legacy-key'));db.commit()
            self.assertEqual(credentials.get_db_api_key(db),'fake-legacy-key')
            self.assertNotEqual(db.query(AppSetting).one().value,'fake-legacy-key')
            db.query(AppSetting).delete();db.commit()
        with patch('hevy_client._load_api_key',return_value='fake-fallback'):
            self.assertEqual(training_client.HevyClient().api_key,'fake-fallback')
