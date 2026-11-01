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
                main.trigger_sync(db=db)
                failed = bool((main._sync_status.get('last_result') or {}).get('error'))
                visible = db.query(WorkoutSession).filter_by(hevy_workout_id=workout_id).first()
                from rackbook.workout_saves import monitoring_status
                monitoring_status(workout_id, 'failed' if failed else 'complete' if visible else 'pending')
            except Exception as exc:
                from rackbook.workout_saves import monitoring_status
                try:
                    monitoring_status(workout_id, 'pending' if getattr(exc,'status_code',None)==409 else 'failed')
                except Exception:
                    pass
    threading.Thread(target=refresh, daemon=True).start()
    return 'pending'
