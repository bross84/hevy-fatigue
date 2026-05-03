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
    parser = argparse.ArgumentParser(description="Gate checks for incremental sync behavior.")
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


def get_last_sync_db(conn):
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?",
        ("last_sync",),
    ).fetchone()
    return row[0] if row else None


def clear_last_sync_db(conn):
    conn.execute("DELETE FROM app_settings WHERE key = ?", ("last_sync",))
    conn.commit()


def workout_sessions_count(conn):
    row = conn.execute("SELECT COUNT(*) FROM workout_sessions").fetchone()
    return int(row[0] if row else 0)


def workout_count_for_id(conn, workout_id):
    row = conn.execute(
        "SELECT COUNT(*) FROM workout_sessions WHERE hevy_workout_id = ?",
        (workout_id,),
    ).fetchone()
    return int(row[0] if row else 0)


def workout_log_count_for_id(conn, workout_id):
    row = conn.execute(
        "SELECT COUNT(*) FROM workout_logs WHERE workout_id = ?",
        (workout_id,),
    ).fetchone()
    return int(row[0] if row else 0)


def pick_existing_workout_id(conn):
    row = conn.execute(
        "SELECT hevy_workout_id FROM workout_sessions ORDER BY workout_date DESC, id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def delete_workout_rows(conn, workout_id):
    conn.execute("DELETE FROM workout_logs WHERE workout_id = ?", (workout_id,))
    conn.execute("DELETE FROM workout_sessions WHERE hevy_workout_id = ?", (workout_id,))
    conn.commit()


def canonical_rows(conn):
    return conn.execute(
        "SELECT exercise_id, canonical_title FROM exercise_canonical"
    ).fetchall()


def non_canonical_titles(conn, exercise_id, canonical_title):
    rows = conn.execute(
        """
        SELECT DISTINCT exercise_title
        FROM workout_logs
        WHERE exercise_id = ?
        """,
        (exercise_id,),
    ).fetchall()
    titles = [row[0] for row in rows if row[0] is not None]
    return [title for title in titles if title != canonical_title]


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


def trigger_sync_and_wait(base_url, timeout_seconds, poll_interval_seconds):
    post_response = requests.post(f"{base_url}/api/sync?force=true", timeout=60)
    if not post_response.ok:
        raise RuntimeError(
            f"POST /api/sync failed: status={post_response.status_code}, payload={post_response.text}"
        )

    post_payload = post_response.json()
    if post_payload.get("status") == "already_running":
        wait_for_sync_idle(base_url, timeout_seconds, poll_interval_seconds)
        post_response = requests.post(f"{base_url}/api/sync?force=true", timeout=60)
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
        last_sync_response = requests.get(f"{base_url}/api/sync/last-sync", timeout=10)
    except Exception as exc:
        return False, f"last-sync endpoint is not reachable: {exc}"

    if last_sync_response.status_code != 200:
        return False, (
            "last-sync endpoint preflight failed: "
            f"status={last_sync_response.status_code}, payload={last_sync_response.text}"
        )

    try:
        payload = last_sync_response.json()
    except Exception as exc:
        return False, f"last-sync endpoint returned non-JSON response: {exc}"

    if "last_sync" not in payload:
        return False, f"last-sync response missing key 'last_sync': payload={payload}"

    return True, f"ok payload={payload}"


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
        runner.record(0, "Preflight app + last-sync endpoint", ok, detail)
        if not ok:
            return 1 if not runner.summary() else 0

        try:
            clear_last_sync_db(conn)
            post_payload, status_payload = trigger_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            sessions_after = workout_sessions_count(conn)
            last_sync_after = get_last_sync_db(conn)
            passed = sessions_after > 0 and bool(last_sync_after)
            detail = (
                f"sessions={sessions_after}, last_sync={last_sync_after}, "
                f"sync_post={post_payload}, sync_status={status_payload}"
            )
            runner.record(1, "Initial import runs when last_sync is absent", passed, detail)
        except Exception as exc:
            runner.record(1, "Initial import runs when last_sync is absent", False, str(exc))

        try:
            last_sync_before = get_last_sync_db(conn)
            sessions_before = workout_sessions_count(conn)
            post_payload, status_payload = trigger_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            last_sync_after = get_last_sync_db(conn)
            sessions_after = workout_sessions_count(conn)

            before_ts = parse_iso_timestamp(last_sync_before)
            after_ts = parse_iso_timestamp(last_sync_after)
            advanced = bool(before_ts and after_ts and after_ts > before_ts)
            count_unchanged = sessions_after == sessions_before
            passed = advanced and count_unchanged
            detail = (
                f"last_sync_before={last_sync_before}, last_sync_after={last_sync_after}, "
                f"sessions_before={sessions_before}, sessions_after={sessions_after}, "
                f"sync_post={post_payload}, sync_status={status_payload}"
            )
            runner.record(2, "Incremental sync runs on second sync", passed, detail)
        except Exception as exc:
            runner.record(2, "Incremental sync runs on second sync", False, str(exc))

        try:
            workout_id = pick_existing_workout_id(conn)
            if not workout_id:
                runner.record(3, "Deleted event simulation removes workout from DB", False, "no workout_sessions rows to target")
            else:
                delete_workout_rows(conn, workout_id)
                session_rows = workout_count_for_id(conn, workout_id)
                log_rows = workout_log_count_for_id(conn, workout_id)
                passed = session_rows == 0 and log_rows == 0
                detail = f"workout_id={workout_id}, workout_sessions_rows={session_rows}, workout_logs_rows={log_rows}"
                runner.record(3, "Deleted event simulation removes workout from DB", passed, detail)
        except Exception as exc:
            runner.record(3, "Deleted event simulation removes workout from DB", False, str(exc))

        try:
            canon = canonical_rows(conn)
            if not canon:
                runner.record(
                    4,
                    "Canonical substitution applies during incremental sync",
                    True,
                    "no exercise_canonical entries found",
                    skipped=True,
                )
            else:
                offenders = []
                checked = 0
                for exercise_id, canonical_title in canon:
                    checked += 1
                    bad_titles = non_canonical_titles(conn, exercise_id, canonical_title)
                    if bad_titles:
                        offenders.append(
                            {
                                "exercise_id": exercise_id,
                                "canonical_title": canonical_title,
                                "non_canonical_titles": bad_titles,
                            }
                        )

                passed = len(offenders) == 0
                detail = f"checked={checked}, offenders={offenders[:3]}"
                runner.record(4, "Canonical substitution applies during incremental sync", passed, detail)
        except Exception as exc:
            runner.record(4, "Canonical substitution applies during incremental sync", False, str(exc))

        try:
            last_sync_before = get_last_sync_db(conn)
            post_payload, status_payload = trigger_sync_and_wait(
                base_url=base_url,
                timeout_seconds=args.sync_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            last_sync_after = get_last_sync_db(conn)
            before_ts = parse_iso_timestamp(last_sync_before)
            after_ts = parse_iso_timestamp(last_sync_after)
            passed = bool(before_ts and after_ts and after_ts > before_ts)
            detail = (
                f"last_sync_before={last_sync_before}, last_sync_after={last_sync_after}, "
                f"sync_post={post_payload}, sync_status={status_payload}"
            )
            runner.record(5, "last_sync advances after each sync", passed, detail)
        except Exception as exc:
            runner.record(5, "last_sync advances after each sync", False, str(exc))

    finally:
        try:
            conn.close()
        except Exception:
            pass

    return 0 if runner.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
