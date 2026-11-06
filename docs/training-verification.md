# Phase 1 verification — 2026-10-31

## Deployed configuration reconciliation

PR #70 merged as `eb76a998bfff57273e20508a3e6fc42f5b2ec8ee`; its GitHub image build
succeeded and published digest
`sha256:b6a4799f644714cf5379f6bbb5138cbf9d101ab58bfe0b8d0d7fdedee6aa5f22`.
The operator deployed that image, validated the running write-disabled app and
then explicitly enabled workout saving (`HEVY_WRITES_ENABLED=1`,
`RACKBOOK_READ_ONLY_PREVIEW=0`). Health is healthy; old Rackbook remains stopped.
No workout was submitted by deployment/enablement commands.

Final backups are at `/var/backups/hevy-phase1/final-20261102T004309Z-25328c25`.
The host snapshot SHA-256 is
`f060dda30fe8ba975171e77fc99081361feb67df9a4fc7a1e17c2d5a39a1dbfc`;
logger snapshot is
`dd262f59e3cb81da203378af58f2ff9cb54a99adcbdfa390d780288d9e1fc694`.
Operator's post-start audit confirmed both integrity checks, the matching host
key, and exact preservation of every original table. Host has 95 check-ins,
307 workout sessions and 4277 logs; logger has 104 sets, 14 TS rows, 7 completion
links, 13 snapshots and 2 shadows. Only the empty save journal was added.
Deployed LAN pages/browser checks passed; the operator confirmed Today, Plans
and Log Workout through authenticated Cloudflare. Tablet/PWA checks remain deferred.

The user requested correcting the configuration tracking gap without restarting
the app or changing data. `deploy/production.compose.yml` now represents the
captured active CasaOS stack, including all metadata, external storage/network,
image digest, healthcheck and approved write flags. Local Compose rendering
equals every field in the user-supplied server capture, without ignored fields
or normalization beyond JSON object key order. Canonical resolved JSON hash is
`f5a8c0389ff14452f63ff94f43305be04e7e204bb541dca2bcd8ffb38d221281`.

Added read-only validation/comparison tooling, eight drift/safety regressions
and PR CI coverage. Deployment files are excluded from application images.
This reconciliation changes Git-tracked files only; it does not claim to have
replaced the active server source files or recreated the container. See
`deploy/README.md` for the exact provenance and future GitHub-first workflow.

The following sections are earlier review/preparation evidence, not current
deployment authorization or status.

## Merge-readiness review — 2026-11-01

The user requested preparing the integration branch for merge, while keeping
deployment and real Hevy writes on hold. Fetched `origin/main` remains `5bef649`;
it is an ancestor of the reviewed integration commit `25bba2b`, so no rebase or
conflict resolution is needed. No additional application correctness issues were
found in the reviewed storage, credential, startup, save/recovery and host-sync
boundaries. Application code is unchanged by this merge-preparation follow-up.

Added `.github/workflows/integration-checks.yml` for PRs targeting main and
manual test dispatch. It has read-only repository permissions, no registry login
or publisher, and builds only a disposable test image. Tests run without external
network access, real credentials, production mounts or published ports. The
existing image-publishing workflow is unchanged; merging main would trigger it,
so this task prepares a PR without merging or dispatching publication.

The exact proposed CI commands passed locally: 74 host/integration tests, 467
logging tests with one existing expected failure, all 25 JavaScript files under
Node 22, and repeated startup/mounted asset/schema/preview write-block checks.
Workflow YAML, trigger/permission structure and embedded smoke-script syntax
were validated. Previous mocked browser and production-copy evidence remains
applicable because this follow-up changes only CI and documentation. GitHub's
hosted check result is separate and must be read from the PR, not inferred from
local results. No branch-protection rules or production settings were changed.

The initial hosted integration check passed, but the separate CodeQL alert gate
flagged case-sensitive script-extraction regexes in imported test harnesses.
These operate on trusted repository fixtures, not user HTML. Replaced the 14
duplicated extractors with a shared test-only helper that recognizes mixed-case
tags, closing whitespace and ignored closing-tag attributes. Added a regression proving mixed-case script bodies
are checked and invalid JavaScript still fails instead of being skipped. All
existing behavioral assertions remain intact. No alerts were dismissed or
suppressed; the PR's rerun determines the hosted security result.

Tablet/PWA checks remain explicitly deferred. Final fresh backups and logging
volume staging remain later release tasks. The superseded manually staged image
must remain unused. Existing standalone apps remain the production entry points.

## Earlier review and branch publication authorization

After the final testing/review pass, the user authorized committing the reviewed
changes and pushing only `codex/rackbook-integration` to GitHub. This does not
authorize a merge to main, image publication or production deployment. The
existing GitHub image workflow triggers only on pushes to main or manual
dispatch, not this branch push. Existing apps and databases remain in use for
the next workout; no production configuration is changed by branch publication.

The user confirmed both original apps are running again after a temporary
operator-controlled stop/restart. No combined app was deployed. The final-backup
and logging-volume staging block was not reported as run; the dedicated volume
was created and verified empty. Earlier image transfer/volume preparation was
premature release preparation, not a substitute for reviewed Git provenance.
The manually loaded `phase1-cutover-20261031-233737` image is superseded by the
review fixes below and must not be used for deployment. Do not continue the old
manual release sequence. A future release requires the user's code acceptance,
commit/push authorization and a build from the reviewed committed revision.

Latest local review results:

