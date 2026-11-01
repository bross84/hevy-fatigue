import os

import httpx
from .database import get_db

_BASE_URL = "https://api.hevyapp.com/v1"
from credentials import get_api_key, save_api_key


class WorkoutNotSent(ValueError):
    """A local preflight check prevented any remote workout request."""


class HevyClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key()

    def _headers(self) -> dict:
        if not self.api_key:
            raise ValueError("No Hevy API key configured.")
        return {"api-key": self.api_key}

    def sync_exercise_cache(self) -> int:
        """Fetch all exercise templates from Hevy and upsert into hevy_exercise_cache."""
        exercises: list[dict] = []
        page = 1
        with httpx.Client(timeout=30) as client:
            while True:
                resp = client.get(
                    f"{_BASE_URL}/exercise_templates",
                    headers=self._headers(),
                    params={"page": page, "pageSize": 100},
                )
                resp.raise_for_status()
                data = resp.json()
                exercises.extend(data.get("exercise_templates", []))
                if page >= data.get("page_count", 1):
                    break
                page += 1

        with get_db() as conn:
            conn.executemany(
                """
                INSERT INTO hevy_exercise_cache (id, title, primary_muscle)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    primary_muscle = excluded.primary_muscle,
                    cached_at = CURRENT_TIMESTAMP
                """,
                [
                    (e["id"], e["title"], e.get("primary_muscle_group"))
                    for e in exercises
                ],
            )

        return len(exercises)

    def list_workouts(self, page: int = 1, page_size: int = 10) -> dict:
        """Fetch one page of the account's workouts. Raises on HTTP or network errors."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE_URL}/workouts",
                headers=self._headers(),
                params={"page": page, "pageSize": page_size},
            )
            resp.raise_for_status()
            return resp.json()

    def list_body_measurements(self, page: int = 1, page_size: int = 10) -> dict:
        """Fetch one page of daily body measurements, newest first. Raises on HTTP or network errors."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE_URL}/body_measurements",
                headers=self._headers(),
                params={"page": page, "pageSize": page_size},
            )
            resp.raise_for_status()
            return resp.json()

    def exercise_history(self,exercise_template_id: str) -> list[dict]:
        """Every logged set for one exercise across all sessions, newest first. Raises on HTTP or network errors."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{_BASE_URL}/exercise_history/{exercise_template_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json().get("exercise_history") or []

    def get_workout(self, workout_id: str) -> dict:
        """Read one saved workout by ID. Never modifies Hevy."""
        from urllib.parse import quote
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{_BASE_URL}/workouts/{quote(workout_id, safe='')}", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data.get("workout", data)

    def create_workout(self, body: dict) -> dict:
        """Create a workout in Hevy and return it. Raises on HTTP or network errors.
        Hevy answers 201 with {"workout": [<workout>]} (a single-element list)."""
        if os.environ.get('HEVY_WRITES_ENABLED', '0') != '1' or os.environ.get('RACKBOOK_READ_ONLY_PREVIEW') == '1':
            raise WorkoutNotSent('Hevy writes are disabled. Enable HEVY_WRITES_ENABLED only at controlled cutover.')
        if not self.api_key:
            raise WorkoutNotSent('Configure the Hevy credential in Settings before saving.')
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{_BASE_URL}/workouts", headers=self._headers(), json=body)
            resp.raise_for_status()
            created = resp.json().get("workout")
        if isinstance(created, list):
            created = created[0] if created else {}
        return created or {}
