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
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            workouts = response.json().get('workouts', [])
            print(f"✅ Success! Connected to Hevy. Found {len(workouts)} recent workouts.")
            return workouts
        else:
            print(f"❌ Connection Failed. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return None

if __name__ == "__main__":
    client = HevyClient()
    client.test_connection()