- 74 host/integration tests passed locally and in the Python 3.14 container.
- 467 imported tests passed locally and in the container, retaining the one
  documented pre-existing expected failure.
- All 24 JavaScript check files passed.
- Fresh mocked happy-path and recovery browser flows passed with no unexpected
  JavaScript errors. The permanent happy-path check now also verifies the actual
  `/training/` worker registration, no dashboard control, and the credential-error
  path to shared host Settings. All new temporary browser servers were stopped.
- Local Docker build/startup tests passed, with outbound networking disabled,
  temporary data and no production mounts.
- Host calculation functions/modules and pinned trial model remain preserved;
  paired guidance is synchronized, source Rackbook checkout remains clean, and
  `git diff --check` passes. No databases, keys or private exports are added to Git.

The review found and fixed one additional integration bug: preview middleware
matched standalone `/hevy/` paths but missed the host's `/training` prefix.
It now removes the mounted root before matching. The regression covers valid
and invalid POST/PUT/PATCH/DELETE requests through combined, standalone and
nested mounts, checks that neither client nor journal is touched, and retains
GET access. The real client's write-policy check was already blocking outbound
writes; this restores the earlier preview rejection as a second layer.
Also corrected Recent's obsolete instruction to paste a key into its disabled
form; its browser error path now directs users to host Settings.

No further actionable integration issues identified in this scoped review.
The user explicitly keeps physical tablet/touch, background alarm/wake-lock and
installed HTTPS PWA checks deferred. Those are not counted as passed. The
dev-PC walkthrough and production-copy/backup checks below already passed.
Final writer-quiesced backups, logging-volume population, image publication and
actual-origin post-deployment checks are future release tasks, not testing gates
to execute before committing. Nothing was committed, pushed or deployed.

## Earlier implementation and preparation evidence

Branch: `codex/rackbook-integration`, based on fetched main `5bef649`.
Source Rackbook: `2e31728`. The source working tree remains clean.

| Check | Result |
| --- | --- |
| Host baseline | 45 Python tests passed; existing CJS passed |
| Source Rackbook baseline | 467 tests; 1 failure, 1 expected failure; all 21 CJS passed |
| Final host/integration Python suite | 73 passed after the six review fixes |
| Imported Rackbook Python suite | 467 run; passed with the original 1 expected failure |
| JavaScript | All 24 CJS files passed: 21 imported, host monitoring, draft transfer and recovery UI |
| Monitoring fixture | Full daily/pattern response exactly matches isolated fetched baseline |
| Normal and full mocked Hevy sync | Exact local RPE remains 5; no local-set duplication or host input substitution |
| Container | Python 3.14 build passed with existing pinned host dependencies |
| Python 3.14 regressions | Review fixes: all 73 host/integration and 467 imported tests passed (original 1 expected failure retained) |
| Container startup | Both fresh schemas, repeated initialization, all mounted pages/assets, scoped manifest and client write block passed |
| Automated browser | Happy path and recovery: Headless Edge, 390×844 touch; expected mock saves/completions, no application JavaScript errors |
| Physical device / actual deployed volumes | Not performed; operator checks remain |

The source baseline failure was the legacy replay's expectation of score `0` for
an incomplete check-in. The current fetched host returns `None`; its imported
test now asserts that exact value while retaining date/future exclusion and
source-database hash checks. The original expected failure remains in
`rackbook/tests/test_session_route.py`; it was not introduced by this integration.

Recovery tests cover stable freeform/planned retries, changed-payload conflict,
concurrent database claims producing one remote call, timeout/lost response,
interrupted sending, committed remote acknowledgement plus local failure,
transaction rollback and replay-safe finalization, matching/mismatching read-only
reconciliation, optional trial/sync/status failures and late results that cannot
reopen completed entries. Mounted recovery endpoints are exercised directly.

Startup/data tests cover fresh and existing copies, repeated initialization,
distinct schemas, same-path rejection, WAL-consistent exclusive backups,
unchanged nonempty trial/shadow payloads, and shared encrypted credentials with
inactive logging credential rows preserved. The pinned recovery model and pure
Hevy payload builder are byte-identical to the source checkout.

Draft tests cover workout/editor round trips, exact weights/TS/notes/plan refs,
UUID persistence and frozen end time, invalid input leaving storage unchanged,
replacement confirmation, expired timers, storage failure and no API effects.

The automated phone flow submits the host check-in, opens Plans, deep-links a
workout into the logger, uses touch weight/reps keypad and RPE picker, completes
sets with a TS, switches units without changing completed kg, checks plates,
leaves/returns/reloads with the same timer and UUID, saves through a mock below
the route layer, verifies one completion and next pending day, opens Progress and
RPE Charts, returns to host Settings and tests unknown-hash handling. Screenshots
are generated under ignored `artifacts/phase1/` by the browser script. Third-party
host chart CDN requests were blocked for this isolated browser run; local
training chart assets were exercised. Existing host chart JavaScript regression
checks passed separately.

The Docker smoke container used no external network, no published port and tmpfs
databases only. It was removed after verification. The local preview uses only
temporary databases and a mock Hevy client. No real Hevy account was used, no
production database/key was copied, and no homelab deployment was changed.

The first container regression run was restarted with stack diagnostics after
appearing stalled; it was progressing through repeated SQLite schema creation on
Docker's slower temporary filesystem. The diagnostic run completed all 467 tests
in about 208 seconds. Final focused container checks use a tmpfs temporary directory.

