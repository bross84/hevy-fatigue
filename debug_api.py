import json
from hevy_client import HevyClient

TARGET_DATE = "2026-04-02"  # Change this to whatever date you want to inspect

client = HevyClient()
page = 1

while True:
    data = client.get_workouts(page)
    workouts = data.get('workouts', [])
    page_count = data.get('page_count', 1)

    for workout in workouts:
        start = workout.get('start_time', '')
        if start.startswith(TARGET_DATE):
            print(json.dumps(workout, indent=2))

    if page >= page_count:
        break
    page += 1
