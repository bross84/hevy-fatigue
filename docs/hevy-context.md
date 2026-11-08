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
| `coaching.py`, `coaching_stress.py`, `coaching_progress.py`, `coaching_outcomes.py` | Read-only AI coach evidence report; stress-index and progress blocks per exercise; saved-proposal outcomes |
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

## Compact logger workspace (local, 2026-11-06)

The approved logger design is implemented in `rackbook/log.html` with view-only
`static/logger-layout.js` and `static/logger-layout.css`. Navigation stays on the
left from 1100px; narrower screens use the same grouped links in a keyboard-
dismissible drawer. From 1900px the workspace has compact set columns, selected
exercise tools and a workout outline/control rail, capped at 1640px of content.
The rails stay available while scrolling; phone/tablet retain the existing set,
keypad and fixed timer/save controls. Dashboard/other pages are outside this pass.

The outline opens a collapsed exercise only on explicit selection. Existing manual
collapse/completion behavior is preserved; finishing all sets does not auto-collapse.
Selection is transient and scoped by exercise instance ID, including duplicate
template IDs. Notes edit existing `ex.notes`; frozen drafts disable the new editor.
Previous performance reads the existing reference cache without additional APIs.
The same live loader/timer nodes move between panes at breakpoints; ownership checks
prevent duplicates after card replacement. Grip drags reacquire pointer capture
after DOM moves so release persists the displayed order. UUIDs, frozen payloads,
TS/TM, canonical completed weights and monitoring/trial rules are unchanged.

Validation uses disposable previews only. See training-verification.md for the
six-exercise/23-set regression and remaining physical-device checks. This is local
implementation, not a commit, push, publication or production deployment.

## Dashboard workspace (local, 2026-11-06)

The approved dashboard layout is implemented entirely inside `static/index.html`,
retaining the host's single-file vanilla-JavaScript boundary. It uses the logger's
grouped left navigation and matching neutral/blue palette. Navigation is persistent
from 1100px (224px rail, 240px from 1900px); phone/tablet use a drawer with focus,
Escape/scrim dismissal and inert background content. Host buttons still use the
existing allowlisted tab/hash activation; logging links remain under `/training`
and Settings remains `/#settings`. The obsolete mobile bottom bar is hidden.

At 1900px and above, independent columns place readiness/pattern stress on the
left, the existing chart stack in the center and recent sessions/joint advisories
on the right. Tablet is a two-column grid; phone is a single stack. Original card
IDs, chart controls, dates, check-in form, theme preference, ranges, seven-session
display limit, score sources and missing-data gaps are retained. No backend/model,
history window, same-day cutoff, frozen trial or database changes belong to this
UI pass. `tools/check_dashboard_layout_browser.py` checks actual shipped Chart.js
against synthetic, temporary host records with mocked Hevy. No real account or
deployed data is used; see training-verification.md for evidence and test-harness
correction. Commit/push/publication/deployment are separate actions.

## Session motivation for coaching (local, 2026-11-06)

The logger has one optional session-level pre-training question: Eager (0),
Willing (1), Neutral (2), Reluctant (3), Dreading it (4). An optional reason
(fatigue, stale training, time/life stress, other) and note accompany the answer.
Unanswered is absent/unknown, never inferred eager. Draft persistence is separate
from saveDraft's weight/stress/trial hooks. Ratings, reasons and notes do not
enter fatigue calculations, daily check-ins or frozen trial records.

Completed workout saves atomically add a logger-only session_motivation record
with the exact frozen answer, client-reported time/phase and server save time.
It is not sent to Hevy. Partial/failed local finalization does not repost the
remote workout. Old frozen requests remain compatible because absent motivation
is omitted before hashing. Controls lock after freeze; draft transfer retains
and validates the optional answer. Marked/previously started working sets make
later edits non-prospective, including after undo. Post-save/Recent review shows
saved motivation even without an original prescription.