Remaining controlled-cutover checks:

1. Verify deployed revisions, real volume/network names, consistent final
   database backups and matching key-file backups.
2. Compare production-copy record counts, latest TS, active plan/completion links,
   trial hashes and daily/pattern outputs at the same cutoff.
3. Export/import drafts on every device and verify the home-screen origin.
4. Run the physical-phone/tablet checklist, including alarm/wake lock, scrolling,
   keypad-to-set tapping, per-exercise units and installed-PWA worker scope.
5. Enable real workout writes only as the deliberate controlled cutover step.

Host repository guidance reserves commits for Brian's review; implementation is
left uncommitted, with no push or deployment. See [cutover](training-cutover.md)
for the separate before-write and after-write rollback procedures.

## Review fixes and second review

All six confirmed issues were corrected with regression coverage:

1. Stale-plan and TS validation rejections are durable journal records; explicit
   correction creates a new identity and uses current edits. Field-validation
   errors before the route also offer safe correction, without treating a
   timeout or a bare missing journal as proof of rejection.
2. Disabled writes and missing credentials are typed preflight failures. They
   leave the same identity/payload prepared and resumable. Generic post/response
   errors remain uncertain and cannot be automatically reposted.
3. Callers omitting a UUID receive non-success HTTP statuses for rejection,
   uncertainty and preflight failures. Known remote saves retain their successful
   response even when local finalization is pending. API rejection detail is
   preserved with the active credential redacted.
4. Workout imports validate string-valued logger inputs, movement identities,
   timestamps, cached reference shape and frozen requests before replacing
   storage. Invalid files leave the destination unchanged.
5. Editor drafts retain cleared/null numeric fields through export/import and
   restoration; malformed objects are rejected. Saving a prescription still
   requires its usual validation. Transfer controls sit above the editor so its
   sticky save bar cannot cover them.
6. Repeated finalization releases its write transaction before status refresh can
   write through a second connection. The regression uses a short SQLite busy
   timeout and verifies the refresh update actually succeeds, without duplicate
   sets or TS records.

The second review also added identity guards: delayed save or recovery callbacks
cannot clear a different draft loaded in the meantime. Existing same-ID payload
conflicts and uncertain-save protections remain in force.

The new phone-width recovery script exercises real server plan rejection,
request-field rejection, correction after reload, fresh identities/payloads,
unfinished editor restoration and export/import replacement confirmation. It
creates exactly two mock workouts and one plan completion, leaves plan data
unchanged during transfer, and reports no browser JavaScript errors. Its preview
uses temporary databases and a mocked client below routes and stops automatically.
Screenshots are under ignored `artifacts/phase1-recovery/`.

Final review-fix results: 73 host/integration tests passed locally and in the
Python 3.14 container; all 467 imported tests passed in both runtimes with the
original expected failure retained. All 24 JavaScript files passed. Both browser
flows passed. The rebuilt local image is `hevy-fatigue:phase1-review-fixes`.
Its network-isolated startup check verifies mounted pages/assets, repeated
initialization, database separation, prepared write-policy rejection and a
non-success response for legacy callers. Test containers and mock browser
servers were stopped and removed after verification; no production deployment,
commit or push occurred.

Second-review result: no remaining blockers identified in the scoped automated
review. Host monitoring functions are unchanged apart from startup wiring; its
monitoring modules/schema and the pinned trial model remain unchanged. Physical
device checks and production-copy/volume/key verification above still gate the
controlled cutover.

## Production preflight evidence (operator supplied)

The operator reported the dev-PC mock walkthrough passed; tablet acceptance is
deferred. No physical-device pass is inferred from this result.

Production inspection identifies host revision `1ce09768eda5252fc8bcc6c87768b8793d1b7470`,
image `sha256:a1d63ef2b1eef067ace922b438333b3073101536605541e151bcec9587145c97`,
volume `hevy-fatigue_hevy-data`, network `hevy-fatigue_hevy-net`, port 8125.
The difference from integration baseline `5bef649` changes only two documentation
files. Rackbook uses image
`sha256:c3ca2e3aff6c94928aa1c14eca1dd118a6b1cc408b5c7e3cff34f48b1dc95bf4`,
volume `rackbook_rackbook-data`, network `rackbook_default`, port 8126; its deployed
source revision remains unknown. Its host bridge mounts the host volume read-only.

Operator-created SQLite backup snapshots are under
`/var/backups/hevy-phase1/20261101T025736Z` on the homelab. Both reported integrity
`ok`, source/copy key equality, restrictive backup permissions and successful
read-only credential decryption in network-isolated containers (host: two
encrypted settings; logger: one; zero failures; both Hevy credentials encrypted).
No credential contents were shared.

| Snapshot | SHA-256 | Selected counts |
| --- | --- | --- |
| Host | `96cfcc96c57f1586d2d6fc9bc9b254783ec44345214e97c686cfc0308836db3e` | 307 workout sessions, 4277 workout logs, 94 readiness rows |
| Logger | `dd262f59e3cb81da203378af58f2ff9cb54a99adcbdfa390d780288d9e1fc694` | 104 local sets, 14 TS rows, 7 completions, 4 plans, 13 trial snapshots, 2 trial shadows |

These are preflight backups taken with the writers running, not final cutover
snapshots. No service stop,
deployment, production configuration change or Hevy write was performed by this
preflight. Existing production write-policy flags were absent in the supplied
inspection; this does not establish that the old standalone logger blocks writes.
The combined mock and all verification containers keep real Hevy writes disabled.

