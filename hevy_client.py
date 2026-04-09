import os
import requests
from dotenv import load_dotenv

# Load the API key from the .env file
load_dotenv()

class HevyClient:
    def __init__(self):
        self.api_key = os.getenv("HEVY_API_KEY")
        self.base_url = "https://api.hevyapp.com/v1"
        self.headers = {"api-key": self.api_key}

    def test_connection(self):
        """Simple check to see if the API key is valid."""
        url = f"{self.base_url}/workouts?page=1"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                print("✅ Connected to Hevy successfully")
                return True
            else:
                print (f"❌ Connection failed. Status: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
            return False

if __name__ == "__main__":
    client = HevyClient()
    client.test_connection()
