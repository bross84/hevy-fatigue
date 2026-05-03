import argparse
import contextlib
import io
import uuid

import requests
from sqlalchemy import text

import importer
from database import SessionLocal


DEFAULT_BASE_URL = "http://127.0.0.1:8000"

OLD_TITLE = "Test Exercise Old Name"
NEW_TITLE = "Test Exercise New Name"
CANONICAL_TITLE = "Test Exercise Canonical"
SECOND_CONFLICT_HEVY_TITLE = "Test Exercise Dismiss Name"
SECOND_CONFLICT_STORED_TITLE = "Test Exercise Dismiss Stored"
POST_RESOLVE_DIFFERENT_TITLE = "Test Exercise Another Name"


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
    parser = argparse.ArgumentParser(description="Gate checks for exercise conflict detection queue behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running local app base URL")
    return parser.parse_args()


def cleanup_test_rows(test_exercise_id, test_workout_id, test_exercise_id_2):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                DELETE FROM workout_logs
                WHERE workout_id = :workout_id
                   OR exercise_id IN (:exercise_id_1, :exercise_id_2)
                """
            ),
            {
                "workout_id": test_workout_id,
                "exercise_id_1": test_exercise_id,
                "exercise_id_2": test_exercise_id_2,
            },
        )
        db.execute(
            text(
                """
                DELETE FROM workout_sessions
                WHERE hevy_workout_id = :workout_id
                """
            ),
            {"workout_id": test_workout_id},
        )
        with contextlib.suppress(Exception):
            db.execute(
                text(
                    """
                    DELETE FROM exercise_conflicts
                    WHERE exercise_id IN (:exercise_id_1, :exercise_id_2)
                    """
                ),
                {
                    "exercise_id_1": test_exercise_id,
                    "exercise_id_2": test_exercise_id_2,
                },
            )
        db.execute(
            text(
                """
                DELETE FROM exercise_canonical
                WHERE exercise_id IN (:exercise_id_1, :exercise_id_2)
                """
            ),
            {
                "exercise_id_1": test_exercise_id,
                "exercise_id_2": test_exercise_id_2,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def preflight(base_url):
    try:
        health = requests.get(f"{base_url}/", timeout=10)
        health.raise_for_status()
    except Exception as exc:
        return False, f"local app is not reachable at {base_url}: {exc}"

    try:
        conflicts_response = requests.get(f"{base_url}/api/exercises/conflicts", timeout=10)
    except Exception as exc:
        return False, f"conflicts endpoint is not reachable: {exc}"

    if conflicts_response.status_code != 200:
        payload = None
        with contextlib.suppress(Exception):
            payload = conflicts_response.json()
        return False, (
            "conflicts endpoint preflight failed: "
            f"status={conflicts_response.status_code}, payload={payload}"
        )

    db = SessionLocal()
    try:
        table_exists = db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='exercise_conflicts'")
        ).first()
        if not table_exists:
            return False, "exercise_conflicts table is missing"

        col_rows = db.execute(text("PRAGMA table_info(exercise_conflicts)")).fetchall()
        col_names = {row[1] for row in col_rows}
        required = {"exercise_id", "hevy_title", "stored_title", "detected_at", "resolved", "resolved_at"}
        missing = sorted(required - col_names)
        if missing:
            return False, f"exercise_conflicts is missing required columns: {missing}"
    finally:
        db.close()

    return True, "ok"


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
                        "title": "Conflict Gate Workout",
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
            return importer.import_hevy_data(api_key="conflict-gate")
    finally:
        importer.HevyClient = original_client


def seed_old_workout_row(test_exercise_id, test_workout_id):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                INSERT INTO workout_logs (
                    date,
                    workout_title,
                    exercise_title,
                    set_number,
                    workout_id,
                    exercise_id,
                    notes,
                    weight_lbs,
                    reps,
                    rpe,
                    rir,
                    estimated_1rm,
                    is_conditioning
                ) VALUES (
                    :date,
                    :workout_title,
                    :exercise_title,
                    :set_number,
                    :workout_id,
                    :exercise_id,
                    :notes,
                    :weight_lbs,
                    :reps,
                    :rpe,
                    :rir,
                    :estimated_1rm,
                    :is_conditioning
                )
                """
            ),
            {
                "date": "2026-05-02",
                "workout_title": "Conflict Gate Seed",
                "exercise_title": OLD_TITLE,
                "set_number": 1,
                "workout_id": test_workout_id,
                "exercise_id": test_exercise_id,
                "notes": None,
                "weight_lbs": 100.0,
                "reps": 5,
                "rpe": 8.0,
                "rir": None,
                "estimated_1rm": 120.0,
                "is_conditioning": 0,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fetch_conflict_row(exercise_id):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT exercise_id, hevy_title, stored_title, detected_at, resolved, resolved_at
                FROM exercise_conflicts
                WHERE exercise_id = :exercise_id
                """
            ),
            {"exercise_id": exercise_id},
        ).first()
        return row
    finally:
        db.close()


def fetch_latest_workout_title(exercise_id, workout_id):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT exercise_title
                FROM workout_logs
                WHERE exercise_id = :exercise_id
                  AND workout_id = :workout_id
                ORDER BY date DESC, id DESC
                LIMIT 1
                """
            ),
            {"exercise_id": exercise_id, "workout_id": workout_id},
        ).first()
        return row[0] if row else None
    finally:
        db.close()