### Production-copy verification result

The operator downloaded the backup archive over SSH to the private directory
`C:\Users\bross\hevy-phase1-verification`, outside both repositories. Local
verification matched both database SHA-256 values above. Inputs were mounted
read-only; only separate working copies were initialized. Original backup copies
remained unchanged. No production service was contacted by the verification run.

`tools/verify_production_copy.py` ran current workspace code with the previously
verified image runtime (`sha256:ae23d6663362f82feffa160d3831aacb0244bee78b0f4c464bf76bc03c86ac15`),
Docker networking disabled, no published ports, a read-only container root and
an additional Python socket-connect guard. Both write-policy flags blocked real
Hevy writes. It initialized the combined application twice and resolved the
shared host credential successfully without printing it or contacting Hevy.

Results:

- Every existing host row remained identical, including settings and imported
  monitoring inputs.
- Every existing logging data row remained identical: all 104 sets (including
  21 RPEs below 6), 14 TS rows, 7 completion links, 4 plans with one active,
  cached references, assignments, soreness and body measurements.
- All frozen trial rows/hashes remained identical, including 13 snapshots,
  2 shadows, 10 starts and 2 skips. No observations were generated.
- The only new table was the empty `workout_saves` journal.
- One existing metadata value, `rpe_chart_source`, changed because the Windows
  checkout's user CSV has CRLF line endings and production's has LF. Both hashes
  were verified against those byte variants, all 520 RPE chart rows were exactly
  equal, and every other logging setting was unchanged. This is an explained
  fingerprint update, not a change to RPE percentages.
- Full daily/training-load and pattern responses matched the deployed host
  revision's code on the same snapshot at fixed cutoffs 2026-10-30, 2026-10-31
  and 2026-11-01, with no normalization or omitted response fields.

The first strict run flagged the metadata change; it was investigated rather
than ignored. The second run passed with the narrow byte-variant/table-equality
check above. Private report, working databases and full response comparisons are
under `C:\Users\bross\hevy-phase1-verification\runs\check-02`; no personal data,
database files or keys were added to the repositories. Disposable verification
containers removed themselves on exit.

Production-copy and backup preflight passes. Remaining operator gates include
final fresh snapshots after writer quiescence, per-device draft handling,
tablet/PWA acceptance (deferred by the user), and review of the exact cutover
Compose volume/network configuration. Rackbook's source SHA is still unknown;
its deployed image ID above is recorded. Nothing was committed, pushed or deployed.

### Deployment configuration and device-handling review

Added `docker-compose.cutover-review.yml` as a review-only initial configuration.
Local Compose v5.6.1 successfully rendered the merged configuration; assertions
verified the original project/container name, port 8125, external production host
volume/network names, separate external logging volume, original host key path,
removed inherited build and no implicit image pull. Both real-write blockers are
literal values and stayed disabled even when the render's env file requested
`HEVY_WRITES_ENABLED=1`. No Docker objects were created or changed by this render.
The operator reports homelab Compose v5.4.0 and supplied the active host
Compose/CasaOS render. Existing restart, icon label, CasaOS metadata keys, port,
volume and network match the documented configuration. A local merge fixture
verified metadata/label inheritance and the added logging mount against that
reported structure; unshared metadata values were represented by test sentinels,
not assumed production values. The operator then ran the full write-disabled
override against the active host Compose using homelab Compose v5.4.0;
`config --quiet` returned exit code 0. Deployment configuration review passes.
No image was pulled, volume created, configuration applied or service changed.
Image availability, final logging-volume staging and final quiesced backups
remain later cutover steps; this result is not deployment approval.

The operator clarified that the host uses Cloudflare and prefers to retain that
address for the combined app. Rackbook's existing Tailscale root proxy targets
8126; the separate 8444 proxy targets 3001. Neither route needs changing for the
combined Cloudflare endpoint. Device transition is from old Tailscale Rackbook
to Cloudflare `/training/log`, with no draft transfer needed while empty. Old
Tailscale service workers cannot control the distinct Cloudflare origin.

Draft-transfer and recovery JavaScript checks were rerun and passed. The runbook
now covers separate origin/profile inventories, competing drafts, open old
editor preservation and unjournaled old-save ambiguity. The operator confirms
only this PC and one tablet used the old Tailscale HTTPS origin, with nothing
unfinished. No transfer/export is needed while both remain empty; recheck if the
old logger is used again before cutover. No device-storage inspection is implied.

### Deployment image preparation

The operator built and exported the uncommitted workspace as
`hevy-fatigue:phase1-cutover-20261031-233737`, platform `linux/amd64`; the homelab
reports `x86_64`. Local inspection verified `HEVY_WRITES_ENABLED=0` in both the
Docker image configuration and the saved archive. Archive checksum and OCI
index/platform/config identity chain were independently checked. The missing
nonsecret preparation manifest was recreated alongside the archive outside Git.

- Local OCI index/image ID: `sha256:ced9a086530c228f1bea17f7f704ab2fbfca7e073d9ecb07be49b33f28f46801`.
- Linux/amd64 manifest: `sha256:03090aea57045caf16f2b720f2605560c6b7837138c20244702cf3503d3130a9`.
- Image configuration: `sha256:3fdf02cdab53c5c4a1614a013e6d1871126ef7b412e5ae2b6a908f52ff3ec6bd`.
- Export SHA-256: `532fe6982237fe99f43c7cfdd99d6ccc50b519cd61c5b7901fb81426054157ee`.
- Private directory: `C:\Users\bross\hevy-phase1-verification\image-20261031-233737`.

