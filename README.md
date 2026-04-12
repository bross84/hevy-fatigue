# ⚡ Hevy Fatigue Monitor

A personal fatigue and readiness tracking web app for powerlifters and strength athletes using the [Hevy](https://hevy.com) workout logger. Automatically pulls your training data from the Hevy PRO API, calculates session stress scores, and pairs them with your daily morning check-in to help you make smarter training decisions.

> **Requires a Hevy PRO subscription** for API access.

---

<!-- SCREENSHOT: Full dashboard view (dark mode) -->
<!-- Suggested: capture the Dashboard tab showing the stress chart and check-in form side by side -->

---

## What It Does

Most fatigue tools either ignore intensity (just counting sets) or ignore volume (only tracking RPE). This app tracks both:

- **Central Stress** — intensity-driven fatigue. Heavy sets close to your max move this number disproportionately. Think nervous system / CNS fatigue.
- **Peripheral Stress** — volume-driven fatigue. Accumulates with every set and rep regardless of how heavy. Think muscular soreness and metabolic fatigue.

Both are calculated from your logged RPE and reps using an RPE percentage table — no manual input required beyond logging your sets in Hevy as you normally would.

### Features

- 📊 **Stress chart** — 60-day rolling history of central and peripheral stress with a configurable moving average baseline. Filter by movement pattern (Quad, Hip, Push, Pull).
- 📝 **Morning check-in** — Log soreness by movement pattern, joint health, tiredness, perceived recovery, and optionally HRV, sleep hours, and sleep quality.
- 💪 **Workouts tab** — Last 12 sessions with per-workout central and peripheral stress scores.
- 🗂️ **Exercise mappings** — All exercises auto-classified into movement patterns by keyword rules. Reviewable and editable with custom percentage splits for blended movements.
- 🔄 **Hevy sync** — Manual sync button on the dashboard; auto-syncs on every check-in submission.
- 🌗 **Light / Dark / Auto theme** — Follows system preference by default.
- 📱 **Mobile responsive** — Works on phone browsers for morning check-ins.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy |
| Database | SQLite |
| Frontend | Vanilla HTML / CSS / JS, Chart.js 4 |
| Deployment | Docker + docker-compose |

---

## Getting Started

### Prerequisites

- A [Hevy PRO](https://hevy.com) account with API access
- Your Hevy API key — found at **hevy.com → Settings → Developer**
- Either **Python 3.12+** (local run) or **Docker** (recommended)

---

## Option 1 — Run Locally (Python)

### 1. Clone the repository

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

### 3. Set up your environment file

```bash
cp .env.example .env
```

Open `.env` and paste your Hevy API key:

```
HEVY_API_KEY=your_api_key_here
```

### 4. Import your Hevy data

```bash
python importer.py
```

This pulls your full workout history from the Hevy API into a local SQLite database. It is safe to run multiple times — duplicate sets are silently skipped.

### 5. Start the server

```bash
uvicorn main:app --reload
```

Open your browser at **http://localhost:8000**

---

## Option 2 — Docker (Recommended)

Docker is the recommended way to run the app long-term, especially if you want it always-on on a home server or VPS. Your database is stored in a named volume that **survives container rebuilds and updates** — you never lose your data.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / Mac) or Docker Engine + Compose (Linux)

### 1. Clone the repository

```bash
git clone https://github.com/bross84/hevy-fatigue.git
cd hevy-fatigue
```

### 2. Set up your environment file

```bash
cp .env.example .env
```

Open `.env` and paste your Hevy API key:

```
HEVY_API_KEY=your_api_key_here
```

### 3. Build and start the container

```bash
docker compose up -d
```

Open your browser at **http://localhost:8000**

### 4. Import your Hevy data

The first time you run the app, click **⟳ Sync Now** on the Dashboard to pull your full Hevy workout history. This may take a minute depending on how many workouts you have.

After the initial import, syncing happens automatically every time you submit a morning check-in. You can also trigger it manually from the Dashboard at any time.

---

### Updating the app

```bash
git pull
docker compose up -d --build
```

Your data is untouched. The `hevy-data` Docker volume that holds the database is completely separate from the application container.

---

## Daily Workflow

1. **Open the app each morning**
2. **Submit a check-in** — rate soreness by movement pattern, joint health, tiredness, and recovery. Optionally add HRV and sleep data.
   The app auto-syncs your latest Hevy workouts before calculating stress scores.
3. **Review the dashboard** — the stress chart shows how yesterday's session compares to your rolling baseline.
4. **Check the Workouts tab** for a session-by-session breakdown.

<!-- SCREENSHOT: Morning check-in form -->
<!-- Suggested: capture the check-in card filled in with typical values -->

<!-- SCREENSHOT: Stress chart with pattern filter active -->
<!-- Suggested: capture the chart with one of the pattern filters (e.g. Hip) selected -->

---

## Exercise Mappings

All exercises imported from Hevy are automatically classified into one of four movement patterns using keyword matching:

| Pattern | Muscles | Examples |
|---------|---------|---------|
| **Quad** | Quads, Knee extensors | Squat, Leg Press, Hack Squat, Lunge |
| **Hip** | Hamstrings, Glutes | Deadlift, RDL, Hip Thrust, Leg Curl |
| **Push** | Chest, Shoulders, Triceps | Bench Press, Overhead Press, Dip |
| **Pull** | Lats, Traps, Biceps, Rear Delts | Row, Lat Pulldown, Pull-up, Face Pull |

Blended movements (e.g. a conventional deadlift that loads both quads and hips) can be given a custom percentage split from the **Exercises tab**. The split only affects which bucket on the pattern chart receives credit — it has no effect on the stress score totals.

> **Note:** The Exercises tab is entirely optional. Leaving exercises unclassified has zero impact on your fatigue scores.

<!-- SCREENSHOT: Exercises tab showing the mapping table -->
<!-- Suggested: capture the Exercises tab with a mix of reviewed and unreviewed exercises visible -->

<!-- SCREENSHOT: Edit modal with a blended split set (e.g. 20% Quad / 80% Hip) -->
<!-- Suggested: capture the edit modal with the split bar showing a non-100% single-pattern split -->

---

## Accessing Remotely

If you want to access the app from outside your home network (e.g. from your phone at the gym), the recommended approach is [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared`). This exposes your local Docker container over HTTPS without opening any ports on your router.

---

## License

MIT — do whatever you like with it.

---

## Acknowledgements

Inspired by the [RTS TRAC system](https://www.reactivetrainingsystems.com/) and the RPE-based autoregulation methodology developed by Mike Tuchscherer. The stress model is adapted from concepts in the scientific literature on session RPE and training load monitoring.