New AI training reviews include motivation_checkins from the existing six-month
read-only logger bridge. The coaching brief explicitly separates motivation from
fatigue, considers reasons alongside performance/spacing, and forbids interpreting
one reluctant day as proof of overtraining or a failed block. Only saved workouts
are observed; skipped/discarded workouts are not tracked. Older review evidence
remains frozen; start a new review after saving to include new answers. No automatic
programming changes, commits, pushes or deployments are part of this local work.

## Dashboard alignment follow-up (2026-11-06)

The approved follow-up supersedes the dashboard's independent unequal-width
column stacks above. One grid now aligns equal-width cards by row: two columns
from 700px, three from 1900px, and one on phones. Readiness and Fatigue Trend
lead; desktop Recent sessions completes the first row, followed by Pattern
stress, Volume/Fatigue and Per-Pattern Fatigue Trend. At two columns, Recent
sessions moves to the third row. Row minimums match the reviewed mockup but
expand for content; chart canvases resize within their cards. Joint advisories
span the grid. Existing chart/model values, gaps, ranges and theme behavior stay
with their existing renderers. Left navigation remains at its existing breakpoints.

Logger exercise cards now explicitly fill a shared column capped at 880px with
border-box sizing from 1100px. Expanded/collapsed cards share both edges, while
80px weight columns and the existing compact set grid remain unchanged. On
smaller screens the original touch/keypad layout is retained.

## Chart-focused dashboard follow-up (2026-11-06)

This approved composition supersedes the equal-card dashboard arrangement above.
Readiness is a compact summary with the same score, state, recommendation and
subjective/objective/combined breakdown. Fatigue Trend spans the available width.
Volume/Fatigue and Per-Pattern Fatigue Trend share equal columns from 2000px;
below that they stack at full width. Pattern stress and Recent sessions follow
all three charts and share a row from 1100px. Left navigation keeps its existing
1100/1900px behavior. Phones retain a compact wrapped summary and single column.

The change is presentation-only in static/index.html: existing card IDs,
renderers, model scores, data gaps, ranges and chart lifecycle are preserved.
The prior compact logger inputs and consistent exercise card widths are untouched.

## Required motivation and weekly coaching (local, 2026-11-06)

Supersedes the optional rating/reason UI above: every current logger workout
requires an explicit Eager(0)..Dreading it(4) answer and Confirm check-in before
working sets or a new save. Notes remain optional; the reason dropdown is removed.
Historical reason data stays readable, with fatigue displayed as Low Energy/Tired
and interpreted as ambiguous legacy wording, never proof of poor recovery.
Motivation represents engagement, not predicted performance or a fatigue component.
Daily, pattern and trial models, exact RPE and loading/toggle rules are unchanged.

Confirmed observations persist in logger-only session_checkins before workout
completion. They may be unlinked and must not be counted as completed training or
assumed skipped sessions. Device confirmation allows logging during an AI/network
failure; server confirmation is required before freezing/uploading a new-format
save. Pending legacy frozen requests are still valid without new check-in fields.
New checkin_required saves verify the exact confirmed answer, start and plan link;
finalization links the check-in atomically with all required local records.

A planned week is the saved microcycle identity, not Monday–Sunday. Confirming
its first session starts one opening AI review using current check-in, saved plan,
monitoring context, training history/spacing and prior coaching excerpts. Later
days and reloads reuse it; late confirmations do not generate a supposedly
pre-training assessment. AI unavailability never blocks logging. The closing
review of a finished microcycle starts automatically at the next check-in (see
"Automatic microcycle review" below) and can still be requested from completed
Plans or the logger's completed microcycle; it includes linked actual workouts,
manual-completion uncertainty, and the opening discussion. It opens a persistent
AI Coach conversation for proposals, questions and program development. No
recommendations are automatically applied.

Opening and closing reviews have deterministic IDs per plan/kind. Existing host
conversation/turn persistence protects concurrent or uncertain attempts from
reposting. Each review freezes its evidence; edits do not silently regenerate it.
Provider requests use the browser's selected model or the server's default.
Nothing schedules a paid request when the app is closed, on a calendar boundary,
or merely because a week is completed. No commit/push/deployment in this work.

