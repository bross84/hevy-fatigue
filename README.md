# <img src="resources/favicon.png" alt="Hevy Fatigue icon" width="18" height="18"> Hevy Fatigue

A self-hosted fatigue and training-readiness app for strength athletes using the [Hevy](https://hevy.com) workout logger.

The app pulls workouts from the Hevy API, derives training stress from your logged sets, and combines that with a daily subjective check-in to generate a simple daily recommendation.

> Requires a Hevy PRO subscription for API access.

## What It Does

This app combines two inputs:

- Training stress derived from your Hevy workout history
- A daily subjective check-in that drives the base fatigue score

The current model is subjective-first:

- Your check-in creates the base fatigue score
- The raw combined score is 80% subjective fatigue and 20% recent tonnage relative to your baseline
- The dashboard fatigue trend uses a 0-20 scale and retains recent fatigue as recovery improves

## Current Dashboard Terms

- Short Term Fatigue: your recent loading relative to your own peak history
- Long Term Fatigue: your longer training baseline relative to your own peak history
- Daily Recommendation: the current recommendation bucket based on the fatigue model
- Intensity Load: the intensity-driven stress signal
- Volume Load: the volume-driven stress signal

## Features

- Daily check-in for soreness, joint health, tiredness, and perceived recovery
- Subjective-first fatigue score with training-load modifier
- 30-day recommendation chart based on fatigue score
- Stress chart with Intensity Load and Volume Load history
- Pattern filtering for Quad, Hip, Push, and Pull
- Workout summary and recent-workouts detail views
- Editable exercise mappings with custom movement splits
- Per-exercise exclusion from stress calculations
- Manual sync from Settings plus auto-sync on check-in submission
- Light, dark, and auto theme support
- Mobile-friendly single-page UI
- Optional calibration settings for recommendation thresholds
- Optional adaptive percentile mode based on recent fatigue history

## Screenshots

### Dashboard

![Dashboard](resources/Dashboard.png)

### Workouts

![Workouts](resources/Workouts.png)

### Exercises

![Exercises](resources/Exercises.png)

### Log

![Log](resources/Log.png)

### Settings

![Settings](resources/Settings.png)

## Recommendation Model

The app uses five recommendation buckets:

- Large Increase
- Increase
- Continue
- Decrease
- Large Decrease

The raw score combines 80% subjective fatigue and 20% objective load. Objective
load compares tonnage from the seven completed days before a check-in with the
180-day weekly baseline. Same-day and future workouts are excluded.

When fatigue worsens, it takes effect immediately. When it improves, the fatigue
trend retains 65% of its previous value and incorporates 35% of today's raw score.
Increases require two consecutive check-ins at least 0.5 points below the next
threshold and advance only one recommendation level at a time.

The fixed fatigue bands are `<=6`, `<=8`, `<=13`, `<=14`, and `>14`, from Large
Increase through Large Decrease. Confirmation rules can delay an increase after
the trend crosses a boundary. Legacy/adaptive calibration thresholds do not
control this daily model; pattern sensitivity settings remain separate.

**Continue Training as Normal** is shown with an insufficient-data explanation
when today's check-in is missing/incomplete, the workout baseline is insufficient,
or monitoring is being established. It means follow your existing plan, without
suggesting an increase or reduction based on missing evidence.

Initial monitoring and returns after more than seven days without valid data
require three consecutive complete check-ins. Shorter gaps show the fallback on
missing days and break increase confirmation, but retain established fatigue
memory. Workouts logged during any monitoring break remain in the load baseline.
The initial workout minimum is three training dates with at least 28 days since
the oldest within the 180-day window. These evidence gates are provisional product
rules, not validated recovery timelines. Joint advisories remain separate.

The dashboard, history chart, log, diagnostics and AI snapshot share this model,
versioned as `recovery-confirmation-v1`. No database migration is required.

## Stress Model

The app calculates two training stress signals from your logged Hevy sets:

- Intensity Load: heavier, higher-effort work drives this up faster
- Volume Load: total work accumulated across sets and reps

These are derived from the RPE table and your logged reps, not from arbitrary set counting.

Warm-up sets are excluded.

Exercises marked "Exclude from stress calculations" are also excluded.

## Daily Workflow

1. Open the app
2. Submit your daily check-in
3. The app auto-syncs recent Hevy data before calculating the new entry
4. Review:
  - Short Term Fatigue
  - Long Term Fatigue
  - Daily Recommendation
5. Use the Log tab to review past entries and fatigue trends

## Settings

The Settings tab handles:

- Hevy API key management
- Manual sync
- Advanced calibration

Advanced calibration is optional and off by default.

It supports:

- Custom fixed thresholds
- Adaptive percentile thresholds
- Configurable lookback window
- Configurable minimum entry count before adaptive mode activates

## Exercise Mappings

Exercises are auto-classified into four movement groups:

- Quad
- Hip
- Push
- Pull

You can review and edit mappings in the Exercises tab.

Notes:

- Custom movement splits affect the pattern charts only
- They do not change the total fatigue score directly
- Excluding a movement from stress calculations removes it from stress totals entirely

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, SQLAlchemy |
| Database | SQLite |
| Frontend | Vanilla HTML, CSS, JS, Chart.js |
| Deployment | Docker / Docker Compose |

## Getting Started

### Prerequisites

- Hevy PRO account with API access
- Hevy API key from `hevy.com -> Settings -> Developer`
- Either Python 3.12+ or Docker

## Option 1 - Run Locally

### 1. Clone the repo

```bash
git clone https://github.com/bross84/hevy-fatigue.git
cd hevy-fatigue
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Start the app

```bash
uvicorn main:app --reload
```

Open:

```text
http://localhost:8000
```

### 4. Add your Hevy API key

Open the Settings tab and save your API key there.

That is now the primary setup flow.

### Optional local fallback

If you prefer not to use the Settings tab locally, the Hevy client still supports:

1. `HEVY_API_KEY_FILE`
2. `HEVY_API_KEY`

It also loads `.env` if present.

## Option 2 - Docker

Docker is the recommended long-running deployment path.

### 1. Clone the repo

```bash
git clone https://github.com/bross84/hevy-fatigue.git
cd hevy-fatigue
```

### 2. Start the container

```bash
docker compose up -d
```

Open:

```text
http://localhost:8125
```

### 3. Add your Hevy API key

Open the Settings tab and save your API key.

The app stores the key encrypted in the app settings table.

### Optional Docker fallback

The app still supports a file-based fallback key at:

```text
/data/hevy_api_key
```

That is useful for advanced deployments, but no longer required for normal setup.

## Updating the App

```bash
docker compose pull
docker compose up -d
```

Your SQLite database lives in the persistent Docker volume and survives rebuilds.

## CLI Importer

If you want to run a one-off import outside the UI:

```bash
python importer.py
```

This is optional. Most users can rely entirely on the in-app sync flow.

## Acknowledgements

The project is heavily inspired by Mike Tuchscherer's RTS / TRAC ideas and broader RPE-based autoregulation concepts.

This app is not an RTS product and does not claim to reproduce TRAC exactly.


## Tests

Install development dependencies and run the regression tests:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/test_recommendation_ui.cjs
```

Tests use isolated in-memory SQLite databases and do not sync with Hevy.
