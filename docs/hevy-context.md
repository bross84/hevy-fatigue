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
| Main nav tabs (current) | Today · Trend · Workouts · Exercises (metrics browser) · Patterns (exercise mappings, canonical names, conflict resolution) · Settings · AI |
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

| Table | Verified columns (PRAGMA) |
|---|---|
| `workout_logs` | `id`, `date`, `workout_title`, `exercise_title`, `set_number`, `workout_id`, `exercise_id`, `notes`, `weight_lbs`, `reps`, `rpe`, `rir`, `estimated_1rm`, `is_conditioning` |
| `workout_sessions` | `id`, `hevy_workout_id`, `workout_date`, `workout_title`, `start_time`, `end_time`, `duration_minutes`, `modality`, `modality_confidence`, `verification_status`, `verified_at`, `srpe`, `created_at`, `updated_at`, `modality_note` |
| `exercise_mappings` | `id`, `exercise_title`, `pct_quad_dom`, `pct_posterior`, `pct_upper_push`, `pct_upper_pull`, `source`, `is_reviewed`, `is_conditioning` (`pattern` string is not stored; label is derived at runtime from `pct_*` columns) |
| `exercise_canonical` | `exercise_id`, `canonical_title`, `created_at`, `updated_at` |

Join note: `workout_logs.workout_id` joins to `workout_sessions.hevy_workout_id` (not `workout_sessions.id`).

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

Four patterns: Knee, Hip, Push, Pull. There is no fifth pattern bucket. Each exercise in `exercise_mappings` carries percentage weights across four columns (`pct_quad_dom`, `pct_posterior`, `pct_upper_push`, `pct_upper_pull`). Session stress is distributed to pattern buckets proportionally based on these weights. For conditioning sessions with no mapped exercises, the system falls back to 25/25/25/25 equal distribution.

Updated 30OCT2026 at the user's request: `pattern_recovery.py` implements `pattern-recovery-v1`. The card separates exact 0–4 soreness, decaying load (`ATL / (2 × CTL)`, capped at 1) and a gradual fatigue trend. This supersedes the old clipped-TSB display, which dropped to zero at balance. Legacy `_pattern_tsb_signal` is retained for compatibility, not used by the active pattern card. Monitoring gaps never remove completed training from the EWMAs; unknown ratings are not zero. See README Pattern Stress for evidence gates and provisional parameters.

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
| Pattern stress dots | `_pattern_tsb_signal(tsb, ctl)` in `main.py` | Resolved — implemented and merged May 16 2026 |
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
## Cross-project continuation (2026-10-30)

Daily recommendations use `recovery-confirmation-v1`; the pattern card uses
`pattern-recovery-v1`. Rackbook records the pinned daily model as a separate
`hf-recovery-shadow-v1` arm while retaining its existing `shared-trial-v0` trial.
Two homelab shadow observations were unavailable, while a later read-only probe
succeeded; the original failure cause is unknown. Rackbook now logs safe capture
phase/cause diagnostics without rewriting trial records or changing model rules.

Continue with Rackbook's [fatigue handoff guide](https://github.com/bross84/rackbook/blob/main/docs/fatigue-handoff.md),
plus its `AGENTS.md`, context and backlog. It contains deployment, bridge/logging
checks, preserved-record guarantees and next steps. This logging follow-up needs
only a Rackbook rebuild; this Hevy Fatigue follow-up is documentation-only.
Private replay exports under `data/analysis/` are ignored by Git and are not
transferred to another PC. Production databases/keys remain on the homelab.


## Phase 1 combined application (2026-10-31)

The workout workflow now lives in the isolated rackbook package at /training.
The host retains its monitoring engine, SQLAlchemy database and input selection;
logging retains sqlite3 and a separate RACKBOOK_DB_PATH. These are explicit
exceptions to the old host-only ORM/file-layout constraints above. credentials.py
owns the shared active Hevy credential. Host startup initializes both applications.
Log Workout and Plans are separate destinations; the old Log tab label is Check-in
History. Settings can be opened with /#settings using an allowlisted tab hash.

Save recovery, source revisions, tests and inventory: [integration](training-integration.md).
Draft transfer, backup, controlled switch and rollback: [cutover](training-cutover.md).
No production deployment or old-service retirement is part of implementation.
The coding assistant implements directly; no Copilot handoff is required.

