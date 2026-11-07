# Phase 1 integration and release record

This branch combines Hevy-Fatigue monitoring and the Rackbook workout workflow.
Production cutover is a separate action. No homelab services or source deployment
were changed during implementation.

## Provenance and baseline

| Source | Revision |
| --- | --- |
| Hevy-Fatigue starting local main | `7a82eb8` |
| Hevy-Fatigue fetched remote main, integration baseline | `5bef649275e81c589937786010ba854ea24a04f9` |
| Rackbook source (`531BBB-AR`) | `2e317280b07051e104c37a1126b8eff9c98b1d37` |
| Integration branch | `codex/rackbook-integration` |

Both starting worktrees were clean. Remote main was fetched before creating the
branch. The host baseline passed 45 Python tests and its JavaScript checks.
The source checkout's origin is `https://github.com/bross84/rackbook.git`;
`531BBB-AR` is its existing local directory name.
Rackbook's baseline ran 467 tests: one failure, one expected failure; every CJS
check passed. The failure was the legacy replay assertion that an incomplete
host check-in has fatigue score `0`. Current host monitoring correctly returns
`None`. Its imported regression asserts that exact current behavior, retaining
date freezing, future exclusion and source-file preservation assertions.

Tests initially stalled inside the Windows sandbox's TestClient execution;
verification used an execution context supporting the test client's local
threads/sockets. The installed host test runtime is Python 3.12; container
verification retains the project's Python 3.14 and pinned dependencies.

## Boundaries

`rackbook/` contains MIT-attributed source services, HTML, CSVs, icons, local chart
vendors, legacy planner and trial/replay helpers. `rackbook/LICENSE` retains the
original license; imported vendor attribution remains in `static/vendor/README.md`.
Internal imports are package-relative. Assets resolve from package files.

The host explicitly initializes its own SQLAlchemy schema, then the logging
schema, RPE CSV, single-week migration, placeholder cleanup, completed-plan
deactivation and journal recovery. Paths must identify distinct files, including
symlink/hardlink aliases. Logging uses stdlib sqlite3 and `RACKBOOK_DB_PATH`;
monitoring uses SQLAlchemy and `DB_PATH`. Settings and similarly named tables
remain independent. Source database files, encryption keys and `.env` were never
copied into this repository.

`credentials.py` retains the host encryption format and legacy plaintext
migration. Both clients/importer use the host credential, with the existing
file/environment fallback. Imported credential routes write only to the host;
old logging credential rows are inactive. The logging key is unnecessary in the
combined deployment, but stays in the old rollback backup.

Monitoring calculation files and input selection are unchanged. A deterministic
fixture containing same-day training, missing ratings and a monitoring gap was
run against an isolated archive of `5bef649` and this application; the full daily
and pattern response matched exactly. The regression fixture is
`tests/fixtures/monitoring-baseline.json`. Local exact sets never enter the host
tables. Saving requests the existing locked sync entry point after local commit;
sync/trial failures cannot fail the save. Hevy publication delays remain pending.

Trial observations, pinned model and shadow hashes are retained. The bridge
uses explicit `HEVY_FATIGUE_DB_PATH` and opens SQLite read-only. No historical
backfill or shadow regeneration occurs. Offline tools run as package modules;
the legacy host replay uses a separate offline process with the selected host
repository as its working directory, without import-path manipulation.

## Retained inventory

All source backend routes remain under `/training` with their suffixes and
models, except additive save-recovery fields. `training-routes.txt` lists them.

| Pages | Assets/services |
| --- | --- |
| `/training/log` | Touch keypad, timers, per-exercise units, plate loader, TS/TM, local drafts |
| `/training/microcycles`, `/training/mesocycles` | Single-week builder, activation, manual and saved completion |
| `/training/recent` | Hevy history with exact local RPE overlay and soreness edits |
| `/training/progress` | Bodyweight, e1RM and strength score |
| `/training/rpe-charts` | General and observed charts, assignments and historical chart import |
| `/training/stress`, `/training/stress/details` | Existing stress model, history and relationships |
| `/training/trial` | Stored prospective observations and frozen shadows |
| `/training/legacy` | Noncredential settings, trial toggle; retained legacy backend |

