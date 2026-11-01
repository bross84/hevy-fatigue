# Hevy API: verified facts

Source: the live OpenAPI spec embedded in https://api.hevyapp.com/docs/ (swagger-ui-init.js), read 2026-10-05. Spec version 0.0.1. Hevy states the API is only for Hevy Pro users, may change structure without notice, and asks clients not to poll exactly on the hour. Auth header: `api-key`.

## Endpoints

| Path | Methods | Purpose |
|---|---|---|
| `/v1/exercise_templates` | GET, POST | List exercise templates; create a custom one |
| `/v1/exercise_templates/{id}` | GET | One template |
| `/v1/exercise_history/{exerciseTemplateId}` | GET | Every logged set for one exercise (`start_date`, `end_date` filters) |
| `/v1/workouts` | GET, POST | List workouts; create one |
| `/v1/workouts/{id}` | GET, PUT | One workout; update it |
| `/v1/workouts/count` | GET | Total workout count |
| `/v1/workouts/events` | GET | Updates and deletes since a date (`since`), newest first, for keeping a local cache current |
| `/v1/routines`, `/v1/routines/{id}` | GET, POST, PUT | Routines (planned workouts) |
| `/v1/routine_folders`, `/v1/routine_folders/{id}` | GET, POST / GET | Routine folders |
| `/v1/user/info` | GET | Account info |
| `/v1/body_measurements`, `/v1/body_measurements/{date}` | GET, POST / GET, PUT | Body measurements |

No endpoint deletes a workout, routine or exercise. `pageSize` maximums from the spec: exercise templates 100 (default 100); workouts, workout events, routines, routine folders and body measurements 10 (default 10). The current code's 100 for templates and 10 for workouts match.

## Sets (what Hevy can store)

Workout set (POST body): `type`, `weight_kg`, `reps`, `rpe`, `distance_meters`, `duration_seconds`, `custom_metric`.

- `type` is one of `warmup`, `normal`, `failure`, `dropset`. There is no AMRAP, joker or "working" type.
- `rpe` is one of **6, 7, 7.5, 8, 8.5, 9, 9.5, 10** or null. RPE 5, 5.5, 6.5 and anything below 6 cannot be stored.
- Routine sets have `type`, `weight_kg`, `reps`, `rep_range`, `distance_meters`, `duration_seconds`, `custom_metric` and **no RPE**. A routine exercise has `notes` and `rest_seconds`.
- `exercise_history` entries carry `rpe`, `weight_kg`, `reps`, `set_type` and `workout_start_time` / `workout_end_time`, so history, last-done dates and e1RM seeding can come straight from Hevy.

## Writing a workout

`POST /v1/workouts` body is `{"workout": {...}}`, all keys snake_case:
- required: `title`, `start_time`, `end_time`, `exercises`
- optional: `description`, `is_private`
- each exercise: `exercise_template_id`, `sets[]`, optional `notes`, `superset_id`

Hevy has no "in-progress workout": a workout is posted complete. The 201 response is `{"workout": [<workout>]}`, a single-element array (not an object). Hevy numbers RPE as 6, 7, 7.5, 8, 8.5, 9, 9.5, 10 only.

## Exercises

Template fields: `id`, `title`, `type`, `primary_muscle_group`, `secondary_muscle_groups`, `equipment`, `is_custom`, `thumbnail_url`. Custom templates are created with `POST /v1/exercise_templates` (`title`, `exercise_type`, `equipment_category`, `muscle_group`, `other_muscles`). Exercise types: `weight_reps`, `reps_only`, `bodyweight_reps`, `bodyweight_assisted_reps`, `duration`, `weight_duration`, `distance_duration`, `short_distance_weight`.

## Gaps in this repo versus the spec (found 2026-10-05)

1. *(Fixed 2026-10-08: the old write-back in `main.py` and `HevyClient.post_workout` were removed. `build_hevy_workout` + `HevyClient.create_workout` are the only way this app writes to Hevy.)* It built `{title, startTime, endTime, exercises:[...]}` with camelCase keys, no `workout` wrapper, no `rpe` and set types Hevy does not accept.
2. Program import accepts exercise names that are not in the cache (stores an empty `hevy_exercise_id` and reports an error).
3. History is read only through `HevyClient.exercise_history` (`best_e1rm_from_hevy` was removed 2026-10-08).
4. `workouts/events` is not used, so the local cache of Hevy data is never refreshed incrementally.
5. RPE below 6 (used in the user's programs) has no Hevy representation.
6. *(Fixed 2026-10-08, same removal.)* `post_workout` read the 201 response as an object, but Hevy returns a list; `create_workout` handles the list.

## Existing AI tooling (web search 2026-10-05; listings read, code NOT audited)

Several community MCP servers wrap the Hevy API so Claude can read workouts and history and create or edit routines and workouts, per their listings covering all 15 public endpoints. Examples: https://github.com/Vellarasan/hevy-mcp, https://hevy-mcp.dev/, https://claudemarketplaces.com/mcp/chrisdoc/hevy-mcp. They need a Hevy Pro API key; because the server sees that key, review its code before use and use a key you can revoke.
