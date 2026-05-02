import argparse
import contextlib
import io
import sys
import uuid

import requests

import importer
from database import ExerciseCanonical, SessionLocal, WorkoutLog, WorkoutSession


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


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
    parser = argparse.ArgumentParser(description="Gate checks for canonical exercise title behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running local app base URL")
    return parser.parse_args()


def cleanup_test_rows(exercise_id, workout_id):
    db = SessionLocal()
    try:
        db.query(WorkoutLog).filter(WorkoutLog.workout_id == workout_id).delete(synchronize_session=False)
        db.query(WorkoutSession).filter(WorkoutSession.hevy_workout_id == workout_id).delete(synchronize_session=False)
        db.query(ExerciseCanonical).filter(ExerciseCanonical.exercise_id == exercise_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def fetch_canonical_rows(base_url):
    response = requests.get(f"{base_url}/api/exercises/canonical", timeout=10)
    payload = response.json()
    return response, payload


def simulate_import(exercise_id, workout_id, api_title):
    class FakeHevyClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def test_connection(self):
            return True

        def get_workouts(self, page=1):
            if page != 1:
                return {"workouts": [], "page_count": 1}
            return {
                "workouts": [
                    {
                        "id": workout_id,
                        "title": "Canonical Gate Workout",
                        "start_time": "2026-05-02T10:00:00Z",
                        "end_time": "2026-05-02T11:00:00Z",
                        "exercises": [
                            {
                                "title": api_title,
                                "exercise_template_id": exercise_id,
                                "sets": [
                                    {
                                        "type": "normal",
                                        "index": 1,
                                        "weight_kg": 100,
                                        "reps": 5,
                                        "rpe": 8,
                                        "rir": None,
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "page_count": 1,
            }

    original_client = importer.HevyClient
    importer.HevyClient = FakeHevyClient
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return importer.import_hevy_data(api_key="canonical-gate")
    finally:
        importer.HevyClient = original_client


def get_stored_workout_title(workout_id):
    db = SessionLocal()
    try:
        row = db.query(WorkoutLog).filter(WorkoutLog.workout_id == workout_id).first()
        return row.exercise_title if row else None
    finally:
        db.close()


def main():
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    runner = GateRunner()

    suffix = uuid.uuid4().hex[:8]
    exercise_id = f"canonical-gate-{suffix}"
    workout_id = f"canonical-gate-workout-{suffix}"
    initial_title = f"Canonical Gate Title {suffix}"
    updated_title = f"Canonical Gate Updated {suffix}"
    api_title = f"Hevy API Gate Title {suffix}"

    try:
        try:
            health = requests.get(f"{base_url}/", timeout=10)
            health.raise_for_status()
        except Exception as exc:
            print(f"FAIL: local app is not reachable at {base_url}: {exc}")
            return 1

        cleanup_test_rows(exercise_id, workout_id)

        try:
            response = requests.post(
                f"{base_url}/api/exercises/canonical",
                json={"exercise_id": exercise_id, "canonical_title": initial_title},
                timeout=10,
            )
            payload = response.json()
            passed = (
                response.status_code == 200
                and payload.get("exercise_id") == exercise_id
                and payload.get("canonical_title") == initial_title
            )
            detail = f"status={response.status_code}, payload={payload}"
            runner.record(1, "POST create canonical row", passed, detail)
        except Exception as exc:
            runner.record(1, "POST create canonical row", False, str(exc))

        try:
            response, payload = fetch_canonical_rows(base_url)
            row = next((item for item in payload if item.get("exercise_id") == exercise_id), None)
            passed = response.status_code == 200 and row is not None and row.get("canonical_title") == initial_title
            detail = f"status={response.status_code}, row={row}"
            runner.record(2, "GET list contains created row", passed, detail)
        except Exception as exc:
            runner.record(2, "GET list contains created row", False, str(exc))

        try:
            result = simulate_import(exercise_id, workout_id, api_title)
            stored_title = get_stored_workout_title(workout_id)
            passed = result.get("new_sets", 0) >= 1 and stored_title == initial_title
            detail = f"import_result={result}, stored_title={stored_title}, api_title={api_title}"
            runner.record(3, "Simulated import stores canonical title", passed, detail)
        except Exception as exc:
            runner.record(3, "Simulated import stores canonical title", False, str(exc))

        try:
            response = requests.post(
                f"{base_url}/api/exercises/canonical",
                json={"exercise_id": exercise_id, "canonical_title": updated_title},
                timeout=10,
            )
            payload = response.json()
            result = simulate_import(exercise_id, workout_id, api_title)
            stored_title = get_stored_workout_title(workout_id)
            passed = (
                response.status_code == 200
                and payload.get("canonical_title") == updated_title
                and stored_title == updated_title
                and result.get("new_sets", 0) >= 1
            )
            detail = f"status={response.status_code}, payload={payload}, stored_title={stored_title}"
            runner.record(4, "POST upsert updates canonical row", passed, detail)
        except Exception as exc:
            runner.record(4, "POST upsert updates canonical row", False, str(exc))

        try:
            response = requests.delete(f"{base_url}/api/exercises/canonical/{exercise_id}", timeout=10)
            payload = response.json()
            passed = response.status_code == 200 and payload == {"deleted": True}
            detail = f"status={response.status_code}, payload={payload}"
            runner.record(5, "DELETE removes canonical row", passed, detail)
        except Exception as exc:
            runner.record(5, "DELETE removes canonical row", False, str(exc))

        try:
            response, payload = fetch_canonical_rows(base_url)
            row = next((item for item in payload if item.get("exercise_id") == exercise_id), None)
            passed = response.status_code == 200 and row is None
            detail = f"status={response.status_code}, row={row}"
            runner.record(6, "GET list omits deleted row", passed, detail)
        except Exception as exc:
            runner.record(6, "GET list omits deleted row", False, str(exc))

    finally:
        cleanup_test_rows(exercise_id, workout_id)

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())