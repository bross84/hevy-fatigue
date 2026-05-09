import argparse
import uuid
from datetime import date

import requests
from sqlalchemy import text

from database import AppSetting, ExerciseCanonical, SessionLocal, WorkoutLog, WorkoutSession, init_db


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
BACKFILL_FLAG_KEY = "migration_canonical_title_backfill_v1"


class GateRunner:
    def __init__(self):
        self.results = []

    def record(self, gate_number, description, passed, detail):
        self.results.append((gate_number, description, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"{status} Gate {gate_number}: {description} - {detail}")

    def summary(self):
        passed = sum(1 for _, _, ok, _ in self.results if ok)
        failed = len(self.results) - passed
        print(f"SUMMARY: {passed} passed, {failed} failed")
        return failed == 0


def parse_args():
    parser = argparse.ArgumentParser(description="Gate checks for movement trend canonical aggregation behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running local app base URL")
    return parser.parse_args()


def cleanup_test_rows(exercise_id, workout_ids):
    db = SessionLocal()
    try:
        db.query(WorkoutLog).filter(WorkoutLog.exercise_id == exercise_id).delete(synchronize_session=False)
        db.query(WorkoutSession).filter(WorkoutSession.hevy_workout_id.in_(workout_ids)).delete(synchronize_session=False)
        db.query(ExerciseCanonical).filter(ExerciseCanonical.exercise_id == exercise_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def seed_historical_rows(exercise_id, workout_ids, raw_titles):
    db = SessionLocal()
    try:
        for idx, workout_id in enumerate(workout_ids):
            workout_date = date(2026, 5, 1 + (idx * 7))
            db.add(
                WorkoutSession(
                    hevy_workout_id=workout_id,
                    workout_date=workout_date,
                    workout_title="Movement Trend Gate Session",
                    verification_status="verified",
                    modality="strength",
                    modality_confidence=0.99,
                )
            )
            db.add(
                WorkoutLog(
                    date=workout_date,
                    workout_title="Movement Trend Gate Session",
                    workout_id=workout_id,
                    exercise_id=exercise_id,
                    exercise_title=raw_titles[idx],
                    set_number=1,
                    weight_lbs=225 + (idx * 10),
                    reps=5,
                    rpe=8.0,
                )
            )
        db.commit()
    finally:
        db.close()


def get_distinct_titles(exercise_id):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT exercise_title
                FROM workout_logs
                WHERE exercise_id = :exercise_id
                ORDER BY exercise_title ASC
                """
            ),
            {"exercise_id": exercise_id},
        ).fetchall()
        return [str(row[0]) for row in rows if row and row[0]]
    finally:
        db.close()


def run_backfill_migration_once():
    db = SessionLocal()
    try:
        db.query(AppSetting).filter(AppSetting.key == BACKFILL_FLAG_KEY).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    init_db()


def main():
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    runner = GateRunner()

    suffix = uuid.uuid4().hex[:8]
    exercise_id = f"mvt-gate-{suffix}"
    workout_ids = [
        f"mvt-gate-workout-a-{suffix}",
        f"mvt-gate-workout-b-{suffix}",
    ]
    raw_titles = [
        f"Barbell Squat {suffix}",
        f"Barbell  Squat {suffix}",
    ]
    canonical_title = f"Back Squat {suffix}"

    try:
        try:
            health = requests.get(f"{base_url}/", timeout=10)
            health.raise_for_status()
        except Exception as exc:
            print(f"FAIL: local app is not reachable at {base_url}: {exc}")
            return 1

        cleanup_test_rows(exercise_id, workout_ids)
        seed_historical_rows(exercise_id, workout_ids, raw_titles)

        try:
            response = requests.post(
                f"{base_url}/api/exercises/canonical",
                json={"exercise_id": exercise_id, "canonical_title": canonical_title},
                timeout=10,
            )
            payload = response.json()
            passed = (
                response.status_code == 200
                and payload.get("exercise_id") == exercise_id
                and payload.get("canonical_title") == canonical_title
            )
            detail = f"status={response.status_code}, payload={payload}"
            runner.record(1, "POST canonical mapping for movement", passed, detail)
        except Exception as exc:
            runner.record(1, "POST canonical mapping for movement", False, str(exc))

        try:
            run_backfill_migration_once()
            titles = get_distinct_titles(exercise_id)
            passed = titles == [canonical_title]
            detail = f"distinct_titles={titles}"
            runner.record(2, "One-time backfill rewrites historical titles", passed, detail)
        except Exception as exc:
            runner.record(2, "One-time backfill rewrites historical titles", False, str(exc))

        try:
            response = requests.get(
                f"{base_url}/api/movements/session-trend",
                params={"exercise_id": exercise_id, "window": "all"},
                timeout=10,
            )
            payload = response.json()
            passed = (
                response.status_code == 200
                and isinstance(payload, list)
                and len(payload) == 2
                and all(item.get("movement_title") == canonical_title for item in payload)
            )
            detail = f"status={response.status_code}, points={len(payload) if isinstance(payload, list) else 'n/a'}, payload={payload}"
            runner.record(3, "Session trend aggregates by exercise_id after backfill", passed, detail)
        except Exception as exc:
            runner.record(3, "Session trend aggregates by exercise_id after backfill", False, str(exc))

    finally:
        cleanup_test_rows(exercise_id, workout_ids)

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
