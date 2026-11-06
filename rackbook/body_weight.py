"""
body_weight.py — Daily body measurements pulled from Hevy (which gets them from Apple Health).

Read-only against Hevy: sync_body_measurements only ever GETs. Rows are keyed by date, so a re-sync
refreshes a day Hevy has revised instead of duplicating it.
"""
from .database import get_db


def sync_body_measurements(client) -> int:
    """Page through every Hevy body measurement and upsert it by date. Returns the number of days stored.
    Days with no weight are skipped (weight is what the progress chart needs)."""
    rows: list[tuple] = []
    page = 1
    while True:
        data = client.list_body_measurements(page=page)
        for m in data.get("body_measurements", []):
            if m.get("date") and m.get("weight_kg") is not None:
                rows.append((m["date"], m["weight_kg"], m.get("lean_mass_kg"), m.get("fat_percent")))
        if page >= data.get("page_count", 1):
            break
        page += 1

    with get_db() as conn:
        conn.executemany(
            """
            INSERT INTO body_measurements (date, weight_kg, lean_mass_kg, fat_percent)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                lean_mass_kg = excluded.lean_mass_kg,
                fat_percent = excluded.fat_percent,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )
    return len(rows)


def list_body_measurements() -> list[dict]:
    """Stored measurements, oldest first."""
    with get_db() as conn:
        cur = conn.execute(
            "SELECT date, weight_kg, lean_mass_kg, fat_percent FROM body_measurements ORDER BY date"
        )
        return [dict(r) for r in cur.fetchall()]