Production backup/copy preflight passed on the operator's 20261101T025736Z
snapshots: key-pair decryption, existing-record preservation, frozen trials and
same-cutoff host outputs verified offline. Private copies are outside Git under
the user's hevy-phase1-verification directory. No deployment occurred; final
quiesced backups and the remaining cutover gates still apply. See the release
evidence in training-verification.md for the explained RPE CSV fingerprint change.

The write-disabled cutover-review Compose override pins discovered external
volumes/network and requires a reviewed image. Local and homelab merged config
rendering passed (homelab Compose v5.4.0, exit code 0); CasaOS metadata is inherited
from the active host Compose. The combined app retains the existing Cloudflare
origin and requires no Tailscale route change. The operator reports
no unfinished work on the only two Rackbook devices (PC and tablet on Tailscale
HTTPS); recheck before cutover if either is used again. No services were stopped.

Deployment image `hevy-fatigue:phase1-cutover-20261031-233737` is staged in the
homelab image store, not running. Server and local immutable image IDs match
(`sha256:ced9a086530c228f1bea17f7f704ab2fbfca7e073d9ecb07be49b33f28f46801`);
write-disabled defaults, transfer checksum and exact-image isolated Python
suites/startup smoke checks passed. Final snapshots and logging-volume staging
still require later authorization. No commit, push or deployment occurred.

Current testing status supersedes the preceding release-preparation notes:
the operator temporarily stopped and then restarted both old apps; both are
running again and no combined deployment occurred. The new logging volume was
created and verified empty, with no final staging reported. The manually staged
image is superseded and must remain unused. The final local review fixed mounted
preview-path blocking and Recent's obsolete credential instructions; 74 host,
467 logging (one expected failure) and 24 JS checks plus mocked browsers and
Docker verification pass. Tablet/PWA checks remain explicitly deferred. Review
and acceptance precede any separately authorized commit/push and GitHub-based
release; do not resume the manual server sequence.

The user subsequently authorized committing the reviewed integration and
pushing only `codex/rackbook-integration`. Deployment, merging main and image
publication remain unauthorized. The image workflow runs on main/manual dispatch,
so this branch push does not publish an image or change either running app.

Merge preparation (2026-11-01): `origin/main` is still the integration baseline
`5bef649`, with no conflicts against reviewed commit `25bba2b`. Added PR-only
read-only CI for Python, JavaScript and container startup; exact commands passed
locally (74 host, 467 logging with one expected failure, 24 JS files). No new
application changes. Prepare the PR and inspect hosted checks; do not merge,
publish an image or deploy while the hold remains. Existing main image-publish
workflow is unchanged and would trigger on a later main merge. Tablet/PWA
acceptance remains deferred and the manually staged image is superseded.

PR #70 is open for the integration, unmerged. Initial GitHub integration tests
passed; CodeQL surfaced test-harness HTML extraction patterns. Shared test-only
mixed-case script extraction plus a regression replaces duplicated patterns;
all 25 JS checks pass locally without weakening existing behavioral assertions.
Read hosted check results on the PR before merging; publication/deployment holds
remain unchanged.

Current deployment supersedes the earlier status notes: PR #70 merged as
`eb76a99`, GitHub built/published its image and the operator deployed it by digest
`sha256:b6a4799f644714cf5379f6bbb5138cbf9d101ab58bfe0b8d0d7fdedee6aa5f22`.
Final backups and deployed-record preservation passed; the combined app is
healthy, Cloudflare pages work, workout saving was explicitly enabled (1/0
write/preview flags) and old Rackbook remains stopped. Tablet/PWA checks are
still deferred. The deployment configuration is now tracked under `deploy/`;
its resolved production file matches the operator's exact server capture.
Future configuration changes go through a GitHub PR before application.
The tracking correction itself must not restart the app or change data.

## Separate prescribed and actual RPE (local implementation, 2026-11-04)

