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
