"""The app's own exercise catalog (local_exercises).

Every exercise has a local record with a local ID. hevy_id only links it to the Hevy
copy. Exercises created in the app are written here before Hevy is contacted; the
whole Hevy catalog is copied here on each exercise sync. Workouts and plans still
refer to exercises by Hevy ID until local workouts become the record (issue #145).
"""
import json
import time
import uuid


def save_created(conn, identity, body):
    """Insert or update the local record for an exercise created in the app."""
    now = time.time()
    conn.execute(
        """INSERT INTO local_exercises(id,title,exercise_type,equipment,primary_muscle,other_muscles,
               is_custom,origin,source_id,hevy_id,created_at,updated_at)
           VALUES(?,?,?,?,?,?,1,'app',?,NULL,?,?)
           ON CONFLICT(id) DO UPDATE SET title=excluded.title, exercise_type=excluded.exercise_type,
               equipment=excluded.equipment, primary_muscle=excluded.primary_muscle,
               other_muscles=excluded.other_muscles, source_id=excluded.source_id,
               updated_at=excluded.updated_at""",
        (identity, body['title'], body['exercise_type'], body['equipment_category'], body['muscle_group'],
         json.dumps(body.get('other_muscles') or []), body.get('source_id'), now, now))


def link_hevy(conn, identity, hevy_id):
    """Record the confirmed Hevy ID on a local record. A copy of the same Hevy exercise
    made by a catalog sync in the meantime is the same exercise, so it is folded in."""
    hevy_id = str(hevy_id)
    conn.execute("DELETE FROM local_exercises WHERE hevy_id=? AND id != ? AND origin='hevy'", (hevy_id, identity))
    conn.execute("UPDATE local_exercises SET hevy_id=?, updated_at=? WHERE id=?", (hevy_id, time.time(), identity))


def mirror_hevy(conn, templates):
    """Copy Hevy exercise templates into the local catalog, matched on Hevy ID.
    Local IDs, origin and creation time are never changed by a sync."""
    now = time.time()
    conn.executemany(
        """INSERT INTO local_exercises(id,title,exercise_type,equipment,primary_muscle,other_muscles,
               is_custom,origin,hevy_id,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,'hevy',?,?,?)
           ON CONFLICT(hevy_id) DO UPDATE SET title=excluded.title,
               exercise_type=COALESCE(excluded.exercise_type, exercise_type),
               equipment=COALESCE(excluded.equipment, equipment),
               primary_muscle=COALESCE(excluded.primary_muscle, primary_muscle),
               other_muscles=excluded.other_muscles,
               is_custom=COALESCE(excluded.is_custom, is_custom), updated_at=excluded.updated_at""",
        [(uuid.uuid4().hex, t['title'], t.get('type'), t.get('equipment'), t.get('primary_muscle_group'),
          json.dumps(t.get('secondary_muscle_groups') or []),
          None if t.get('is_custom') is None else int(bool(t.get('is_custom'))), str(t['id']), now, now)
         for t in templates if t.get('id') is not None and t.get('title')])


def title_taken(conn, title, except_id=None):
    """True when another local exercise already uses this name (ignoring case). Records
    from creation attempts Hevy rejected do not count: they can be edited and resent."""
    key = title.strip().casefold()
    rows = conn.execute(
        """SELECT e.id, e.title FROM local_exercises e
           LEFT JOIN exercise_creations c ON c.id = e.id
           WHERE e.origin='hevy' OR e.hevy_id IS NOT NULL OR COALESCE(c.state,'') != 'rejected'""").fetchall()
    return any(r['id'] != except_id and r['title'].strip().casefold() == key for r in rows)


def get(conn, identity):
    row = conn.execute('SELECT * FROM local_exercises WHERE id=?', (identity,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out['other_muscles'] = json.loads(out['other_muscles'] or '[]')
    out['is_custom'] = None if out['is_custom'] is None else bool(out['is_custom'])
    return out