No container was started for the build/export step. The operator then transferred
the archive over SSH, reported `sha256sum --check` passed, loaded the image into
the homelab image store, and verified Linux/amd64 and disabled-write defaults.
The server image ID exactly matches the local OCI index ID above. Image import
did not start or replace a service.

Final isolated local verification of that exact immutable image passed: 73 host
tests, 467 logging tests with the original expected failure, repeated combined
startup, mounted pages/assets, distinct database schemas and training manifest
scope. A valid combined save request with both blockers active stayed prepared
with a disabled-write reason and created zero logged sets. All checks used
disposable data, no network access, no published ports or persistent volume
mounts; test containers removed themselves on exit.

Initial harness runs forced preview mode over mocked-save tests and were
incompatible with their intended request paths; normal test settings passed.
A further logging run with a read-only container root could not create the
legacy replay's temporary fixture under packaged data. Repeating with a writable
disposable container layer passed, without changing any test assertions or
application code. Those initial logs remain separate under ignored artifacts.

Image preparation and staging pass. Final writer-quiesced backups and actual
logging-volume staging remain future authorized cutover steps. Depending on
Docker's image store, a loaded image may
be identified by its OCI index or image configuration digest; verify the archive
and configuration identity rather than assuming the two digests are equivalent.
No commit, registry push, service stop or deployment occurred.

## RPErx / RPEact implementation verification — 2026-11-04

Local-only change; no commit, push, image publication or deployment. Existing
operator documentation/deployment edits present at task start were preserved.
All API/browser fixtures use temporary SQLite and mocked Hevy below routes.

| Check | Result |
| --- | --- |
| Host/integration Python suite | 78 passed; new regressions cover target/actual recovery with one remote post, target hash conflicts, pre-upgrade frozen hash compatibility, migration twice with unchanged historical rows, and invalid/nonfinite targets. |
| Logging Python suite | 468 run, OK with the existing one expected failure; added Recent target/actual response and mismatched-history protection assertions. |
| JavaScript | All 25 `tests/*.cjs` and `rackbook/tests/*.cjs` files passed; real rendered controls plus real LS calculation verify easier/harder effort, original target, fixed completed/manual loads, undo/redo and redraw. Transfer covers separate Rx/actual and frozen-payload target validation. |
| Mock browser happy path | Headless Edge: 390x844 touch and 1280x900 desktop. Separate controls, low/decimal actual effort, canonical weights, reload, one successful mock save, one plan completion, Recent showing both values, scoped worker and zero unexpected JS errors. Desktop direct typing verified independently of touch picker. |
| Mock browser recovery | Stale-plan correction, request-model rejection correction, retained pending identity, local recovery and unfinished editor transfer passed; zero JS errors. |
| Docker build/startup | BLOCKED locally: `docker build --tag hevy-fatigue:rpe-tracking-check .` could not connect to `dockerDesktopLinuxEngine` (pipe absent). No test image was built or started; container verification remains a release gate. |
| Physical device / deployed data | Not performed; existing normal-workout and physical PWA/tablet acceptance remain pending. |

Initial sandboxed Python attempts stalled in TestClient (including early errors)
and were stopped after the complete replacement runs passed outside the sandbox.
These are execution-environment limitations, not accepted baseline application
failures. The inherited expected failure remains unchanged. No assertions were
weakened. Disposable localhost previews were stopped after verification.

Behavior: Rx remains the authored target; actual drives subsequent LS weights
and existing actual-effort consumers. Completing a set with empty actual copies
the target, preserving the old no-extra-tap default; this is not an explicit RPE
confirmation flag. Historical prescriptions remain null. New targets are local
metadata, not sent to Hevy or inserted into host monitoring tables. Frozen trial
records and model rules are unchanged. Release/rollback follow-up is recorded in
training-cutover.md; session/block guidance and nutrition are outside this change.

Publication follow-up: the user authorized commit/push without local Docker.
The original LSe1RM toggle was verified unchanged; an added regression proves
that off preserves both e1RM and TM bases despite actual-RPE edits, and on
restores the previous actual-set basis. Targeted logger checks pass. Local
Docker is not a requirement for branch publication; container checks can run
in existing GitHub CI. No deployment is authorized by branch publication.

## Restored latest update workflow — 2026-11-04

The user explicitly requested restoring `docker compose pull && docker compose
up -d`. Production now uses the repository's published `latest`, with no
`pull_policy: never`. Rendered before/after comparison found exactly two changed
fields: service image and pull policy. All volume definitions/mounts, database
and key paths, settings/write flags, container identity, port, network and CasaOS
metadata match exactly. No app or model code changed.

All 10 read-only deployment configuration tests passed, including rejection of
blocked pull policies, incorrect images/local builds, storage swaps, changed
settings, changed ports and extra services. No local image build/start or real
DB experiment was performed. CI performs the existing broader verification.
The operator already reported fresh integrity-checked host/logging backups and
the matching host key. This records configuration preparation; server application
and physical-device acceptance must be reported separately after the operator
installs the tracked file and recreates the app.

## Descriptive session review verification — 2026-11-04 (local only)

