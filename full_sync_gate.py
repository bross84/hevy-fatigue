import argparse
import sqlite3
import sys
import time
from datetime import datetime

import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DB_PATH = "/data/hevy_fatigue.db"


class GateRunner:
    def __init__(self):
        self.results = []

    def record(self, gate_number, description, passed, detail, skipped=False):
        self.results.append((gate_number, description, passed, detail, skipped))
        if skipped:
            status = "SKIP"
        else:
            status = "PASS" if passed else "FAIL"
        print(f"{status} Gate {gate_number}: {description} - {detail}")

    def summary(self):
        passed = sum(1 for _, _, ok, _, skipped in self.results if ok and not skipped)
        failed = sum(1 for _, _, ok, _, skipped in self.results if not ok and not skipped)
        skipped = sum(1 for _, _, _, _, was_skipped in self.results if was_skipped)
        print(f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped")
        return failed == 0


def parse_args():
    parser = argparse.ArgumentParser(description="Gate checks for full sync behavior.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Running local app base URL")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite database path")
    parser.add_argument("--sync-timeout-seconds", type=int, default=300, help="Max time to wait for sync completion")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0, help="Polling interval for /api/sync/status")
    return parser.parse_args()


def connect_db(db_path):
    return sqlite3.connect(db_path)


def parse_iso_timestamp(raw_value):
    if not raw_value:
        return None
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))


def get_migration_flag_db(conn):
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        ("migration_incremental_sync_v1",),
    ).fetchone()
    return row[0] if row else None


def get_last_sync_db(conn):
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        ("last_sync",),
    ).fetchone()
    return row[0] if row else None


def workout_sessions_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()
    return int(row[0] if row else 0)


def workout_logs_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM workout_logs").fetchone()
    return int(row[0] if row else 0)


def daily_readiness_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM daily_readiness").fetchone()
    return int(row[0] if row else 0)


def exercise_mappings_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM exercise_mappings").fetchone()
    return int(row[0] if row else 0)


def exercise_canonical_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM exercise_canonical").fetchone()
    return int(row[0] if row else 0)


def wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds):
    deadline = time.time() + timeout_seconds
    last_payload = None

    while time.time() <= deadline:
        status_response = requests.get(f"{base_url}/api/sync/status", timeout=30)
        if not status_response.ok:
            raise RuntimeError(
                f"GET /api/sync/status failed: status={status_response.status_code}, payload={status_response.text}"
            )

        payload = status_response.json()
        last_payload = payload
        if not bool(payload.get("running", False)):
            return payload

        time.sleep(poll_interval_seconds)

    raise RuntimeError(
        f"Timed out waiting for sync completion after {timeout_seconds}s. Last status: {last_payload}"
    )


def trigger_full_sync_and_wait(base_url, timeout_seconds, poll_interval_seconds):
    post_response = requests.post(f"{base_url}/api/sync/full", timeout=60)
    if not post_response.ok:
        raise RuntimeError(
            f"POST /api/sync/full failed: status={post_response.status_code}, payload={post_response.text}"
        )

    post_payload = post_response.json()
    if post_payload.get("status") == "already_running":
        wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds)
        post_response = requests.post(f"{base_url}/api/sync/full", timeout=60)
        if not post_response.ok:
            raise RuntimeError(
                f"POST /api/sync/full retry failed: status={post_response.status_code}, payload={post_response.text}"
            )
        post_payload = post_response.json()

    status_payload = wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds)
    return post_payload, status_payload


def trigger_incremental_sync_and_wait(base_url, timeout_seconds, poll_interval_seconds):
    post_response = requests.post(f"{base_url}/api/sync", timeout=60)
    if not post_response.ok:
        raise RuntimeError(
            f"POST /api/sync failed: status={post_response.status_code}, payload={post_response.text}"
        )

    post_payload = post_response.json()
    if post_payload.get("status") == "already_running":
        wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds)
        post_response = requests.post(f"{base_url}/api/sync", timeout=60)
        if not post_response.ok:
            raise RuntimeError(
                f"POST /api/sync retry failed: status={post_response.status_code}, payload={post_response.text}"
            )
        post_payload = post_response.json()

    status_payload = wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds)
    return post_payload, status_payload


