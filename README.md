# Hevy Fatigue

A self-hosted fatigue and training-readiness app for strength athletes using the [Hevy](https://hevy.com) workout logger.

The app pulls workouts from the Hevy API, derives training stress from your logged sets, and combines that with a daily subjective check-in to generate a simple daily recommendation.

> Requires a Hevy PRO subscription for API access.

## What It Does

This app combines two inputs:

- Training stress derived from your Hevy workout history
- A daily subjective check-in that drives the base fatigue score

The current model is subjective-first:

- Your check-in creates the base fatigue score
- Recent training stress applies a bounded modifier
- The final fatigue score is shown on a 0-10 scale

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

> Screenshot to add: Main dashboard showing Short Term Fatigue, Long Term Fatigue, Daily Recommendation, the 30-day recommendation chart, and the stress chart.

## Recommendation Model

The app uses five recommendation buckets:

- Large Increase
- Increase
- Continue
- Decrease
- Large Decrease

By default, recommendations use fixed fatigue score thresholds:

- `>= 8.0` -> Large Decrease
- `>= 6.5` -> Decrease
- `>= 4.5` -> Continue
- `>= 3.0` -> Increase
- `< 3.0` -> Large Increase

You can optionally override those thresholds in Settings.

You can also enable adaptive percentile mode. When enabled, the app uses recent fatigue-score history to derive thresholds from your own data:

- `P20` -> Increase threshold
- `P40` -> Continue threshold
- `P60` -> Decrease threshold
- `P80` -> Large Decrease threshold

If there are not enough recent entries, adaptive mode falls back safely to your fixed thresholds.

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

> Screenshot to add: Daily check-in form with soreness, joint health, tiredness, and recovery inputs visible before submission.

> Screenshot to add: Log view showing past entries and fatigue trend history.

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

> Screenshot to add: Settings tab with API key management, manual sync, and advanced calibration options visible.

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

> Screenshot to add: Exercises tab showing exercise mappings, movement group assignment, and an example of the stress-calculation exclusion toggle.

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

> Screenshot to add: First-time setup view showing where to paste and save the Hevy API key.

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