The logger now shows RPErx (prescribed) and RPEact (actual) independently.
Draft `rpe` remains the prescription and `arpe` the actual. Marking done copies
the target into an empty actual field, retaining the existing on-target workflow;
this default is not an independently confirmed effort rating. Actual edits never
overwrite the prescription or completed weight. Next-set LS e1RM, TS/TM, stress
and Hevy output continue to use actual effort. Local `logged_sets.rpe` remains
actual; nullable `target_rpe` stores the prescription. Old rows remain unknown
for target RPE, with no historical backfill. Recent shows both for matched new
records. This does not add session/block advice or nutrition/Health integration.
The user subsequently authorized committing/pushing this follow-up; deployment
remains separate. The original LSe1RM toggle remains unchanged: off uses the
selected e1RM/TM basis, on allows the previous actual set to supply the basis.

## Latest-based production updates (2026-11-04)

The user explicitly restored `docker compose pull && docker compose up -d`.
Production Compose uses `ghcr.io/bross84/hevy-fatigue:latest` and no restrictive
pull policy. This supersedes prior digest-pin requirements for routine updates.
Storage, host key/settings, write/preview flags, port 8125, network and CasaOS
metadata are unchanged. Config changes still go through GitHub; routine app
updates no longer need an image-pin PR. See deploy/README.md. Server application
is an operator action and is not proven by the repository change alone.

## Preserved session prescriptions and descriptive review (local, 2026-11-04)

The operator confirms the deployed RPE fields/LSe1RM toggle work and existing
history/settings are intact after restoring latest-based updates. This is user
acceptance of the preceding release, not deployment evidence for this follow-up.

Newly loaded planned/repeated workouts capture an independent original session
snapshot, including set identities, reps, RPE, fixed loads, notes, plan identity/
revision and the loaded RPE table. Added/omitted work is identifiable without
rewriting the snapshot. Completed sets retain suggested automatic load, actual
load/reps/RPE, completion time, fixed/manual state, LS/basis and entered versus
copied/unrated effort. Existing weight calculations, TS/TM and LS toggle behavior
are unchanged. Ad hoc sessions explicitly lack an initial session baseline;
legacy drafts/frozen saves do not gain invented original prescriptions.

The separate logger table `session_reviews` stores the prescription, actual
exercise evidence and versioned description atomically with required local save
effects and journal completion. GET `/training/session-reviews/{workout_id}` is
read-only. The logger shows the review after a completed save/recovery and Recent
can reopen it. Working-set/reps comparisons and like-for-like e1RM endpoints are
descriptive only; copied/unknown effort is excluded from performance estimates.
No cross-session/block recommendations, host model changes or automatic program
edits are included. Release evidence and limitations: training-verification.md.

## Optional weight-source selection (local, 2026-11-05)

Selecting the currently selected e1RM or TM tile now deselects it. With both off,
weights remain supplied/entered values; RPE, reps, history refresh and unit changes
do not calculate new weights. LSe1RM is disabled while no source is selected,
without erasing its remembered preference. Selecting either source re-enables
the existing calculations. Other movements and existing TS/TM behavior retain
their prior settings; e1RM tracking and session reviews still work.

An additive logger-only `exercise_refs.auto_weights` flag defaults to 1 for
existing movements. The remembered basis stays e1rm/tm internally, avoiding a
rebuild of the constrained table. Draft autoWeights and API auto_weights preserve
the deselected state across reload/new workouts. New review evidence records
basis manual and LS off when no weight source is active. No new progression
algorithm or bodyweight-load calculation was added. Local implementation only.

## Provisional session advice and feedback (local, 2026-11-05)

`session_advice.py` adds provisional-session-v1 as a separate advisory policy;
existing monitoring/daily/pattern models and frozen trials are unchanged. It can
suggest a smaller session from current tiredness/poor recovery, repeated recorded
RPE overshoots, or three declining matched local capacity observations. Optional
extra work requires a good current check-in and three sustained rep-matched
exposures with entered representative effort and no recorded overshoot. These
are tentative product rules, not validated individual recovery thresholds.
Unknown/stale check-ins remain unknown; pain/high joint-discomfort flags yield
review rather than an increase. Manual-weight movements do not use added-weight
capacity trends. No block recommendation or automatic programming edit is added.

Advice uses a read-only host bridge for original 0–4 daily ratings and imported
exercise history, plus exact local history. Workout identities are deduplicated
with local records preferred. The lookback is 90 days, with recent comparison
samples limited by a 21-day staleness rule. The dashboard's .limit(7) only limits
recent-session display; full/incremental Hevy imports already paginate all API
pages. `/api/workouts/recent` has its own display count (default 12). Neither is a
backend history-retention limit. Missing imported history is labelled explicitly.

