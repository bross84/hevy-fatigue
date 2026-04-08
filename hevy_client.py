import os
import requests
from dotenv import load_dotenv

load_dotenv()

class HevyClient:
    def __init__(self):
        self.api_key = os.getenv("HEVY_API_KEY")
        self.base_url = "https://api.hevyapp.com/v1"
        self.headers = {"api-key": self.api_key}

    def get_latest_workouts(self, page=1):
        """Fetches the most recent workouts from Hevy."""
        url = f"{self.base_url}/workouts?page={page}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()['workouts']
        else:
            print(f"Error: {response.status_code}")
            return None

# Test the connection (Run this to see if your API key works)
if __name__ == "__main__":
    client = HevyClient()
    workouts = client.get_latest_workouts()
    if workouts:
        print(f"Successfully fetched {len(workouts)} workouts.")