The preceding latest/RPE release is operator-reported healthy: separate RPE
fields and the original toggle work, and existing data/settings remain intact.
That acceptance does not establish deployment or device acceptance of this new
session-review implementation. Existing unrelated local documentation edits
were preserved. No commit, push, publication or deployment occurred here.

| Check | Result |
| --- | --- |
| Host/integration suite | 81 passed. New coverage verifies one remote post across local failure/retry, rollback of review and all required local effects, durable original plan revision, frozen snapshot conflict protection, read-only review retrieval and ambiguous metadata rejection. Legacy hash compatibility remains covered. |
| Logging suite | 477 run, OK with one inherited expected failure. Nine new pure review tests cover original sets/reps, omissions/additions and removed movements, changed targets, copied/unknown/unrated effort, TS/back-off comparability, actual completion order, missing data and no invented ad hoc/legacy baseline. |
| JavaScript | All 26 files passed. New actual capture/display tests verify immutable loaded prescriptions through edits/deletion, original set IDs, suggested/manual loads, RPE provenance, reload/transfer validation, safe text rendering and nonblocking review-fetch errors. Existing real LS on/off and TM/e1RM adjustment, canonical weight, keypad, timer, confirmation and recovery assertions remain intact. |
| Mocked browser | Headless Edge 390x844 touch and 1280x900 desktop passed: separate fields, reload, one mock save and completion, preserved original prescription, entered versus copied effort, post-save description, Recent review retrieval and no unexpected JS errors. Separate fault/correction/unfinished-transfer recovery checks passed. |
| Visual QA | Inspected the rendered phone review with expanded set evidence; original/actual values, units, unknown data and descriptive limitations render without page overflow. Screenshot is ignored under artifacts/phase1/session-review-phone.png. |
| Docker | No local build/start, per the user's explicit preference. Container verification can run in existing PR CI after separately authorized publication; no local container result is claimed. |
| Physical device / deployed data | Not performed for this follow-up. No real Hevy workout or production database was used for testing. |

The review is versioned session-description-v1 and read-only after atomic local
commit. Original loaded targets/fixed loads/notes, plan identity/revision, RPE
curve and set identities are retained alongside actual evidence. No historical
prescriptions are reconstructed and no frozen trial rows are rewritten. Legacy
pending identities/payloads remain compatible. Ad hoc sessions explicitly have
no initial full-session baseline. Copied or unknown effort does not supply
performance estimates; like-for-like endpoint change requires matching reps,
effort, role and set type. Estimates are not fatigue measurements. Cross-session
comparisons and block/program changes are not implemented in this increment.

Publication follow-up (2026-11-05): the user authorized committing and pushing
this session-review change, opening a PR and checking GitHub CI. Merge, image
publication on main and deployment are separate from this authorization.

## Optional weight-source verification — 2026-11-05 (local only)

The user requested only that e1RM/TM selection no longer be forced. No new rep/
load progression rules or bodyweight calculations were introduced. Selecting an
active tile again leaves both unselected, stops automatic loads for that movement
and disables LS while preserving the remembered preference. Existing lifts keep
their existing selection and calculation behavior.

- Host/integration: 81 passed, including legacy frozen-save identity and recovery.
- Logging: 480 run, OK with the inherited one expected failure. New API/migration
  checks verify the off preference survives initialization and stays per movement,
  and the new column preserves every prior row/default. Manual-basis evidence
  remains compatible with actual-performance review tracking.
- JavaScript: all 27 checks passed. New real-control/calculation checks exercise
  deselecting e1RM and TM by mouse/keyboard, stopped LS/base calculations, unchanged
  supplied/manual/completed weights, and restoration on selection. Transfer and
  session capture preserve the off/manual state without changing frozen shapes.
- Mocked browser: phone/desktop acceptance passed, including both tiles off,
  disabled LS, RPE edits leaving weights fixed, reload, stored preference, fresh
  workout load, ordinary save/review and Recent. Recovery browser scenarios also
  passed with no unexpected JavaScript errors. Desktop screenshot inspected.
- Physical-device/deployed-data checks were not performed for this follow-up.
  No real database or Hevy account was used. Local Docker build/start was omitted
  per the user's preference; container CI can run after authorized publication.

Existing unrelated documentation edits were preserved. No commit, push, image
publication or deployment occurred in this implementation. Disposable mocked
preview servers were stopped after verification.

Publication follow-up (2026-11-05): the user authorized commit/push, opening
a PR and checking GitHub CI for this change. Merge/publication on main and
server deployment remain separate actions.

## Provisional session recommendations — 2026-11-05 (local only)

The user authorized building session suggestions, four feedback actions and
actual-outcome tracking without automatic programming changes. Existing unrelated
local documentation edits were preserved. No commit, push, publication or server
deployment occurred. All experiments used temporary databases and mocked Hevy.