Each session/movement gets an immutable evidence snapshot. Accept/Modify/Dismiss/
Not now append decision events; Modify records optional set/rep/RPE intent only,
including zero sets for a skipped movement. No workout/program inputs are edited.
Dismiss collapses similar advice for seven days; Not now defers only this record.
Snapshots do not silently re-evaluate after check-in or workout edits; the UI
states this and refresh reloads recorded decisions, not a new assessment.

Frozen save links identify the precise acknowledged decision. Actual saved dose
and entered effort comparisons are recorded atomically with local save effects
and journal completion. Acceptance is never treated as execution or proof of
benefit. The review/Recent show the decision versus actual work and the first
later check-in within the six subsequent dates, read-only and date-only. Later
check-ins do not rewrite frozen recommendation/trial records. Recent decisions
and linked actual counts inform feedback context; this is not automatic fitting
of a physiological model. Unrelated settings, keys and latest update flow remain
unchanged. No commit/push/deployment occurred in this local implementation.

## AI training-history reviews (local, 2026-11-05)

The existing OpenRouter assistant now supports saved training-review conversations.
coaching.py builds six calendar months of evidence from the host SQLAlchemy
session and a read-only SQLite connection to the separate logger path. No Hevy
requests or real-account experiments are needed to assemble a report. Local exact
workout IDs take precedence over matching imports, including zero-set reviews.
Counts, calendar spans, actual exposure intervals, weekly observed set counts,
rep distributions and entered RPE deviations are calculated in code. Imported
roles/targets remain unknown. Matched load comparisons require identical movement,
reps, entered actual RPE, role and known e1RM/TM basis; manual/unknown-basis sets
remain visible without invented total-system e1RMs. Recent detail is bounded and
omissions are labelled; summaries cover the entire available window.

The report includes raw daily and existing pretraining check-ins (separate scales),
current saved plans/completions, preserved prescriptions/reviews, advisory decision
and frozen actual-outcome records, selected existing monitoring context, and bounded
excerpts from previous completed AI conversations. No questionnaire, fatigue model,
trial, source-selection behavior or workout-save payload changes. Block intent is
inferred explicitly, not assumed from a title or elapsed weeks. AI programming
collaboration is authorized; applying changes remains a separate explicit action.

New host-only coaching_conversations/coaching_turns tables preserve evidence date,
server-built context, user messages, selected model, responses and completion status.
They are initialized by existing Base.metadata.create_all. Pending is committed
before provider I/O; completed text is stored before the stream's final marker.
Failed/interrupted/pending output is visible and never automatically resent. A new
review refreshes evidence and can reference bounded prior review excerpts; old
conversations retain their original context. Reloading never calls OpenRouter.

The AI tab has Review my training, a saved-review selector, reload and context
preview. Ordinary follow-ups use the recorded conversation instead of browser-only
history. A compact abstract-level reference pack is embedded in the coaching brief;
only supplied reference URLs become clickable in review answers. Text is sanitized,
but model reasoning and numerical claims still need human review. No live literature
search, personalized model training or automatic program editing is claimed.

## AI model selector refresh (local, 2026-11-05)

The AI dropdown now uses eight current text-chat IDs verified against the public
OpenRouter /api/v1/models catalog on 2026-11-05. Budget choices: GPT-6 Luna,
Claude Haiku 5.5, DeepSeek V4.1 Flash and Qwen3.8 Flash. Balanced choices:
GPT-6.1 Terra and Gemini 3.8 Flash. Higher-cost choices: GPT-6.1 Sol and
Claude Sonnet 5.5. These are price/positioning tiers, not measured training-coaching
rankings. No Pro, batch-only, video/image-generation or experimental presets.

The default for a new browser/unspecified legacy chat request is GPT-6.1 Terra;
existing localStorage model IDs remain untouched, including removed presets, which
appear as saved custom selections. The custom-ID input remains available. Selected
presets show checked-date input/output USD per million tokens; history/reasoning
and provider rates affect actual charges. No API call or automatic model switch
is triggered by changing the selector. Keys, databases, review evidence, fatigue
models, training prescriptions and logger weight controls remain unchanged.
