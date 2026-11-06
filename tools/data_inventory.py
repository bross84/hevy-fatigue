"""Read-only backup inventory. Never prints settings or credential contents."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def inventory(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        # Names come only from SQLite's own schema, quoted as identifiers.
        counts={t:db.execute('SELECT COUNT(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
        out={'counts':counts,'integrity':db.execute('PRAGMA integrity_check').fetchone()[0]}
        if 'training_max_history' in tables:
            out['latest_ts']=[dict(r) for r in db.execute('''SELECT * FROM training_max_history h
                WHERE h.id=(SELECT id FROM training_max_history WHERE exercise_template_id=h.exercise_template_id ORDER BY set_at DESC,id DESC LIMIT 1)
                ORDER BY exercise_template_id''')]
        if 'mesocycles' in tables:
            out['active_plans']=[dict(r) for r in db.execute('SELECT id,revision,active FROM mesocycles WHERE active=1')]
            out['completion_links']=[dict(r) for r in db.execute('SELECT * FROM mesocycle_completions ORDER BY mesocycle_id,session_id')]
        out['trial_hashes']={}
        for table in tables:
            if table.startswith('fatigue_trial'):
                rows=[dict(r) for r in db.execute('SELECT * FROM "'+table.replace('"','""')+'"')]
                serialized=json.dumps(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)),sort_keys=True)
                out['trial_hashes'][table]=hashlib.sha256(serialized.encode()).hexdigest()
        return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('database')
    print(json.dumps(inventory(parser.parse_args().database),indent=2))