Packaged assets include all seven HTML pages plus legacy settings, both RPE CSVs,
Chart.js/Hammer/zoom vendors, stress-chart helper, PWA icons, manifest and worker.
The worker remains network-only and its default scope is `/training/`.

Logging data retained: `logged_sets`, exercise refs, TS/TM history, RPE tables and
assignments/history, cached templates, body measurements, microcycle documents,
aliases/backups/completion links, soreness, trial observations/shadows/notes and
all original legacy program/block/session tables. Startup adds the save journal;
it does not merge these with host tables.

Browser source keys identified: `logDraft`, `unit`, `restSecs`, `restEnd`,
`restTotal`, `mesocycleEditor` and the editor's retired `.weeks`, `.blankDays`,
`.beforeBlankDays` variants. The source currently deletes editor drafts on load;
the combined app persists editor drafts. Only the current `mesocycleEditor`
shape is imported, never an unvalidated retired migration backup. Combined keys
use `training.` prefixes. Legacy theme/unit preferences are also namespaced.

## Save contract

The combined UI persists a UUID before save and freezes the payload (including
end time) before the request. The journal stores canonical hash, validated input,
Hevy-normalized payload, TS rows, state, remote ID, timestamps and safe errors.
Database claims prevent concurrent POSTs with the same ID. An interrupted
`sending` becomes `uncertain` at initialization and never automatically reposts.

Required local records and `complete` commit in one transaction. Local failures
leave the acknowledged remote ID in `remote_saved`; retries only finalize.
Reconciliation reads Hevy and verifies title, timezone-normalized times,
description, ordered movements, notes and normalized sets, including upload
rounding and dropped RPE. There is no force-link path.

Recovery routes: `GET /training/workout-saves/{UUID}`,
`POST .../{UUID}/finalize`, `POST .../{UUID}/reconcile` with
`{"hevy_workout_id":"existing-id"}`. Pending/uncertain drafts stay frozen;
rejections can explicitly unlock a corrected draft with a new identity.
Old API callers may omit the UUID; their calls get individual journal entries
but cannot rely on draft retry deduplication. They retain HTTP error responses
when no remote save is known, so older loggers cannot clear failed drafts as
successes. This does not promise exactly-once remote delivery.

Deterministic plan/TS/payload validation failures for UUID callers are journaled
as `rejected` before any remote call. Field-level request validation occurs
before route execution; the UI records that explicit rejection and offers
correction after confirming there is no journal entry. A missing journal alone,
timeout or unknown response never permits correction of an ambiguous identity.
Correction is explicit, persists a new UUID, and removes the frozen payload only
after storage succeeds. Known local write-policy and missing-credential failures
remain `prepared`, allowing the same frozen request to resume after configuration.
Generic response errors remain `uncertain`; old uncertain records are never
automatically reclassified based on their error text.

## Verification commands

```powershell
python -X utf8 -m unittest discover -s tests
python -X utf8 -m unittest discover -s rackbook/tests -t .
node tests/test_recommendation_ui.cjs
node tests/test_draft_transfer.cjs
node tests/test_save_recovery_ui.cjs
Get-ChildItem rackbook/tests/*.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE) { throw $_.Name } }
docker build -t hevy-fatigue:phase1-local .
python -X utf8 -m uvicorn tools.preview_app:app --host 127.0.0.1 --port 18127
# Separate terminal, uses only the disposable mocked preview above:
python -X utf8 tools/check_training_browser.py
# Self-owned fresh mock server; stopped automatically after recovery acceptance:
python -X utf8 tools/check_training_recovery_browser.py
```

The preview mock replaces the Hevy client below the routes. Ordinary builds also
block outbound workout creation inside that client unless
`HEVY_WRITES_ENABLED=1`; `RACKBOOK_READ_ONLY_PREVIEW=1` blocks it regardless.
Never enable writes to inspect a copied production database.

Final results and remaining checks are recorded in `training-verification.md`.
See `training-cutover.md` for draft transfer, backup, switch and rollback steps.