| Check | Result |
| --- | --- |
| Host/integration | 85 passed. Coverage includes frozen legacy hashes, exact accepted/modified intent versus different actual sets/reps/entered RPE, unchanged input programming, foreign-link rejection before remote I/O, decision locking after freeze, conflict protection, atomic outcome rollback/finalization and one remote post across retries. Advisory metadata is excluded from Hevy requests. |
| Logging | 495 run, OK with one inherited expected failure. Fifteen new service tests cover immediate check-in-based tentative reductions, missing/stale/future data, history beyond seven workouts, read-only host queries, exact-local precedence, effort confirmation, capacity trends, manual-weight exclusions, immutable snapshots, append-only/idempotent/concurrent decisions, dismissal versus deferral, and later check-ins without rewriting captured evidence. |
| JavaScript | All 28 files passed. Actual advisory controls exercise Accept/Modify/Dismiss/Not now, unchanged workout prescriptions, recorded modified intent, stable links, no automatic repost after errors and frozen-save behavior. Recovery correction drops links bound to the rejected UUID; failed storage preserves the original identity and links. Existing source-off/LS/TS/TM, low RPE, canonical units, keypad/timers and save confirmation assertions remain intact. |
| Mocked browsers | Phone 390x844 and desktop 1280x900 passed. The browser records Not now then modified one-set intent, keeps the two-set workout intact, saves once and reports actual two sets differing from intent. Post-save review and Recent retain the linked decision and preserved prescription. Existing recovery/correction/unfinished-transfer flows passed. No unexpected JavaScript errors. |
| Visual QA | Inspected expanded provisional advice/decision controls on phone and the existing review follow-up. Screenshots remain ignored under artifacts/phase1. |
| Docker | No local build/start per the user's explicit preference. Container verification remains available in existing GitHub PR CI after authorized publication; no current container result is claimed. |
| Physical device / deployed data | Not performed for this follow-up. No real Hevy account or production databases were used. |

Initial Windows fixture cleanup failures were corrected by explicitly closing
stdlib SQLite handles, without weakening behavioral assertions. A repeated
browser run against an already-completed disposable fixture was reset to a fresh
mock server rather than changing its expected behavior. Temporary previews were
stopped after verification. No new unresolved application failure was accepted.

The seven-workout finding: main.py applies .limit(7) only to the dashboard recent
session list. /api/workouts/recent uses a separate count parameter (default 12).
Full and incremental import loops already walk through page_count. No import
history cap was changed. The advisory policy reads up to 90 days of stored local
and imported exercise history, excludes current/future training, and uses recent
rep-matched observations under its own explicitly provisional criteria. Missing
imported history is labelled, not silently treated as an empty training history.

Policy is provisional-session-v1. All thresholds are named product constants,
not validated personalized limits. Feedback currently adapts repetition through
dismissal and supplies later evidence; there is no automatic physiological-model
training or causal effectiveness claim. Advice does not require the legacy
12-marked-TS gate. Outcomes compare exact acknowledged intent with saved work;
acceptance alone is never an outcome. Later daily check-ins are read-only view
context and cannot regenerate historical trial/recommendation snapshots. All
original host monitoring models, cutoffs and trial timing/records are preserved.

Publication follow-up: the user authorized commit/push, opening a PR and
checking GitHub CI for this feature. Main merge, image publication and server
deployment remain separate actions.

## AI training-history coaching — 2026-11-05 (local only)

Implemented Review my training and persisted follow-up conversations using the
existing encrypted key, model selection and OpenRouter proxy. All automated
experiments use disposable databases, mocked Hevy and mocked provider responses.
No real database, API key, remote AI call, commit, push, merge or deployment is part
of this implementation. Unrelated existing documentation/deployment edits remain.

Reference pack reviewed at abstract/publication-record level on 2026-11-05:
- ACSM (2009), Progression models in resistance training for healthy adults:
  https://pubmed.ncbi.nlm.nih.gov/19204579/
- Larsen et al. (2021), subjective/objective autoregulation systematic review:
  https://pubmed.ncbi.nlm.nih.gov/33520457/
- Moesgaard et al. (2022), volume-equated periodization systematic review/meta-analysis:
  https://pubmed.ncbi.nlm.nih.gov/35044672/ ; abstract cross-checked against the
  authors' institutional record at https://researchprofiles.ku.dk/da/publications/effects-of-periodization-on-strength-and-muscle-hypertrophy-in-vo

These are bounded general principles with explicit applicability limitations,
not support for app-specific cutoffs or an individual phase-transition date.
Coaching prompts require report dates/fields for numerical claims and supplied
reference IDs/URLs for literature claims. The browser verifies citation destinations
and strips unknown clickable URLs/executable markup. Mocks verify evidence arithmetic
and plumbing, not the scientific accuracy of arbitrary live model prose.

Verification: all 12 new coaching tests passed, including >7 workouts, exact-local
precedence, sparse/incomplete monitoring, six-month boundaries, manual/unknown and
copied-target exclusions, rep/RPE comparability, context-size omissions, read-only
logger evidence, immutable capture, prior excerpts, stored model/follow-up, duplicate
message and stale sequence rejection, provider setup/error/partial failures and
logging availability. Full host/integration and logging suite results follow below.
All 28 existing JavaScript files passed. Mocked coaching browsers passed at 390x844
and 1280x900, including review generation, follow-up/reload persistence, original
evidence, interrupt/reload without another AI request, supplied-only clickable
references, markup sanitization and no horizontal overflow. Existing mocked workout
and save-recovery browser flows also passed. Temporary preview servers are stopped
by their harnesses. Screenshots remain ignored under artifacts/coaching.

Initial sandboxed tests could not open Windows sandbox temporary files; rerunning
outside that sandbox on the same isolated fixtures resolved the environment issue.
A test initially assumed the standalone logger initialized the separately owned save
journal; it now checks the actual logger tables for unchanged training. Browser
checks wait for initial review loading and distinguish clickable a[href] links from
labelled unverified anchor text. Behavioral expectations were not weakened.

