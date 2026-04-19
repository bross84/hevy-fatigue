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

if __name__ == "__main__":
    client = HevyClient()
    client.test_connection()
