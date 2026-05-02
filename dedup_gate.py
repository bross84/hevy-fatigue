import argparse
import sqlite3
import sys
import time

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DB_PATH = "/data/hevy_fatigue.db"


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
    parser = argparse.ArgumentParser(description="Gate checks for workout_logs dedup + unique-index protections.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running local app base URL")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument("--sync-timeout-seconds", type=int, default=300, help="Max time to wait for sync completion")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0, help="Polling interval for /api/sync/status")
    return parser.parse_args()


def connect_db(db_path):
    return sqlite3.connect(db_path)


def index_exists(conn, index_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name = ?",
        (index_name,),
    ).fetchone()
    return row is not None


def duplicate_group_count(conn):
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM (
          SELECT workout_id, exercise_id, set_number
          FROM workout_logs
          GROUP BY workout_id, exercise_id, set_number
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()
    return int(row[0] if row else 0)


def workout_log_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM workout_logs").fetchone()
    return int(row[0] if row else 0)


def trigger_sync_and_wait(base_url, timeout_seconds, poll_interval_seconds):
    post_response = requests.post(f"{base_url}/api/sync", timeout=30)
    post_payload = post_response.json()

    if not post_response.ok:
        raise RuntimeError(f"POST /api/sync failed: status={post_response.status_code}, payload={post_payload}")

    deadline = time.time() + timeout_seconds
    last_status_payload = None

    while time.time() <= deadline:
        status_response = requests.get(f"{base_url}/api/sync/status", timeout=30)
        status_payload = status_response.json()
        if not status_response.ok:
            raise RuntimeError(
                f"GET /api/sync/status failed: status={status_response.status_code}, payload={status_payload}"
            )

        last_status_payload = status_payload
        if not bool(status_payload.get("running", False)):
            return post_payload, status_payload

        time.sleep(poll_interval_seconds)

    raise RuntimeError(
        f"Timed out waiting for sync completion after {timeout_seconds}s. Last status: {last_status_payload}"
    )


def main():
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    runner = GateRunner()

    try:
        conn = connect_db(args.db_path)
    except Exception as exc:
        print(f"FAIL: could not open database at {args.db_path}: {exc}")
        return 1

    try:
        try:
            has_index = index_exists(conn, "uq_workout_logs_set")
            runner.record(1, "Unique index uq_workout_logs_set exists", has_index, f"exists={has_index}")
        except Exception as exc:
            runner.record(1, "Unique index uq_workout_logs_set exists", False, str(exc))

        try:
            dup_count = duplicate_group_count(conn)
            passed = dup_count == 0
            detail = "duplicate_groups=0" if passed else f"duplicate_groups={dup_count}"
            runner.record(2, "No duplicate natural-key rows", passed, detail)
        except Exception as exc:
            runner.record(2, "No duplicate natural-key rows", False, str(exc))

        try:
            before_count = workout_log_count(conn)
            post_payload, status_payload = trigger_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )

            # Read with a fresh connection after sync to avoid stale state.
            conn.close()
            conn = connect_db(args.db_path)
            after_count = workout_log_count(conn)
            delta = after_count - before_count
            passed = delta <= 10
            detail = (
                f"before={before_count}, after={after_count}, delta={delta}, "
                f"sync_post={post_payload}, sync_status={status_payload}"
            )
            runner.record(3, "Sync does not re-add existing rows", passed, detail)
        except Exception as exc:
            runner.record(3, "Sync does not re-add existing rows", False, str(exc))

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
