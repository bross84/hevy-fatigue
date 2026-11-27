"""Host adapters; logging never imports monitoring calculation internals."""
import threading

_host_started = False


def enable():
    global _host_started
    _host_started = True


def monitoring_visible(workout_id):
    """A later normal/manual sync may have imported a previously delayed save."""
    if not _host_started or not workout_id:
        return False
    from database import SessionLocal, WorkoutSession
    with SessionLocal() as db:
        return db.query(WorkoutSession).filter_by(hevy_workout_id=workout_id).first() is not None


def request_monitoring_refresh(workout_id):
    # The usual host entry point owns locking, credential resolution and imports.
    # A delayed Hevy result stays pending; this adapter never posts a workout.
    if not _host_started:
        return 'pending'
    from database import SessionLocal, WorkoutSession
    import main
    if not main._sync_lock.acquire(blocking=False):
        return 'pending'
    main._sync_lock.release()
    def refresh():
        with SessionLocal() as db:
            try:
                # Use this run's own outcome (#148). If another sync grabbed the lock
                # first, its result is not ours: stay pending for a later sync to settle.
                outcome = main.run_incremental_sync(db)
                from rackbook.workout_saves import monitoring_status
                if outcome.get('status') == 'already_running':
                    monitoring_status(workout_id, 'pending')
                    return
                failed = outcome.get('status') == 'failed' or bool((outcome.get('result') or {}).get('error'))
                visible = db.query(WorkoutSession).filter_by(hevy_workout_id=workout_id).first()
                if visible:
                    # The session may have been imported before the save finished locally (#199).
                    from importer import _fill_srpe_from_log
                    _fill_srpe_from_log(db, workout_id)
                    db.commit()
                monitoring_status(workout_id, 'failed' if failed else 'complete' if visible else 'pending')
            except Exception as exc:
                from rackbook.workout_saves import monitoring_status
                try:
                    monitoring_status(workout_id, 'pending' if getattr(exc,'status_code',None)==409 else 'failed')
                except Exception:
                    pass
    threading.Thread(target=refresh, daemon=True).start()
    return 'pending'