def unresolved_conflict_count(exercise_id):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM exercise_conflicts
                WHERE exercise_id = :exercise_id
                  AND resolved = 0
                """
            ),
            {"exercise_id": exercise_id},
        ).first()
        return int(row[0] if row else 0)
    finally:
        db.close()


def canonical_exists(exercise_id, expected_title=None):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT canonical_title
                FROM exercise_canonical
                WHERE exercise_id = :exercise_id
                """
            ),
            {"exercise_id": exercise_id},
        ).first()
        if not row:
            return False
        if expected_title is None:
            return True
        return row[0] == expected_title
    finally:
        db.close()


def insert_unresolved_conflict(exercise_id, hevy_title, stored_title):
    db = SessionLocal()
    try:
        now = "2026-05-02 10:00:00"
        db.execute(
            text(
                """
                INSERT INTO exercise_conflicts (
                    exercise_id,
                    hevy_title,
                    stored_title,
                    detected_at,
                    resolved,
                    resolved_at
                ) VALUES (
                    :exercise_id,
                    :hevy_title,
                    :stored_title,
                    :detected_at,
                    :resolved,
                    :resolved_at
                )
                """
            ),
            {
                "exercise_id": exercise_id,
                "hevy_title": hevy_title,
                "stored_title": stored_title,
                "detected_at": now,
                "resolved": 0,
                "resolved_at": None,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def conflict_present_in_get_list(base_url, exercise_id):
    response = requests.get(f"{base_url}/api/exercises/conflicts", timeout=10)
    payload = response.json()
    if not response.ok:
        raise RuntimeError(f"GET /api/exercises/conflicts failed: status={response.status_code}, payload={payload}")
    found = next((row for row in payload if row.get("exercise_id") == exercise_id), None)
    return found, payload


def main():
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    runner = GateRunner()

    suffix = uuid.uuid4().hex
    test_exercise_id = f"conflict-gate-ex-{suffix}"
    test_workout_id = f"conflict-gate-workout-{suffix}"
    test_exercise_id_2 = f"conflict-gate-ex2-{suffix}"

    try:
        cleanup_test_rows(test_exercise_id, test_workout_id, test_exercise_id_2)

        ok, detail = preflight(base_url)
        if not ok:
            print(f"FAIL Preflight: {detail}")
            return 1

        try:
            seed_old_workout_row(test_exercise_id, test_workout_id)
            import_result = simulate_import(test_exercise_id, test_workout_id, NEW_TITLE)
            row = fetch_conflict_row(test_exercise_id)
            passed = (
                row is not None
                and row[0] == test_exercise_id
                and row[1] == NEW_TITLE
                and row[2] == OLD_TITLE
            )
            runner.record(
                1,
                "Conflict detected on sync",
                passed,
                f"import_result={import_result}, conflict_row={row}",
            )
        except Exception as exc:
            runner.record(1, "Conflict detected on sync", False, str(exc))

        try:
            latest_title = fetch_latest_workout_title(test_exercise_id, test_workout_id)
            passed = latest_title == NEW_TITLE
            runner.record(
                2,
                "Newest title wins in workout_logs",
                passed,
                f"latest_title={latest_title}",
            )
        except Exception as exc:
            runner.record(2, "Newest title wins in workout_logs", False, str(exc))

        try:
            row, payload = conflict_present_in_get_list(base_url, test_exercise_id)
            passed = row is not None
            runner.record(
                3,
                "GET /api/exercises/conflicts returns conflict",
                passed,
                f"row={row}",
            )
        except Exception as exc:
            runner.record(3, "GET /api/exercises/conflicts returns conflict", False, str(exc))

        try:
            response = requests.post(
                f"{base_url}/api/exercises/conflicts/{test_exercise_id}/resolve",
                json={"canonical_title": CANONICAL_TITLE},
                timeout=10,
            )
            payload = response.json()
            row = fetch_conflict_row(test_exercise_id)
            canonical_ok = canonical_exists(test_exercise_id, CANONICAL_TITLE)
            resolved_ok = row is not None and int(row[4] or 0) == 1 and row[5] is not None
            passed = response.ok and canonical_ok and resolved_ok
            runner.record(
                4,
                "Resolve conflict",
                passed,
                f"status={response.status_code}, payload={payload}, conflict_row={row}, canonical_ok={canonical_ok}",
            )
        except Exception as exc:
            runner.record(4, "Resolve conflict", False, str(exc))

        try:
            row, payload = conflict_present_in_get_list(base_url, test_exercise_id)
            passed = row is None
            runner.record(
                5,
                "Resolved conflict absent from GET",
                passed,
                f"row={row}",
            )
        except Exception as exc:
            runner.record(5, "Resolved conflict absent from GET", False, str(exc))

        try:
            import_result = simulate_import(test_exercise_id, test_workout_id, POST_RESOLVE_DIFFERENT_TITLE)
            count = unresolved_conflict_count(test_exercise_id)
            passed = count == 0
            runner.record(
                6,
                "No new conflict after resolve",
                passed,
                f"import_result={import_result}, unresolved_count={count}",
            )
        except Exception as exc:
            runner.record(6, "No new conflict after resolve", False, str(exc))

        try:
            insert_unresolved_conflict(test_exercise_id_2, SECOND_CONFLICT_HEVY_TITLE, SECOND_CONFLICT_STORED_TITLE)
            response = requests.post(
                f"{base_url}/api/exercises/conflicts/{test_exercise_id_2}/dismiss",
                timeout=10,
            )
            payload = response.json()
            row = fetch_conflict_row(test_exercise_id_2)
            no_canonical = not canonical_exists(test_exercise_id_2)
            resolved_ok = row is not None and int(row[4] or 0) == 1 and row[5] is not None
            passed = response.ok and resolved_ok and no_canonical
            runner.record(
                7,
                "Dismiss path",
                passed,
                f"status={response.status_code}, payload={payload}, conflict_row={row}, no_canonical={no_canonical}",
            )
        except Exception as exc:
            runner.record(7, "Dismiss path", False, str(exc))

    finally:
        cleanup_test_rows(test_exercise_id, test_workout_id, test_exercise_id_2)

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