The snapshot-specific `tools/verify_production_copy.py` verifies the operator's
20261101T025736Z backup hashes, starts disposable copies twice, fingerprints all
existing rows and compares full host outputs against archived deployed code at
three fixed dates. Run it only with networking disabled and read-only input
mounts; private working copies/reports belong outside Git. Production preflight
passed; final writer-quiesced backups remain a separate cutover requirement.

Latest review: preview middleware now matches app-relative paths for mounted
and nested logging requests, rejecting preview writes before the client/journal
while retaining reads. The Recent credential-error screen directs users to
shared host Settings. Host/integration count is now 74; see the current status
at the top of training-verification.md. Both old services are running again;
the previously staged uncommitted image is superseded and must remain unused.
The user authorized and completed branch publication as `25bba2b`, then requested
merge preparation. A PR-only test workflow now verifies the Python suites, all
JavaScript checks and write-disabled container startup without image publication.
Merge/deployment and real Hevy writes remain on hold. Tablet acceptance is deferred.

Current state supersedes that earlier hold: the user authorized PR #70's merge,
GitHub image publication, cutover and write enablement. Production runs the
`eb76a99` release by digest, with old Rackbook stopped. The exact running
configuration is tracked in `deploy/production.compose.yml`, distinct from the
write-disabled root development configuration. Read-only comparison with the
operator's captured CasaOS stack reports no differences. See `deploy/README.md`
for provenance and the GitHub-first update workflow; this tracking correction
does not restart containers, alter server files or change application data.

## RPErx / RPEact follow-up (local, 2026-11-04)

`EntrySet.target_rpe` carries the prescription into the frozen journal payload
and required atomic local set write. Existing `rpe` continues to mean actual
for Hevy, exact local history, stress, TS/TM and trend calculations. Startup
adds nullable `logged_sets.target_rpe` using a PRAGMA-guarded migration; existing
rows are preserved without inferring prescriptions. Requests lacking a target
omit the new null field before hashing, preserving legacy frozen-save identity.
New targets participate in the payload hash, including conflict protection.

The logger has separate accessible Rx/actual controls. Completion retains the
existing copy-target-if-blank default; actual can be entered before completion
or corrected afterward. Blank actual cleared after completion stays unrated.
The original target stays visible across actual edits, undo/redo and reload.
Completed/manual loads are unchanged. Draft transfer preserves both fields and
validates the new field in frozen payloads. Recent exposes the target only when
local/remote sets match the existing movement/count/reps/type checks; legacy
history retains its actual-only display. No host monitoring or trial rules change.

## Production update workflow (2026-11-04)

At the user's request, routine updates return to published `latest` followed by
`docker compose pull && docker compose up -d`. The deployment contract now
requires the correct latest image and an unblocked default pull policy. Existing
separate external volumes, database/key paths, settings and write guards retain
their strict checks. No application or model behavior changes in this follow-up.

## Frozen session evidence and descriptive review (local, 2026-11-04)

`session_review.py` owns explicit snapshot/evidence request models, pure review
calculation and read-only retrieval. `session_reviews` is an additive logger-only
table initialized by logger startup. Finalization writes its snapshot/actual/
versioned review in the same transaction as exact sets, TS, plan completion,
soreness and journal completion. Failure rolls back required local effects;
retry finalizes without reposting. New metadata participates in frozen identity;
absent new optional fields are stripped to preserve pre-upgrade request hashes.
No existing rows or frozen trials are regenerated.

`static/session-review.js` captures independent loaded-plan/repeated-workout
prescriptions and displays the read-only review. Set IDs survive deletion,
undo/reload/transfer; original missing sets stay in the snapshot and extra sets
receive new IDs. Original notes, fixed weights, plan revision/identity and RPE
curve are retained. Auto-weight calculation only gains passive suggested-load
recording. Actual RPE source and completion time are captured without extra
required taps. The LS toggle, manual/completed load stability and TS/TM remain
unchanged. Transfer validates both live and frozen metadata.

