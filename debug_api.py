import json
from hevy_client import HevyClient

client = HevyClient()
data = client.get_workouts(page=1)

# Print the first workout only, formatted so it's readable
first_workout = data.get('workouts', [])[0]
print(json.dumps(first_workout, indent=2))
