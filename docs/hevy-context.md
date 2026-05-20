# Hevy Fatigue — Project Context Reference

This file is read by the Copilot agent at the start of every task. It contains stable project facts — schema, architecture decisions, known bugs, and hard constraints.

---

## Project Summary

Hevy Fatigue is a personal training load and fatigue monitoring dashboard. It syncs workout data from the Hevy API, combines it with daily subjective check-ins, and produces a readiness score, per-pattern fatigue signals, and AI-assisted guidance.

- Deployed via Docker at `hevy.ghostvoid.site`, used as an iOS PWA
- Intended for eventual public release to the Hevy community
- Development model: Claude (architect) → Copilot (implementer) → Brian (reviewer/committer)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI |
| ORM | SQLAlchemy (Core + ORM) |
| Database | SQLite at `/data/hevy_fatigue.db` inside Docker |
| Frontend | Vanilla JS, single-file `index.html`, Chart.js, marked.js |
| AI tab | OpenRouter, backend proxy, encrypted key storage |
| Deployment | Docker + docker-compose |

---

## Key Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, all API routes, fatigue engine |
| `database.py` | SQLAlchemy models, `init_db()`, schema migrations |
| `index.html` | Entire frontend — HTML, CSS, and JS in one file |
| `diagnostic.html` | Engine snapshot / diagnostics page |
| `importer.py` | Hevy API sync logic, session processing pipeline |
| `hevy_client.py` | Hevy API HTTP client, pagination, auth |
| `docker-compose.yml` | Deployment config — contains CasaOS metadata, do not alter |
| `requirements.txt` | Must stay in sync with all imports in `.py` files |

---

## Database Schema

### Tables

| Table | PK | Notes |
|---|---|---|
| `workout_sessions` | `hevy_workout_id` | One row per synced Hevy workout |
| `workout_logs` | — | One row per set; joins to `workout_sessions` via `workout_id = hevy_workout_id` |
| `daily_readiness` | — | Subjective check-in scores, one row per day |
| `exercise_mappings` | — | Maps exercise titles to movement patterns |
| `exercise_canonical` | `exercise_id` | Maps old exercise titles to canonical renamed titles |
| `exercise_conflicts` | — | Flags title mismatches detected during sync |
| `app_settings` | `key` | Key-value store for persistent config |
| `rpe_chart` | — | Reference RPE-to-percent table |

### Verified Column Names

| Column | Correct | Wrong guess |
|---|---|---|
| Set weight | `workout_logs.weight_lbs` | `weight_kg` |
| Workout name | `workout_sessions.workout_title` | `title` |
| Session FK on logs | `workout_logs.workout_id` | `session_id` |

### DB Access

```bash
docker exec -it hevy-fatigue sqlite3 /data/hevy_fatigue.db
```

---

## Fatigue Model

### Core Principles — Do Not Change Without a Spec

| Principle | Rule |
|---|---|
| Subjective-first | Check-in scores drive daily output. Training load is a modifier, not the driver. |
| Common currency | Session stress scores normalize across modalities. Not raw tonnage or duration. |
| Non-prescriptive | No directive language anywhere in output. The app informs, it does not instruct. |
| Named constants only | All thresholds and scale factors in `app_settings` or named module-level constants. No magic numbers. |

### Stress Calculation Pathways

| Modality | Formula |
|---|---|
| `ST` — Strength | per-set RPE × tonnage |
| `HYP` — Hypertrophy | per-set RPE × tonnage; sRPE fallback when ≥50% of sets lack RPE: `sRPE × duration_minutes / HYP_SRPE_SCALE` |
| `CON` / `CAR` | `sRPE × duration_minutes / CON_SRPE_SCALE` |

### Movement Patterns

Five patterns: Knee, Hip, Push, Pull, Full Body. Each runs its own ATL/CTL/TSB via parallel EWMA.

Pattern stress dots use `_pattern_tsb_signal(tsb, ctl)` — not an ATL/CTL ratio. Do not substitute.

---

## Session Modality Classification

Two layers — do not collapse into one:

1. **Title keyword match** (first) — title contains `ST`, `HYP`, `CON`, or `CAR`
2. **Exercise-level analysis** (fallback) — used when title match fails

| Token | Meaning | Example |
|---|---|---|
| `ST` | Strength | `ST Week 1` |
| `HYP` | Hypertrophy | `HYP A` |
| `CON` | Conditioning | `CON @7` |
| `CAR` | Cardio | `CAR Easy` |
| `@N` | sRPE in title | `CON @7` |
| `+` | Mixed session | `ST+HYP` |

If both layers fail: classify as `UNKNOWN`, log in importer, report in implementation report. Do not drop silently.

---

## Schema Migration Pattern

1. All migration code in `init_db()` in `database.py`
2. Every migration must be idempotent
3. Check `sqlite_master` or `PRAGMA table_info` before any `ALTER TABLE`
4. New tables: define SQLAlchemy model on `Base`, let `create_all()` handle it
5. One-time changes: gate with a flag key in `app_settings`
6. No Alembic or external migration tools

---

## Known Active Bugs

Do not touch without an explicit spec. Log any incidental observation under "Out-of-scope observations."

| Bug | Location | Status |
|---|---|---|
| Pattern stress dots show "Fresh" while Per-Pattern Trend shows high load | `_pattern_load_signal()` in `main.py` | Fix spec written (TSB-based signal), not yet implemented |
| Combined score formula label truncates at narrow viewport widths | `index.html` | Open |
| Pattern stress card uses yellow for "Normal Stress" — should be green | `index.html` | Open |

---

## Hard Constraints

| Constraint | Rule |
|---|---|
| ORM | SQLAlchemy only. No Alembic, no Flask. |
| Frontend libraries | Chart.js and marked.js only. No bundler, no build step. |
| Frontend structure | `index.html` holds all HTML, CSS, JS. Do not split. |
| DB path | Read from `os.environ` as `DB_PATH`. Never hardcode. |
| Output language | No directives. App informs, does not instruct. |
| Docker | Do not alter CasaOS metadata in `docker-compose.yml`. Port 8125 fixed. |
| Commits | No `git commit` or `git push`. Brian commits after review. |
| Deletions | No permanent deletions without explicit written instruction. |
| Column names | Always verify with `PRAGMA table_info`. Never assume. |