The review distinguishes original from final targets, completed work, omitted
and added working sets, and unknown data. Explicitly entered effort with a stored
percentage can supply e1RM estimates; copied targets are identified and excluded.
Endpoint change requires matching reps, effort, role and set type. Timing orders
the endpoints; completion spacing is not measured rest. Ad hoc and pre-upgrade
sessions do not receive invented initial plans. This increment does not compare
against prior sessions or produce block/programming changes.

## Deselectable e1RM/TM weight sources (local, 2026-11-05)

`auto_weights` is an additive, PRAGMA-guarded exercise_refs column with default
1, distinct from the unused legacy auto column. API models/store round-trip the
flag. Defaults preserve every existing movement's basis, LS choice, units,
rounding/rest/bar/chain settings and TS/TM data. Clicking an active source tile
disables automatic weights; clicking either tile when unselected enables it.
baseFor returns no calculation basis while disabled, including when LS was
previously on. No supplied/completed/manual weight is rewritten on deselection.

The logger persists autoWeights in drafts and consults the saved movement flag
for older drafts without that field. Draft transfer validates/preserves it.
Session capture uses the existing evidence shape with basis manual, no automatic
suggestion and LS off in this state. Extending that enum does not change legacy
serialized defaults or frozen-save hashes. Logging, actual RPE, TS/TM tracking
and descriptive reviews continue independently of weight-source selection.

## Provisional session advice (local, 2026-11-05)

New logger tables session_advisories, advisory_decisions and advisory_outcomes
hold immutable suggestions, append-only decisions, and separately observed saved
training. Startup initializes them idempotently. The host is opened read-only
through HEVY_FATIGUE_DB_PATH for bounded fixed queries of daily_readiness and
imported exercise history. No credentials/settings are copied or returned, and
no host table is changed. Exact local rows take precedence for matching workout
IDs; imported history without set-role provenance is supporting context, not a
capacity estimate. Dashboard/API display limits do not truncate these sources.

POST /training/session-advice captures one snapshot per save UUID/movement before
that movement starts. Current, incomplete and unavailable check-ins are distinct.
POST /training/session-advice/{recommendation_id}/decisions accepts four actions
with UUID idempotency, optional reason, explicit modified intent and optimistic
last-decision checking. Events are not overwritten. Accept/Modify never mutate a
plan or workout. Advice is provisional, versioned and evidence-labelled. Dismiss
reduces repeat suggestions for seven days; Not now only collapses this one.
Evidence is frozen at capture and is not silently regenerated by a refresh.

WorkoutEntry.advisory_links freezes exact recommendation/decision IDs with the
persisted request UUID. Absent links are omitted before hashing for legacy save
compatibility. Ownership, duplicate and decision-parent checks precede remote
I/O; foreign links are durably rejected. Decisions lock once a save journal
exists. Explicit correction of a rejected draft drops old advice links only after
successful new-identity persistence; sending/uncertain attempts never reset or
repost automatically. Advisory identifiers/reasons never enter the Hevy payload.

Required actual-dose records join exact sets, session review, TS, plan completion,
soreness and journal completion in one local transaction. Retry/finalize/reconcile
retain the existing remote-ID-first and read-only full-match guarantees. Outcome
records preserve decision versus execution, including different set/rep/RPE
results, omitted movements, ambiguous identities and late recorded timing. No
training improvement or causal adherence is inferred from a matching dose. Recent
and post-save review enrich the frozen training outcome with a read-only later
check-in; the next check-in may be incomplete and is never treated as zero.
Future feedback only associates a matched dose with the exact frozen decision,
not a later unacknowledged decision event. No historical trial is regenerated.

## AI coaching context and conversations (local, 2026-11-05)

Host routes: GET/POST /api/ai/conversations; GET
/api/ai/conversations/{conversation_id}; POST
/api/ai/conversations/{conversation_id}/messages. Creation accepts a UUID and
freezes the report once. Messages accept UUID, message, model and expected_sequence;
server-side history is authoritative. The legacy /api/ai/chat remains compatible.
No trainingUrl calls are needed for these host-owned routes; logger paths and
network-only worker scope remain unchanged.

