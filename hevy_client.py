import os

import requests
from dotenv import load_dotenv

# Load .env for local development (no-op if file doesn't exist)
load_dotenv()

_KEY_FILE = os.getenv("HEVY_API_KEY_FILE", "/data/hevy_api_key")

def _load_api_key() -> str | None:
    """
    Resolution order:
      1. Key file at HEVY_API_KEY_FILE (default /data/hevy_api_key) — used in Docker
      2. HEVY_API_KEY environment variable — used for local development
    """
    try:
        with open(_KEY_FILE) as fh:
            key = fh.read().strip()
            if key:
                return key
    except FileNotFoundError:
        pass
    return os.getenv("HEVY_API_KEY")

class HevyClient:
    def __init__(self, api_key: str | None = None):
        # Caller can inject the key directly (e.g. read from the settings DB).
        # Falls back to file → env var for local dev.
        self.api_key = api_key or _load_api_key()
        self.base_url = "https://api.hevyapp.com/v1"
        self.headers = {"api-key": self.api_key} if self.api_key else {}
        self.session = requests.Session()
        if self.headers:
            self.session.headers.update(self.headers)

    def test_connection(self):
        """Simple check to see if the API key is valid."""
        if not self.api_key:
            print("❌ Connection failed. No Hevy API key is configured.")
            return False
        url = f"{self.base_url}/workouts?page=1"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                print("✅ Connected to Hevy successfully")
                return True
            else:
                print(f"❌ Connection failed. Status: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return False

    def get_workouts(self, page=1):
        """Fetch one page of workouts from the Hevy API."""
        if not self.api_key:
            raise ValueError("No Hevy API key is configured.")
        url = f"{self.base_url}/workouts?page={page}"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_workout_events(self, since: str, page: int = 1, page_size: int = 10) -> dict:
        """
        Fetch paginated workout events (updates and deletes) since a given timestamp.

        Args:
            since: ISO 8601 timestamp string - only events after this time are returned
            page: Page number (default: 1)
            page_size: Number of items per page (max 10, default: 10)

        Returns:
            dict: { page, page_count, events: [...] }
            Each event is either:
              { type: "updated", workout: { id, title, exercises, ... } }
              { type: "deleted", id: <workout_id>, deleted_at: <timestamp> }
        """
        if not self.api_key:
            raise ValueError("No Hevy API key is configured.")

        url = f"{self.base_url}/workouts/events"
        params = {
            "since": since,
            "page": page,
            "pageSize": max(1, min(page_size, 10)),
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 404:
                return {"page": page, "page_count": 0, "events": []}
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                raise PermissionError("Unauthorized Hevy API request.") from exc
            raise RuntimeError("Hevy API request failed.") from exc
        except requests.exceptions.JSONDecodeError as exc:
            raise RuntimeError("Hevy API returned invalid JSON.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError("Failed to connect to the Hevy API.") from exc
        except requests.exceptions.Timeout as exc:
            raise RuntimeError("Timed out while requesting the Hevy API.") from exc
        except Exception as exc:
            raise RuntimeError("Unexpected error while requesting the Hevy API.") from exc

if __name__ == "__main__":
    client = HevyClient()
    client.test_connection()