## Daily AI interpretation and personal fatigue range (local, 2026-11-06)

After a successful daily check-in save or rating edit in the host UI, DailyCoach
requests a short interpretation using the existing selected OpenRouter model.
The ratings commit first; AI preparation/provider failures cannot roll them back.
Opening the dashboard also starts an interpretation for today’s existing check-in
if there is no recorded attempt. Reloads restore recorded turns. Retry appears
after a failure, including an interrupted turn. Pending and completed turns
are restored without resending. Setup failures are remembered in this browser.

The dashboard shows the saved initial interpretation, capture date, model/status
and Discuss with AI Coach link. Existing conversation storage persists follow-ups.
Identity is deterministic for date + exact eight ratings, including nulls. Changed
ratings create another frozen version; unchanged ratings reuse the saved version.
Old conversations survive edits/deletion, labelled by evidence date. Future-date
check-ins do not generate interpretations. Backdated interpretations use the
selected observation and exclude workouts on/after that date.

The existing 0–20 scores, recovery smoothing, rule outputs, cutoff, missing-data,
pattern/trial calculations and logging weight behavior are unchanged. The primary
readiness card points to AI interpretation. Diagnostics retain the old rule output
for comparison. Raw subjective/objective/
combined values remain visible. Motivation is engagement, never added to fatigue.

Fatigue Trend replaces fixed Low/Recovery/Optimal coloured zones with each point's
prior 84-calendar-day 10th–90th percentile of eligible smoothed scores. Require 14
observations spanning at least 28 days; otherwise show collecting/coverage. Range
is computed before display slicing and excludes the point itself/future data.
It is descriptive of this athlete, not a validated optimal zone or a programming
trigger. Raw combined scores have a separate dashed line; missing values stay
null and the axis remains 0–20. Absolute ratings remain available so chronically
high fatigue cannot be hidden by the moving reference. No program writes occur.