coaching.py separates evidence and conversation logic from routes. Reports cover
six calendar months, not seven displayed workouts: exact local records override
imports by remote workout identity. Role/target/provenance gaps remain explicit.
Full-window summaries precede limits of 12 recent sessions/preserved prescriptions,
six raw exposures per movement, 10 saved plans (active first), 40 advisory decision
rows, and excerpts from three prior reviews/four completed turns. Character limits
remove older detail with notices, never silently change summary totals; oversized
remaining summaries fail clearly rather than send a misleading partial assessment.
Daily observations are date-only. Pretraining soreness is a distinct 0–3 input;
raw trial input may be read, but predictions/completions are never regenerated.

Host conversation tables remain separate from logger tables. Appends use optimistic
sequence checking and a short SQLite BEGIN IMMEDIATE transaction, committed before
provider I/O. Provider responses finalize through a separate short-lived host
session. Status is complete only after the provider's final marker and successful
persistence; partial/provider-error/failed-start attempts retain their own statuses.
Duplicate message IDs, stale sequence and pending messages are rejected before
provider calls. Lost responses require read-only reload; no automatic replay.
Crash-left pending turns remain visible; start a new review if they cannot finish.
New conversations include historical excerpts labelled as unverified prior claims,
not evidence that suggestions were applied or effective. Stored evidence dates
never advance silently during a follow-up.

The existing key storage and selected OpenRouter model are reused. No additional
credentials or settings are copied into logger storage. AI failure does not block
training. The UI strips executable markup, remote images and unknown reference
links; supplied references remain clickable. This does not establish factual
correctness of a model's prose. Review its claims against visible report fields.

## AI model catalog follow-up (local, 2026-11-05)

AI_MODEL_OPTIONS remains a curated static list in the vanilla host page; no new
runtime catalog dependency or route is introduced. Presets now carry display name
and base input/output price metadata, checked 2026-11-05 against OpenRouter's
public catalog. All listed models expose text output and /api/v1/chat/completions.
The model-price hint updates on both preset and custom changes. Removed/unknown
saved IDs retain their exact value via the custom field rather than being migrated.
The new-browser frontend default and backend legacy default are both
openai/gpt-6.1-terra. Explicit model IDs still take precedence, and saved review
turns continue recording the actual selected model. No routing or reasoning
parameter changes, model benchmarks, credential requests or billable tests added.

## Logger workspace follow-up (local, 2026-11-06)

`logger-layout.js` is a view controller over the existing logger. It receives draft,
card and save/render callbacks; it owns no calculation, database or remote-save
logic. Desktop uses instance-scoped selection, compact set inputs, previous cached
performance, existing exercise notes and an outline. The real loader and timer/save
controls are reparented, not cloned, and returned before redraw or narrower layouts.
The wide layout starts at 1900px to leave room for the 768px set table and two tool
rails. The grouped left navigation starts at 1100px; mobile retains touch geometry.
All existing training links/assets remain under `/training`; host destinations use
allowlisted hashes, including `/#settings`. No new frontend dependency is required.

`tools/check_logger_layout_browser.py` starts/stops its own mocked temporary app
on 127.0.0.1:18129. It loads six browser-local movements/23 sets, including repeated
template IDs, and verifies notes, loader replacement/selection, canonical weights,
Rx/actual completion, timer/UUID continuity across 390–2560px, real grip reordering
and reload. No Hevy workout is created by that check. The existing save/recovery
acceptance scripts still verify remote-mock publication and local finalization.
The design study retains unslop attribution in the stylesheet (Damir Sokolovsky,
@heydamir, CC BY 4.0). No release/deployment action is part of this follow-up.

## Dashboard navigation/layout follow-up (local, 2026-11-06)

The host's `static/index.html` now shares the logger's grouped left-navigation
design while retaining native host tab/hash handlers. The dashboard has three
independent columns at desktop widths >=1900px, a two-column tablet grid and a
single phone stack. Existing canvas/card nodes stay owned by their original
renderers; CSS changes their layout rather than copying or rebuilding charts.
All six dashboard cards and conditional joint advisories remain. The current-date
heading, sentence-case labels, calmer palette and 44px chart controls complete the
approved visual pass. Host Settings/AI/history and training navigation remain
accessible through the drawer or fixed rail; model and save logic are unchanged.