def preflight(base_url):
    try:
        root_response = requests.get(f"{base_url}/", timeout=10)
        root_response.raise_for_status()
    except Exception as exc:
        return False, f"local app is not reachable at {base_url}: {exc}"

    try:
        status_response = requests.get(f"{base_url}/api/sync/status", timeout=10)
    except Exception as exc:
        return False, f"sync/status endpoint is not reachable: {exc}"

    if status_response.status_code != 200:
        return False, (
            "sync/status endpoint preflight failed: "
            f"status={status_response.status_code}, payload={status_response.text}"
        )

    return True, "ok"


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
        ok, detail = preflight(base_url)
        runner.record(0, "Preflight app + sync/status endpoint", ok, detail)
        if not ok:
            return 1 if not runner.summary() else 0

        # Capture baseline counts before full sync
        baseline_readiness = daily_readiness_count(conn)
        baseline_mappings = exercise_mappings_count(conn)
        baseline_canonical = exercise_canonical_count(conn)
        baseline_sessions = workout_sessions_count(conn)
        baseline_logs = workout_logs_count(conn)

        print(f"\n[Baseline] daily_readiness={baseline_readiness}, exercise_mappings={baseline_mappings}, "
              f"exercise_canonical={baseline_canonical}, workout_sessions={baseline_sessions}, workout_logs={baseline_logs}\n")

        # Gate 1: Trigger full sync and verify completion
        try:
            post_payload, status_payload = trigger_full_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            passed = post_payload.get("status") == "complete"
            detail = f"post={post_payload}, status={status_payload}"
            runner.record(1, "Full sync completes successfully", passed, detail)
        except Exception as exc:
            runner.record(1, "Full sync completes successfully", False, str(exc))

        # Gate 2: Sync flag cleared
        try:
            flag_cleared = get_migration_flag_db(conn) is None
            detail = f"migration_incremental_sync_v1={get_migration_flag_db(conn)}"
            runner.record(2, "Sync flag (migration_incremental_sync_v1) cleared", flag_cleared, detail)
        except Exception as exc:
            runner.record(2, "Sync flag (migration_incremental_sync_v1) cleared", False, str(exc))

        # Gate 3: last_sync cleared (no value present, so next sync is full import)
        try:
            last_sync_cleared = get_last_sync_db(conn) is None
            detail = f"last_sync={get_last_sync_db(conn)}"
            runner.record(3, "last_sync timestamp cleared", last_sync_cleared, detail)
        except Exception as exc:
            runner.record(3, "last_sync timestamp cleared", False, str(exc))

        # Gate 4: Data reimported (workout_sessions > 0)
        try:
            sessions_after = workout_sessions_count(conn)
            logs_after = workout_logs_count(conn)
            passed = sessions_after > 0 and logs_after > 0
            detail = f"workout_sessions={sessions_after}, workout_logs={logs_after} (baseline: sessions={baseline_sessions}, logs={baseline_logs})"
            runner.record(4, "Data reimported (workout_sessions and logs > 0)", passed, detail)
        except Exception as exc:
            runner.record(4, "Data reimported (workout_sessions and logs > 0)", False, str(exc))

        # Gate 5: Check-in data preserved (daily_readiness count unchanged)
        try:
            readiness_after = daily_readiness_count(conn)
            passed = readiness_after == baseline_readiness
            detail = f"baseline={baseline_readiness}, after={readiness_after}"
            runner.record(5, "Check-in data preserved (daily_readiness count unchanged)", passed, detail)
        except Exception as exc:
            runner.record(5, "Check-in data preserved (daily_readiness count unchanged)", False, str(exc))

        # Gate 6: Exercise mappings preserved
        try:
            mappings_after = exercise_mappings_count(conn)
            passed = mappings_after == baseline_mappings
            detail = f"baseline={baseline_mappings}, after={mappings_after}"
            runner.record(6, "Exercise mappings preserved (count unchanged)", passed, detail)
        except Exception as exc:
            runner.record(6, "Exercise mappings preserved (count unchanged)", False, str(exc))

        # Gate 7: Exercise canonical preserved
        try:
            canonical_after = exercise_canonical_count(conn)
            passed = canonical_after == baseline_canonical
            detail = f"baseline={baseline_canonical}, after={canonical_after}"
            runner.record(7, "Exercise canonical titles preserved (count unchanged)", passed, detail)
        except Exception as exc:
            runner.record(7, "Exercise canonical titles preserved (count unchanged)", False, str(exc))

        # Gate 8: Incremental sync works after full sync
        try:
            last_sync_before_incr = get_last_sync_db(conn)
            post_payload, status_payload = trigger_incremental_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            last_sync_after_incr = get_last_sync_db(conn)
            
            before_ts = parse_iso_timestamp(last_sync_before_incr)
            after_ts = parse_iso_timestamp(last_sync_after_incr)
            passed = bool(before_ts and after_ts and after_ts > before_ts)
            detail = f"last_sync_before={last_sync_before_incr}, last_sync_after={last_sync_after_incr}"
            runner.record(8, "Incremental sync works after full sync (last_sync advances)", passed, detail)
        except Exception as exc:
            runner.record(8, "Incremental sync works after full sync (last_sync advances)", False, str(exc))

        # Gate 9: Confirmation dialog blocks execution (manual check)
        runner.record(
            9,
            "Confirmation dialog prevents unintended full sync",
            True,
            "UI cancel path tested manually or via browser automation — skipping automated check",
            skipped=True,
        )

        # Gate 10: Both buttons disabled during sync
        runner.record(
            10,
            "Both sync buttons disabled during any active sync",
            True,
            "Verified in UI code: _setSyncButtonsDisabled() manages both buttons — skipping active-sync automated check",
            skipped=True,
        )

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