Coach script compatibility (follow-up to #88). The host HTML requires cache
revalidation. Dashboard and logger load the shared Coach script with a revised
URL, and the dashboard also revises its daily script URL. Update these revisions
when the script interface changes. If the expected function is unavailable, the
daily card keeps the saved evidence and prompts for a reload and Retry.

Pending daily interpretations can be retried explicitly after five minutes. The
dashboard and saved AI Coach conversation use the same frozen check-in evidence.
The server checks the specific pending turn and expected sequence before
recording it as interrupted and starting a replacement in one transaction.
A late completion may only update a turn that is still pending.

The dashboard's daily card now shows one AI training recommendation and one
short reason. Coach remains the entry point for discussion. The current format
uses a distinct conversation identity, so a check-in with an older completed
write-up can generate the compact recommendation once. Older conversations
remain accessible. If the prior review has a pending turn, it retains its
existing Retry flow before the dashboard starts the new format.

The AI training recommendation appears in the recommendation area of the
Readiness card, with its reason and Coach link in the same section.

## Daily check-in dialog (local, 2026-11-07)

A missing check-in shows the Check in action on Today. The daily form opens
from that action, with focus on Close and Tab contained in the dialog. Escape,
Close, and backdrop dismissal restore the trigger. Saving today's ratings
hides the trigger and returns focus to the dashboard heading.

## Today overview layout (local, 2026-11-07)

Readiness groups the missing-check-in explanation with its action. Current
Pattern stress follows Readiness on narrow screens and sits beside it from
1400px. The table retains separate load, soreness and trend signals. Fatigue
Trend leads the charts below the overview. Log Workout is available in
Readiness below the 1100px persistent-navigation breakpoint.
An available daily fatigue score shows its maximum inline (for example,
`6.0 / 20`). An unavailable score is shown as a dash when applicable.

## Mobile next set (local, 2026-11-07)

Below 768px the logger uses full-width 48px set buttons and highlights the
next unfinished working set in each exercise. A blocked working set shows
the motivation requirement beside its button. Check in opens the live form
there and confirmation returns focus to the set. Warm-ups remain available
before confirmation. Session advice is in a disclosure below the set rows.

## Mobile save recovery (local, 2026-11-07)

The mobile logger hides Finish and save to Hevy while its recovery panel is
present. The rest timer remains in the footer. If Hevy confirmed the upload,
Finish local records leads. For an unknown outcome, Check save status leads
and a separate disclosure accepts the ID of an existing Hevy workout.

## Stress index in AI coach evidence (local, 2026-11-07)

`coaching_stress.py` adds a read-only `stress` block to every exercise in the
`build_report` evidence, plus a top-level `stress_model` description and two
limitation notes. It scores the sessions the report has already merged (exact
local sets replace the matching import) with `rackbook/stress_index.py`
(`rackbook-stress-v2`), so the coach, `/log` and `/stress` share one calculation.
No Hevy request, database write or new table is involved; the module is pure.

Per movement: model version, `as_of`, scored/unscored session counts, days since
the last scored exposure, the typical session (median, usual low/high, baseline
session and estimated-session counts, provisional flag), rolling 7/28-day
totals, the latest session and the last six sessions with their earlier-only
baseline status. Values are rounded to two decimals. A movement with nothing
scorable reports `no_scorable_sessions` and an `unscored_sessions` count, never
a zero.

Rules and limits: imported host start times are naive UTC (the importer strips
the offset) and are treated as UTC; sessions with no start time are not scored.
The window is the report's six months, so older history does not feed the 84-day
reference. Imported Hevy sets carry no set type, so warm-ups cannot be separated
there and local exact sets are more reliable; blank RPEs are estimated at 5 and
counted. Report-day sessions are included even when their UTC start falls on the
next day. Under context pressure per-session stress detail is dropped before the
summary and the omission is recorded.

`BRIEF` tells the coach to compare a session only with that movement's own range,
never to add stress across movements or call it a recovery limit, fatigue
measurement or optimal zone, and not to add or cut work on stress alone. Existing
frozen conversations keep their original evidence; new reviews carry the block.
No session-advice rule or automatic programming change uses stress yet. Tests:
`tests/test_coaching_stress.py`, `tests/test_coaching_patterns.py`.

## Rolling-window pattern stress index in AI coach evidence (local, 2026-11-07; windows 2026-11-08)

`coaching_stress.pattern_rollup` adds `pattern_stress_index` to the report. It
splits each scored movement session (total, central, peripheral) across Knee,
Hip, Push and Pull using that exercise's current `exercise_mappings` percentages
(matched by exercise title) and sums over rolling 7-day windows. It is read-only and
stores nothing. The host Pattern Stress card (ATL/CTL, soreness, trend), the
daily/recovery models and `calculate_stress_scores` are unchanged; this is a
different quantity and is named to avoid confusion (see `GLOSSARY.md`).

Windows (2026-11-08): the first version summed by Monday calendar weeks, which
does not match how training is paced (a microcycle is not a calendar week) and
made totals jump on a Monday. A window is now the 7 local days ending on the
report date (`as_of`); the last window is the last 7 days, and there is no
partial window. `coaching.build_report` uses the same windows for its per-window
workload counts, which replace `weekly_workload` as `workload_windows`
(`window_start`, `window_end`, sessions, known and unknown-role working sets, and
`partial` for the oldest window when it starts before the six-month evidence
window). Evidence frozen before this change keeps the old Monday shape; nothing
is regenerated. The host's separate per-movement volume chart is unchanged.

Block contents: model version, `as_of`, `window_days`, nine windows (the last
7 days and eight before them) with per-pattern totals and unmapped stress,
the rolling 28-day total (the separate `rolling_7_day` copy is gone because the
latest window is the same quantity), per-pattern `typical_window` (median of
the earlier windows that had scored sessions; the latest window is the one being
judged and never counts; provisional under four such windows), unmapped
exercise titles (at most ten) and `reviewed_share`, the fraction of attributed
stress from user-reviewed mappings.

Rules: accessories use their full mapping percentage; no discount is invented.
Conditioning exercises are excluded. A missing mapping, or percentages that do
not sum to 1.0 (±0.01), put the stress in `unmapped` rather than guessing.
Empty windows appear as real zeros but never enter the typical window. Mapping edits
re-attribute history on the next report because nothing is stored. Frozen
conversations keep their original evidence. `BRIEF` tells the coach these are
attributed totals, never recovery limits or targets, and that a low push or pull
window can simply be a lower-body window. No UI shows this block yet.

## Why an AI turn failed (local, 2026-11-08)

A daily recommendation that failed showed only "Response failed". Two causes were
indistinguishable: the provider failing, and a reply that was valid in substance but
broke a format rule (a 215-character reason against a 200 limit, fixed separately by
accepting up to 300 and asking for 160). Each failed or interrupted turn now keeps a
short plain-text reason in `coaching_turns.failure` (nullable, at most 300
characters, never evidence or prompt text), added on first start by a guarded
`ALTER TABLE` in `database.init_db`. Older turns have none and show the old message.

`coaching_stream.relay` decides the provider-side reasons (an error event with the
provider's own message clipped to one 160-character line, a reply cut off at the length
limit, a content-filter stop, an empty reply, unreadable data, a stream that ended early,
a reply over the saved size limit, a dropped connection) and passes the first one to a
recorder that declares a third `reason` parameter; two-parameter recorders are unchanged.
An HTTP error before streaming (bad key, unknown model, no credit) is recorded from the
provider's message. `coaching.parse_daily_recommendation` names the exact format rule that
a daily reply broke, and `finish_turn` stores it. The conversation view's turns gain
`failure`; the daily card shows "Response failed. <reason> You can retry the
interpretation." and the AI chat page adds "Reason: …" to its recorded-status message, both as
plain text. Retry, no-automatic-resend and the failed status itself are unchanged. Tests:
`tests/test_coaching_stream.py`, `tests/test_daily_coaching.py`, `tests/test_daily_coach_ui.cjs`.

## Movement progress in AI coach evidence (local, 2026-11-07)

`coaching_progress.py` adds a read-only `progress` block to every exercise in the
`build_report` evidence and a top-level `progress_summary`. It is pure: it uses the
sessions the report already merged, so it makes no Hevy request, database write or
new table. The question it answers is whether a movement is moving, not what to do
about it; the coach and the athlete decide that.

Method: each exposure (one movement in one session) is reduced to its anchor, the
heaviest recorded-RPE working set, via `stress_index.session_anchor` (the same anchor
the stress index uses, so blank-RPE sets never count) and the e1RM that set implies.
The last 28 local days are compared with the 28 days before by the median e1RM of each
period: `progressing` at +2.5% or more, `declining` at −5% or more, `flat` between
(about one RPE half-step of rounding error), and `insufficient_evidence` with a
`reason` when there are fewer than three recent or two earlier usable exposures.
Medians keep one bad day or one mistyped RPE from moving the label. Anchors harder
than RPE 7 are required; lighter exposures (deloads) are counted in
`low_effort_exposures` rather than read as a decline. Warm-ups, conditioning sets,
blank RPEs and unknown loads are excluded and counted (`unusable_exposures`). These
thresholds are product heuristics, stated as such in the report limitations.

Each block also names the confounders the coach is told to check before suggesting
anything: `rep_range_shift` (median anchor reps moved by 3 or more), `entered_share`
(how much of each period used RPEs entered in the logger rather than imported),
`high_rep_exposures`, the best e1RM in the window and exposures since it, and the
last six anchor points. `progress_summary` carries the status counts and an
`attention` list of up to eight `flat` or `declining` movements (declining first),
with `attention_total` for the full count. Under context pressure the per-exposure
points are dropped before the summaries and the omission is recorded.

`BRIEF` tells the coach to raise the attention list in a training or weekly review
even when not asked (not in the daily interpretation), to check the confounders, and
to offer options such as holding, a rep-range or set-count change, a variation or a
phase change with what would change its view. A flat or declining label is context,
never a diagnosis or proof that a block should end. Existing frozen conversations
keep their original evidence. There is still no block or phase field on microcycles,
no rule that changes a plan, and no check of whether a past recommendation worked.
Tests: `tests/test_coaching_progress.py`, `rackbook/tests/test_stress_index.py`.

## Proposal outcomes in AI coach evidence (local, 2026-11-08)

`coaching_outcomes.py` adds a top-level `proposal_outcomes` list to the `build_report`
evidence: the latest five week proposals the athlete saved as drafts, newest first. It
is pure and read-only. `coaching.local_evidence` reads the logger's `plan_proposals`
rows (latest ten), their `mesocycles` rows and all of their `mesocycle_completions`
over the same `mode=ro` connection; nothing is written, no table is added and Hevy is
not contacted. A database from before `plan_proposals` existed simply has no proposals;
any other read failure still marks the local source `unavailable_or_incomplete`.

Per proposal: `stage` (`not_started`, `active_not_started`, `in_progress`, `completed`,
`archived_unused`, `plan_removed`), `edited_since_save` (plan revision above 1),
`sessions_planned` and `sessions_completed` (planned counts sessions that have
exercises), first and last completion dates, and `comparison`: `not_executed`,
`too_early` (under 28 days since the first completed session) or `available`. Only an
`available` comparison lists each proposed movement (up to eight) with its
`proposed_reps` and its progress status before and after: `before` is computed as of the
day before the save (UTC date) and `after` as of the report day, both with
`coaching_progress.assess_at` over the merged six-month sessions, so it works for
proposals saved before this feature and needs no frozen evidence. Each side carries
status, `change_pct`, `median_anchor_reps` and `entered_share`, so the coach can see
whether the rep range actually changed.

Limits, also in the report limitations and `BRIEF`: `after` covers everything trained
since the save, not only the proposed week; a proposal that was never started or was
edited says little about the proposal; nothing here shows that a proposal caused a
change. Without about eight weeks of history before the save, the `before` side reads
`insufficient_evidence`. Under context pressure the oldest outcomes are dropped first
and the omission is recorded. Existing frozen conversations keep their original
evidence. There is no UI for outcomes and no rule that changes a plan.
Tests: `tests/test_coaching_outcomes.py`, `tests/test_coaching_progress.py`.

## Automatic microcycle review (local, 2026-11-08)

A microcycle is one saved plan (one `weeks[0]`); it is not a calendar week and has no
Sunday/Monday rhythm. Before this change only the opening (look-ahead) review was
automatic, and only when a check-in belonged to day 1 of a plan. The closing
(look-back) review is now offered by the logger at the first confirmed pre-training
check-in after a microcycle's last day, whether or not that workout belongs to a plan.

`POST /training/session-checkins` adds `closing_review` (`{plan_id, name, completed_on}`
or `null`) beside the unchanged `weekly_review_eligible`. `session_checkins.closing_candidate`
decides it with reads only, inside the check-in's existing transaction. A microcycle
qualifies when every session in its document has a completion (the same predicate the
host's end-review requires; manual marks count and archived plans are allowed), its last
session started before this check-in but within 14 days of it (older microcycles are never
resurrected automatically), it is the most recently finished one, and no other check-in
has started since it finished. The check-in must have been confirmed before working sets.
That makes one automatic attempt per finished microcycle; the same check-in re-posted
(reload) gets the same answer, a later check-in gets none, and the manual request remains.

The browser (`rackbook/static/session-motivation.js`) then calls
`AICoach.reviewWeek(plan, 'end')` exactly like the manual link: the host's deterministic
conversation identity and the server-owned sequence-zero message mean a review that
already has turns is never resent. At a planned day 1 the closing review runs first and
the existing opening review follows (it can see the closing one in its prior coaching
excerpts). A failure never blocks confirming the check-in, logging or the opening review,
and shows a message with no automatic resend. If training has already started the review
is not run; an existing one is only shown. The result appears in the collapsed
Pre-training check-in card as "Finished microcycle · status" with a link to AI Coach.

The closing prompt and label now say microcycle and point the coach at `progress_summary`
and `proposal_outcomes`. Stored identities (`hevy-fatigue:weekly-review:<plan>:end`) are
unchanged. Tests: `rackbook/tests/test_closing_review_trigger.py`,
`rackbook/tests/test_closing_review_ui.cjs`, `tests/test_coaching.py`, and the mocked
`tools/check_weekly_coaching_browser.py`. Not changed: review evidence, pattern-stress
calendar-week grouping, plan activation or any automatic programming change.

## Skipping a day (local, 2026-11-08)

Until now a day you would not train could only be resolved with "Mark already completed", which reads as
trained, or by editing it out of the plan. Without that the microcycle never finished, so the automatic
closing review (and the manual one) could not run. The Planned workout box on the log page now offers
**Skip this day** beside "Mark already completed": one prompt with an optional note (for example where the
work went instead), local only, never a Hevy call. A skipped day is shown as "Skipped" with its note and
"Undo skip"; the microcycle cards count "N completed · M skipped".

A skip is stored in `mesocycle_completions` with `outcome = 'skipped'` and the optional `note`, so every "is the
day resolved" rule (finishing a plan, the end-review predicate, the next-check-in trigger, builder locks) works
unchanged, while every "was it trained" use (saved-workout and manual-mark counts, first completion date,
progress comparison) excludes it. The closing review's `week_context` adds `skipped_count` and
`skipped_sessions` (`session_id`, `name`, `note`, `skipped_at`) next to `manually_marked_count`, which no longer
counts skips; `plan_completions` and proposal outcomes carry the outcome (`sessions_skipped`, stage
`finished_with_skips`). `BRIEF` and the closing prompt say a skipped day was the athlete's choice and not
trained, is not by itself a failure, fatigue signal or motivation problem, and that its note is the athlete's own
words. A skip is compared with when a check-in was confirmed (not when the workout started), so skipping Day 4,
loading the next microcycle's Day 1 and confirming the check-in starts the review of the skipped microcycle
followed by the new opening review. Proposal-outcome timing is now reported in days
(`days_since_first_completion`). Tests: `rackbook/tests/test_skip_day.py`, `tests/test_coaching.py`,
`tests/test_coaching_outcomes.py`, `rackbook/tests/test_log_plan_selection.cjs`, and the mocked
`tools/check_weekly_coaching_browser.py`. Not included: skipping several days at once, automatic skip
detection, moving a day, or linking work done elsewhere to the skipped day.

## AI week proposals in the AI Coach (local, 2026-11-07)

The coach may now end a reply with one `plan-proposal-v1` fenced JSON block when the athlete
asks for a concrete week. `BRIEF` shows the exact format (the example is shared with the parser
and tested against it), limits movements to the report's new `known_movements` (up to 80 ids with
titles, last date, exposure count and saved-plan flag) and forbids weights: loads still come from
the athlete's TS/TM/RPE loading. The coach still cannot apply anything.

The AI tab hides the machine block from the reply text and adds a Proposed week card
(`rackbook/static/plan-proposal.js`, loaded with `training.js` and called through `trainingUrl`):
rationale, a diff against the active microcycle, the sessions, and validation issues. Everything
from the AI is shown as text. Preview is read-only. Save as draft is the only write: it creates one
new inactive microcycle and a provenance row through the logger (`rackbook/docs/rackbook-context.md`),
repeat saves reuse the first, and the athlete reviews and activates it on `/training/microcycles`.
No existing plan is edited and nothing is activated. ADR:
`docs/adr/0001-ai-proposals-become-drafts.md`. Tests: `tests/test_coaching_proposals.py`,
`rackbook/tests/test_plan_proposals.py`, `rackbook/tests/test_plan_proposal_ui.cjs`.