The new `tools/dashboard_preview.py` imports `tools.preview_app` before database
models and asserts that the SQLAlchemy bind matches the disposable DB_PATH.
`tools/check_dashboard_layout_browser.py` starts/stops this fixture on port 18130,
uses the shipped Chart.js in place of its matching CDN import, and verifies actual
canvas rendering, gaps, range/theme controls, responsive navigation and logger
links. No new runtime dependency, bundler, provider call or production action.

## Motivation check-in contract (local, 2026-11-06)

WorkoutEntry adds optional motivation: strict integer level 0..4, optional reason
fatigue/stale/life_stress/other, note up to 500 characters, optional timezone-aware
recorded_at and timing before_working_sets/after_working_sets/unknown. This is
coaching context, not a fatigue-model input. The new session_motivation table is
created idempotently only in logger SQLite. No existing tables are merged or
rewritten. Nullable/absent motivation is removed before canonical save hashing;
old journal payloads keep their exact identities.

The record commits in the existing required-local-effects transaction before
journal completion. It is excluded from the outgoing Hevy payload. Retry/finalize
retains remote-ID-first behavior and records exactly once. Session-review responses
add nullable motivation (with saved_at), including legacy/ad-hoc review responses.
Draft transfer validates live and frozen motivation data; malformed types, reasons,
notes or timestamps reject before replacement. Clearing resets the whole answer;
zero is an explicit Eager response. The frozen-save controls cannot change intent.

The host reads motivation_checkins through the read-only logger connection, with
client timing explicitly distinguished from server persistence time. Existing
six-month bounds, frozen conversation snapshots and context-size notices apply.
The assistant receives the recorded score/reason/note directly, separate from raw
daily ratings and pre-movement soreness. No new endpoints or external fetches are
required. Checks compare full monitoring snapshots before/after an answer to verify
unchanged fatigue output. Save recovery and exact local RPE behavior remain intact.

## Approved dashboard alignment and logger widths (2026-11-06)

Implemented the follow-up mockup after user approval: equal dashboard columns,
row-aligned cards and Fatigue Trend immediately beside Readiness on tablet and
desktop (immediately after it on phones). Replaced the three DOM column wrappers
with one ordered set of the existing cards; IDs, renderers, chart datasets and
API requests are preserved. Desktop uses three equal columns, tablet/narrower
desktop two, phone one. Minimum row sizes grow with wrapped content rather than
clipping it. The advisory remains conditional and spans all columns.

All logger exercise cards explicitly fill the same capped 880px column, including
mixed expanded/collapsed movements. The left navigation, compact set inputs,
loader ownership, timers, draft/save identity and training behavior are retained.
Only layout files, associated browser acceptance checks and release documentation
were updated in this follow-up. No database or schema migration is introduced.

## Chart-focused dashboard composition (2026-11-06)

After mockup approval, replaced the oversized Readiness card with a compact
summary strip and made the three charts the dashboard's primary content.
Fatigue Trend occupies a full row; the other two charts share a wide desktop
row at 2000px and above, stacking below that breakpoint. Pattern stress and
Recent sessions are retained below the charts. DOM order follows that reading
order, with the same IDs and existing render functions. Left navigation and
all logger files remain unchanged in this follow-up. No backend/model, schema,
storage, credential, API or save behavior is changed.

Mocked browser acceptance now checks this composition instead of requiring all
six cards to have equal widths: compact populated/missing readiness, full-width
trend, aligned equal secondary charts on wide screens, readable stacked charts,
secondary content placement, containment and navigation across 320–2560px.

## Required check-in and weekly review integration (local, 2026-11-06)

POST /training/session-checkins accepts session UUID, timezone-aware workout_start,
MotivationInput and optional planned_session. The logger-owned session_checkins
table is initialized idempotently. Confirmation validates plan membership and
returns weekly_review_eligible only for incomplete day 1 with a pre-working-set
response. Frozen save journals reject check-in edits. Data stays separate from
monitoring tables and frozen trial records; no new Hevy payload fields are added.