No local Docker build/start per the user's standing preference. Physical-device,
production-data and live AI assessment quality/cost have not been verified. No
fatigue model or logging behavior was changed. Human review remains necessary.

Final automated results: 97 host/integration tests passed; 495 logging tests
passed with one inherited expected failure; all 28 JavaScript files passed.
Final mocked coaching phone/desktop rerun, existing training browser and recovery
browser checks passed. No listeners remained on preview ports 18127/18128/18129.

Publication follow-up: the user authorized committing/pushing the AI training
review changes, opening a PR and checking GitHub CI. Merge and deployment remain
separate actions. Unrelated local edits are excluded from the feature commit.

## AI model selector and value options — 2026-11-05 (local only)

Read-only catalog verification: https://openrouter.ai/api/v1/models . Official
OpenAI model/pricing guidance also checked at
https://developers.openai.com/api/docs/models and
https://developers.openai.com/api/docs/pricing . OpenRouter IDs and its listed
rates are authoritative for this integration; provider-specific charges may vary.
No user API key or training data was sent during catalog verification.

Snapshot USD per 1M input/output tokens:
- openai/gpt-6.1-terra: 1 / 5 (new-browser default)
- openai/gpt-6-luna: 0.10 / 0.50
- anthropic/claude-haiku-5.5: 0.10 / 0.50
- deepseek/deepseek-v4.1-flash: 0.045 / 0.50
- qwen/qwen3.8-flash: 0.15 / 0.47
- google/gemini-3.8-flash: 0.825 / 4.125
- openai/gpt-6.1-sol: 2 / 10
- anthropic/claude-sonnet-5.5: 2 / 10

No training-specific quality ranking is claimed. Budget/balanced/higher-cost labels
are selection aids, not proof of superior coaching or an exact per-review bill.
Existing saved/custom IDs are preserved; no automatic model replacement occurs.
Mocked phone/desktop browser checks passed for fresh default, removed preset and
custom retention, budget-price updates, selection persistence and actual selected
model recorded on review/follow-up turns. Existing saved evidence, interrupted
response handling and reference sanitization browser checks also passed. No new
unit tests merely mirror the preset list. All 28 JavaScript files passed.
Full Python suite results are recorded below when complete. No local Docker per
the user's standing preference; live provider quality/cost, physical devices and
deployed-data verification remain unperformed. No commit, push or deployment is
part of this local update; unrelated existing edits are preserved.

Final selector regression results: 97 host/integration tests passed; 495 logger
tests passed with the inherited expected failure; all 28 JavaScript files passed;
mocked coaching browser checks passed at 390x844 and 1280x900. No live AI calls.

Publication follow-up: the user authorized committing/pushing the model selector
refresh, opening a PR and checking GitHub CI. Merge and deployment remain separate
actions; unrelated local deployment/documentation edits are excluded.

## Session motivation check-in — local verification, 2026-11-06

Completed the optional session-level motivation question/reason/note and AI review
context. Concurrent logger-layout and pre-existing deployment/documentation edits
were preserved; this follow-up does not claim ownership of those edits. No real
Hevy account, production databases or live AI calls were used.

- Host/integration: 102 passed. New cases cover exact-once local motivation,
  exclusion from Hevy, atomic rollback and finalize without remote repost,
  unanswered/zero semantics, frozen payload conflicts, request validation and
  unchanged legacy hashes. Coaching evidence tests verify the exact answer and
  note reach the provider system context and compare the complete monitoring
  diagnostics snapshot before/after the motivation record: unchanged.
- Logging: 495 passed with one inherited expected failure.
- JavaScript: all 29 files passed. The new control test covers unanswered/zero,
  reasons/notes, draft restore, unchanged sets, late timing (including undo),
  frozen controls and clearing. Transfer tests retain the answer and reject
  invalid score/type/reason/note/timing before modifying storage.
- Mocked training browser: passed phone/desktop. Motivation remains after reload,
  sets stay unchanged, saved review displays the reason/note, and a newly captured
  host AI report contains the exact saved motivation record. Existing Rx/actual,
  source toggles, canonical weights, timer/UUID, one remote save and plan completion
  checks remain intact. No unexpected browser errors.
- Mocked AI coaching phone/desktop and save-recovery browser flows passed.
- Targeted reruns passed after the final transfer/timing assertions. git diff
  --check passed. Disposable preview servers were stopped by their harnesses.

Only saved workouts enter AI history. Unfinished motivation stays in the device
draft, and discarded/skipped sessions remain unknown. recorded_at/timing are
client-reported, not verified prospective measurements. Motivation remains separate
from all daily/pattern/trial models and weight adjustments. Existing frozen review
snapshots are not rewritten. No local Docker was run for this motivation task,
consistent with the user's standing preference; concurrent layout verification
is documented separately above. Physical-device/deployed-data acceptance remains
unperformed. No commit, push, publication or production deployment occurred.

The previous attempt to launch broad tests was not executed because automatic
approval review could not complete due to a usage limit. After the user's request
to resume, authorized isolated runs completed successfully as recorded above.

Publication follow-up: the user authorized commit/push, opening a motivation-only
PR and checking GitHub CI. The logger layout, its drag/loader/navigation changes,
layout assets/checker, and unrelated documentation/deployment edits are excluded.
Merge and production deployment remain separate actions.

PR isolation check: exported only the staged tree to a disposable ignored directory.
All 29 JavaScript files and the mocked phone/desktop workout browser flow passed
without logger-layout assets, navigation, rails, loader or drag hooks.