WorkoutEntry adds nullable checkin_required (literal true). Absent legacy flags
are omitted before hashing. Current UI supplies true, checks local confirmation
before working sets/new saves, persists the confirmed observation before freeze,
and validates it server-side before remote I/O. Required finalization links the
session check-in to the remote ID in the existing local transaction. Frozen legacy
payloads bypass new requirements; no identity replacement or automatic repost is
introduced. Draft transfer validates the added confirmation/flag shape.

POST /api/ai/week-reviews accepts plan_id, start/end kind and opening session UUID.
weekly_coaching.py reads logger data read-only; the host owns conversation storage.
UUIDv5(plan ID + kind) deduplicates captures and concurrent requests. The normal
server-owned /messages endpoint sends the initial assessment with sequence zero;
existing turns, including uncertain/failed ones, are never automatically resent.
A missing key or interrupted response is visible without changing workout inputs.
GET /api/settings/ai adds default_model for the logger's fallback selection.

Opening evidence includes the confirmed current observation even without a saved
workout. Closing capture requires all planned sessions completed/explicitly marked;
actual dose comes only from linked workouts. Its opening discussion includes the
first and latest five completed turns, bounded to 4000 characters per message.
Context budgets include the weekly section and retain existing omission notices.
Motivation is raw engagement context and cannot change fatigue or infer performance.

WeeklyCoach is a shared vanilla script at /training/static/weekly-coach.js. Host
AI requests use /api/ai; logger requests use trainingUrl. Explicit completed-week
links use /?coaching_week=...&coaching_kind=end#ai. The host replaces that request
with a saved conversation link after capture, preserving reload/follow-up behavior.
Links from opening assessments use coaching_conversation UUID with #ai. No new
framework, scheduler, model tool permission or automatic program-writing API.

## Daily interpretation integration (local, 2026-11-06)

Host-only daily_coaching.py reuses CoachingConversation/CoachingTurn; no new table
or migration and no logger write. POST /api/ai/daily-reviews accepts explicit date,
requires an existing nonfuture DailyReadiness record, and freezes a compact report
at UUIDv5(date + SHA256 of canonical date/eight rating fields). Concurrent captures
resolve to one identity. GET /api/ai/daily-reviews/{date} returns only the current
rating version or null, never captures/sends. Saved conversations remain accessible
through existing Coach routes, with Daily check-in labels in the conversation list.

The client starts after successful POST/PUT readiness, independent of scoring and
save success. It shares WeeklyCoach.reviewPrepared (selected/default model, existing
expected_sequence=0 turn protection and SSE persistence). Repeated captures/tabs
cannot automatically resend existing turns. If an edit arrives during a response,
the client rechecks the current identity afterward. Reload restores without billing.
Provider outage/missing configuration is shown separately from a successful save.
The existing log editor's open/active CSS class mismatch was fixed so rating edits
can actually open the modal; stress fields remain untouched.

Daily evidence includes exact current ratings, raw/smoothed scores, causal personal
range/coverage and recent daily scores. Training evidence ends before the check-in
date using existing deduplicated Hevy/Rackbook reporting. Compact context retains
four sessions, recent exercise summaries, 14 prior daily observations, motivation,
current saved plan intent and bounded prior programming-review discussions. Context
is capped at 36k characters with explicit omissions. Original check-in/trial/plan
records are not modified. Full/weekly review excerpts exclude daily conversations
so daily summaries do not crowd out prior programming discussions. Daily brief
separates tiredness/recovery/engagement, considers spacing/performance, rejects
low-fatigue-only load increases and treats the historical band as descriptive.
The daily reference pack additionally identifies Saw et al. (2016),
https://pmc.ncbi.nlm.nih.gov/articles/PMC4789708/; it does not validate app thresholds.

readiness_context.historical_ranges decorates a chronological replay without
altering any original field. Previous 84 days, eligible smoothed values only,
linear 10th/90th percentiles, median, observation count, observed span and missing/
ineligible count. A point requires 14 observations over 28 days; its own value and
future values cannot shift its range. GET /api/readiness/combined-history adds
historical_range and historical_position after replay, before days slicing. Raw
combined data remain available even when smoothed eligibility is insufficient.
