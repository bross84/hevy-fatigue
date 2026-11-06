# Controlled Phase 1 cutover and rollback

## Current deployment configuration

PR #70 was merged as `eb76a99`; GitHub published `sha-eb76a99`. The operator
completed final backups, populated the dedicated logging volume, started the
combined app from that published image, verified Cloudflare access and exact
preservation of every original database table, then explicitly enabled workout
writes. The combined app is healthy; old Rackbook remains stopped.

The canonical tracked configuration is now `deploy/production.compose.yml`,
reproducing the operator's resolved three-file server configuration exactly.
See `deploy/README.md` for read-only comparison, current server-file provenance
and the GitHub-first update workflow. This tracking correction itself does not
restart/recreate anything, edit server files or alter data. Root development
Compose and the historical write-disabled cutover template are not production
configuration. New configuration changes must be reviewed through GitHub first.

The remainder records earlier preparation instructions and rollback procedures;
its historical authorization/status statements are not the current deployment
state. Do not rerun earlier backup/staging steps over existing data.

## Historical cutover preparation

Current state: return to testing/review. The operator restored both original
apps after a temporary stop. No combined app was deployed and no final staging
was reported. The new logging volume exists and was verified empty. Do not run
the stop/backup/staging sequence again until release is separately authorized.
Physical tablet/PWA acceptance remains explicitly deferred by the user. Code
acceptance and an authorized GitHub commit/release workflow precede future
cutover work; a manually transferred uncommitted image is not the release path.

These instructions prepare a later operator-controlled switch. Do not run them
against production as part of implementation or testing. Keep access on the
existing private network; retain container `hevy-fatigue`, port 8125 and its
existing network/CasaOS configuration.

## Reviewed configuration, not yet applied

`docker-compose.cutover-review.yml` is an additive, initial write-disabled
override for the repository Compose file. Render it only during this review;
no `up`, `down`, restart, volume creation or service stop is authorized yet.
It requires Compose support for `!reset`; local Compose is v5.6.1 and the
operator reports homelab Compose v5.4.0. The final merged homelab validation
returned exit code 0. No configuration was applied.

| Item | Reviewed value |
| --- | --- |
| Project / container | `hevy-fatigue` / `hevy-fatigue` |
| Image | Required `PHASE1_IMAGE`: reviewed immutable image ID or repository digest; never infer from `latest` |
| Host storage | External existing `hevy-fatigue_hevy-data` at `/data` |
| Logging storage | External dedicated `hevy-fatigue_training-data` at `/training-data`; created and verified empty, not populated |
| Host database / key | `/data/hevy_fatigue.db` / `/data/app.key` |
| Logging database | `/training-data/rackbook.db` |
| Bridge | `/data/hevy_fatigue.db` |
| Network | External existing `hevy-fatigue_hevy-net` |
| Port | Existing 8125 to container 8000 |
| Write policy | Literal `HEVY_WRITES_ENABLED=0`, `RACKBOOK_READ_ONLY_PREVIEW=1` |
| Build / pull | Inherited build removed; `pull_policy: never` |

The override's external declarations refuse empty replacement volumes or a new
network. The logging volume must later be deliberately staged with the final
SQLite snapshot before any start; neither old Rackbook storage nor its key is
mounted writable into the combined app. The host keeps its original data/key
volume. `PHASE1_IMAGE` must exist on the deployment host before a future start;
the development machine's image ID is not evidence that it exists there.

The prepared image has now been loaded (not started) on the homelab as
`hevy-fatigue:phase1-cutover-20261031-233737`. The operator verified server image
ID `sha256:ced9a086530c228f1bea17f7f704ab2fbfca7e073d9ecb07be49b33f28f46801`,
matching the local reviewed artifact, Linux/amd64 and `HEVY_WRITES_ENABLED=0`.
That image is now superseded by later review fixes and must not be selected for
deployment. A future `PHASE1_IMAGE` must identify the release built from the
reviewed committed revision. Loading an image does not stage the logging volume
or authorize a service start. See training-verification.md for historical image
tests/checksum and the current review status.

Local config rendering confirmed both blockers remain set even with an
environment file containing `HEVY_WRITES_ENABLED=1`. Enabling real writes later
requires an explicit reviewed configuration change to both blockers; an `.env`
edit alone cannot enable this override. No write-enabling override is supplied.

Production's active host Compose file is
`/var/lib/docker-data/AppData/hevy-fatigue/docker-compose.yml`. The old Rackbook
uses its sibling `rackbook/docker-compose.yml` plus
`rackbook/docker-compose.fatigue-bridge.yml`. Host environment names show no
extra user-configured variables beyond `DB_PATH` and `TZ`; it has an `icon` label
that the repository base file does not contain. Preserve this label and all
CasaOS metadata by using the active host Compose as the base for the future
override, rather than replacing it with the repository base. The override now
explicitly adds the logging mount even when the deployed base lacks that mount.
The operator's active-file render confirms `restart: unless-stopped`, the
existing port/mount/network values, the `icon` service label, and top-level
CasaOS keys `author`, `category`, `hostname`, `icon`, `index`, `is_uncontrolled`,
`port_map`, `scheme` and `title`. Keep the current icon, custom title
`hevy-fatigue`, index `/`, port map `8125`, scheme `http`, empty hostname and
category `self`. The CasaOS launcher scheme describes its local port; it does
not replace or reconfigure the external Cloudflare HTTPS endpoint. Preserve
the unshared author/uncontrolled values by inheritance, not by inventing them.
A local merge fixture verified complete CasaOS/label preservation, unchanged
port/restart and the added logging mount against the reported structure,
including the empty IPAM object. The operator's merged homelab render passed
with exit code 0. This does not verify image availability or staged-volume contents.

The operator confirms Hevy-Fatigue uses Cloudflare, while Rackbook uses Tailscale.
The combined app retains the existing Cloudflare host origin, with training at
`/training/log`; no Tailscale or Cloudflare routing change is planned. Current
Tailscale serve routes are `https://ubuntu-server.taildbe131.ts.net/` to
`http://localhost:8126`, and port 8444 to `http://127.0.0.1:3001`. Leave both
routes and the existing Cloudflare tunnel untouched during review and cutover
unless a separately authorized requirement arises. Old-service retirement is
not authorized by this review.

For local render only (using a private env file that sets `PHASE1_IMAGE`):

```sh
docker compose --env-file /path/to/review.env -f /var/lib/docker-data/AppData/hevy-fatigue/docker-compose.yml -f /path/to/docker-compose.cutover-review.yml config --quiet
```

This validates syntax, not the existence or contents of external volumes/images.

## Draft transfer on each device

First inventory every device, browser profile, private session and installed
home-screen app actually used. Record its exact origin, including scheme and
port: LAN, Tailscale and HTTPS shortcuts may each have separate storage. Do not
infer that an empty draft at one address means another address/profile is empty.
The final target origin is the existing Cloudflare host origin plus `/training/log`;
the mocked preview origin is only for practice and is not the transfer target.
The old Tailscale origin and new Cloudflare origin have independent browser
storage and service-worker registrations. The old root-scoped worker cannot
control the Cloudflare host. Do not delete site storage or unregister workers
during this review. At cutover open the Cloudflare training URL directly on both
devices and replace an old Rackbook shortcut if used; its old `/log` URL and root
manifest do not identify the new `/training/log` app. Verify the new training
manifest/worker scope is `/training/` on the Cloudflare origin.

For the current review, do not save workouts, discard drafts, reload an open
old editor or remove home-screen apps. In each already-open old page, this
optional console snippet reads only the known draft keys and reports presence;
it makes no API calls and changes no storage:

```javascript
(() => {
  const read = key => {
    try { return {value:JSON.parse(localStorage.getItem(key)), invalid:false}; }
    catch (_) { return {value:null, invalid:true}; }
  };
  const workout=read('logDraft'), editor=read('mesocycleEditor');
  const form=document.getElementById('editor');
  console.log({
    origin:location.origin,
    workoutDraftPresent:!!workout.value,
    workoutDraftUnreadable:workout.invalid,
    workoutHasIdentity:!!workout.value?.client_workout_id,
    workoutHasFrozenRequest:!!workout.value?.frozenSave,
    storedEditorPresent:!!editor.value,
    storedEditorUnreadable:editor.invalid,
    editorCurrentlyOpen:!!form && !form.hidden
  });
})();
```

Also ask whether Save was ever attempted for each retained draft. The absence of
an identity/frozen request is not evidence of non-delivery: the old logger has no
durable save journal. A timeout, closed page or lost response from an old save is
a blocking ambiguity. Preserve the draft and investigate the existing remote
workout and local records read-only before transfer/resubmission. Importing it
and assigning a UUID does not deduplicate a previous unjournaled remote save.

| Device / profile / exact origin | Workout present | Old save ever attempted / outcome | Open unsaved editor | Export retained / verified | Final import verified |
| --- | --- | --- | --- | --- | --- |
| Dev PC / existing browser / `https://ubuntu-server.taildbe131.ts.net` | None, operator confirmed | No uncertain outcome reported | None, operator confirmed | Not needed while empty | Not needed while empty |
| One tablet / existing browser or shortcut / same Tailscale HTTPS origin | None, operator confirmed | No uncertain outcome reported | None, operator confirmed | Not needed while empty | Not needed while empty |

The operator reports only those two devices and nothing unfinished in Rackbook.
This is device-owner confirmation, not automated access to either device's
storage. Recheck both immediately before cutover if Rackbook is used again.

Export one file per origin/profile and keep both source and destination drafts
until verified. Do not merge competing device drafts by importing over one
another; preserve each export and decide which draft to continue. Inspect a
replacement prompt deliberately. Exports contain workout details: keep them in
private device storage, not Git or chat attachments. Re-export after subsequent
edits before the eventual final snapshot. No draft absence/export/import is
certified until checked on that actual device/profile.

Before stopping Rackbook, finish its workout or export the draft on **every
phone/tablet/browser profile**. Storage belongs to the old origin and is not
accessible from the new address. Run this small helper in the old Rackbook page's
browser console; it reads only the identified workout/timer/unit keys and never
calls Hevy or modifies the old repository:

```javascript
(() => {
  const draft = JSON.parse(localStorage.getItem('logDraft'));
  if (!draft) throw Error('No workout draft on this device.');
  const data = {draft, unit:localStorage.getItem('unit') || 'kg',
    restSecs:localStorage.getItem('restSecs'), restEnd:localStorage.getItem('restEnd'),
    restTotal:localStorage.getItem('restTotal')};
  const blob = new Blob([JSON.stringify({version:1,type:'workout-draft',data},null,2)],
    {type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='rackbook-workout-draft.json'; a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
})();
```

The inspected source does **not** persist current microcycle editor changes and
clears old editor backups at page load. Save the plan normally before leaving
the old editor. A plan save does not complete a workout. If a current editor
snapshot is present in browser storage from an earlier version, export only that
known key (never dump all localStorage):

```javascript
(() => {
  const data=JSON.parse(localStorage.getItem('mesocycleEditor'));
  if (!data) throw Error('No stored editor draft. Save the open plan before leaving.');
  // Accepted current shape: {plan, wi:0, si:<selected day>, assignmentCatalog:{...}}.
  if (!data.plan || !Array.isArray(data.plan.weeks))
    throw Error('Retired editor format. Keep this backup and save the plan in the old editor.');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify({version:1,type:'microcycle-editor',data},null,2)],{type:'application/json'}));
  a.download='rackbook-editor-draft.json'; a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
})();
```

In the combined app, open Log Workout or Plans → **Transfer device draft**.
Export creates the same versioned JSON. Import validates the whole file before
storage changes and asks before replacing an existing draft. It preserves exact
canonical kg, checked sets, TS, refs, notes and UUID/frozen payload. Old workouts
without a UUID receive one when restored. Expired timers remain expired. Import
does not post, activate a plan or create completion records. Reload restores the
imported draft. Keep the export until the saved workout and exact local records
are verified.

If a transferred draft has a pending save, use its recovery status first. A
`remote_saved` draft offers local retry. An `uncertain` draft needs the existing
Hevy workout ID for read-only reconciliation. Do not start a new save identity
merely because the response was lost. Definite rejections expose an explicit
correction action. This includes local plan/TS validation failures. Correction
retains the edited sets but creates a new save identity and a fresh payload.
If writes are disabled or credentials are missing, the attempt stays prepared:
fix the configuration and use **Resume prepared save** with the original identity.
Do not reinterpret older uncertain records as prepared based only on an error
message.

## Operator checklist

1. Record the **deployed** source/image revisions of both containers. Inspect
   actual mounts (`docker inspect hevy-fatigue` and `docker inspect rackbook`),
   existing network, CasaOS metadata and paths. Do not assume volume names from
   development. Record the container environment without sharing secret values.
   Confirm which volume owns `/data/app.key` for each service.
2. Create consistent timestamped backups of both databases using SQLite's backup
   API, including WAL content. Use `tools/backup_sqlite.py SOURCE NEW_BACKUP` in a
   runtime that can read the volume. It refuses to overwrite a destination and
   runs `PRAGMA integrity_check`. Keep each matching key file with its respective
   backup, with restrictive permissions. Never print key contents. A database
   dump alone is insufficient to restore encrypted host settings.
3. Finish/export each device's drafts using the preceding instructions. Save
   unsaved old microcycle edits before navigating away. Record daily/pattern
   outputs from the current host for the same cutoff date and data.
4. Stop the **old Rackbook writer** and keep its container/volumes recoverable.
   Do not delete anything. Stop the host briefly for its final database/key
   snapshot if settings are being changed. Retain the original host volume and
   encryption key together.
5. Make the final consistent logging snapshot with the backup API after the old
   writer is stopped. Copy that snapshot into a **new dedicated logging volume**
   as `rackbook.db`. Do not mount the original logging volume writable in both
   applications. Keep the old snapshot/key pair as rollback material.
6. Build the reviewed revision. Confirm Compose resolves the **existing host
   volume**, not a newly named empty replacement. The combined service mounts
   existing `hevy-data:/data` and separate `training-data:/training-data` with
   `DB_PATH=/data/hevy_fatigue.db`,
   `RACKBOOK_DB_PATH=/training-data/rackbook.db`,
   `HEVY_FATIGUE_DB_PATH=/data/hevy_fatigue.db`, `TZ=America/New_York`.
   First start with `HEVY_WRITES_ENABLED=0`. Preserve existing tunnel/network
   access, name, port 8125 and CasaOS metadata. Use an override with `external:
   true`/`name:` for discovered existing volumes where needed; inspect
   `docker compose config` before starting.
7. Run `tools/data_inventory.py` against before/after **copies** and compare
   counts, latest TS values, active plan, completion links and trial hashes.
   Startup legitimately adds journal/schema/migration setting rows and may
   deactivate a fully completed plan; investigate all other differences.
   Existing trial payload hashes must remain identical. Check the logger's
   previous sets and exact low RPEs. Check cache/exercise references and units.
   The verified preflight also identified an LF/CRLF-only `rpe_chart_source`
   fingerprint change: accept this only when both fingerprints match the chosen
   CSV byte variants, every RPE chart row is identical, and other settings are
   preserved. Do not dismiss arbitrary setting changes as metadata.
8. Verify the same daily and pattern outputs against the captured host baseline,
   at the same date/cutoff and with unchanged check-ins/Hevy data. The deterministic
   fixture regression is additional evidence, not a replacement for this
   deployed-data check. Ensure same-day training remains excluded where intended.
9. Import drafts on each device, resolving replacement prompts deliberately.
   Confirm weights, checked sets, TS, notes, plan identity and remaining timer.
   Uninstall/re-add an old home-screen shortcut if it points to the old origin.
   The combined training manifest starts `/training/log`; its worker scope is
   `/training/` and cannot own the root dashboard.
10. Perform the phone checklist below with mocked/disposable data first. Only
    after save-recovery regressions pass and all operator checks succeed, set
    `HEVY_WRITES_ENABLED=1` for the controlled cutover. Confirm the shared host
    credential through Settings; never re-enter it into logging storage.
11. Keep the old deployment stopped, with source, image and backup/key pair
    available. Record the cutover timestamp and first combined-app workout ID.
    No deletion or automatic retirement is part of this phase.

For volume copies, mount the old volume read-only and a separate backup directory
or new destination volume. Example **inside a maintenance Python container**:

```sh
python /app/tools/backup_sqlite.py /old-data/rackbook.db /backup/rackbook-final.db
python /app/tools/data_inventory.py /backup/rackbook-final.db
```

Do not use `cp rackbook.db` against an actively written SQLite database while
ignoring its WAL. Copying the already closed, verified backup artifact to the new
volume is safe. Volume names and maintenance-container commands must use the
actual names established in step 1.

## Physical phone/tablet checklist

Record device/browser/version separately from automated browser results:

1. Today → submit/review check-in → Plans.
2. Load a selected pending day; confirm that loading/discarding does not complete it.
3. Enter weight/reps/RPE by touch. Tap set completion with keypad open and verify
   the tapped row stays under the finger. Verify TS pins e1RM.
4. Switch page and per-exercise kg/lb; completed canonical weights stay fixed.
   Inspect plates and warm-up removal.
5. Start timer, leave and return; reload and restore the same draft/identity.
   Test the alarm and wake-lock behavior on the physical device.
6. Save once. Confirm exact local sets, TS/TM and one plan completion; next pending
   day appears. Check a low RPE remains exact after normal and full monitoring sync.
7. Use disposable mocks to exercise uncertain-save and local-finalization recovery.
8. Open Progress, Recent, Stress and RPE Charts; return to Today and Check-in History.
   Settings must open the host tab. Revisit the optional trial only through Settings.

## Rollback

**Before any new combined-app writes:** stop the combined service and restart the
prior host/logger deployments against their original volumes and matching keys.
Keep the prepared copies for diagnosis. Do not run two logger writers.

**After new writes:** first stop the combined writer and back up its updated
logging database consistently. Preserve new host check-ins/settings and its key
as well. Transfer the updated logging database back to the old logger's intended
volume **before** restarting it. Added journal tables may remain; the old logger
ignores them. Keep the old logger's matching encryption key and original
credential rows (inactive but preserved by the combined app). Confirm record
counts, TS, plans and completion links before resuming. Never restore an older
logging backup over new workouts or repost them from an exported draft.

The old logger does not understand the new save journal. Resolve every pending or
uncertain combined save before using its draft in the old app; otherwise return
temporarily to the combined app for verified reconciliation/local finalization.
Maintain a copy of the updated database and all device exports until recovery is
confirmed. If host data must be restored, preserve its newer check-ins/settings
instead of replacing them with a stale snapshot.

## RPErx / RPEact release follow-up (not deployed, 2026-11-04)

The user authorized committing and pushing this follow-up without local Docker.
Local Docker is not required for publication of the branch; existing GitHub CI
can verify the container runtime. Before a separately authorized deployment, back
up both databases with matching rollback key material under the existing procedure.
Logger startup adds only nullable `logged_sets.target_rpe`; it does not backfill
historical targets or alter monitoring tables. Keep the new logging database and
all pending journals on rollback; do not remove the column or restore an older
snapshot over newer saves. Older code does not record new target values.

Pending/frozen saves from before this upgrade must retain their UUID and payload.
Do not replace them to add targets: the server preserves legacy hashes and can
finish their existing local effects with an unknown prescription. Before changing
versions, preserve/export unfinished device drafts and resolve ambiguous saves
using the existing read-only reconciliation procedure. Verify the physical
PWA/tablet controls separately: Rx 6, actual 5 and then 7 should retain Rx 6 and
the performed weight while moving eligible next-set suggestions up/down. Check
reload and Recent history during the next authorized normal workout; do not
create a production test workout. No deployment or device acceptance occurred here.

## Routine latest-based updates (2026-11-04, supersedes image-pin steps above)

The user authorized restoring `docker compose pull && docker compose up -d`.
Use the reviewed `deploy/production.compose.yml` with the latest image and no
`pull_policy: never`; initial installation must retain the existing external
volumes, network, project identity and all settings. After installing it once,
future published app updates require only pull and up from the server's existing
Compose directory. No `down -v`, volume removal or database reset is needed.

The operator has reported fresh integrity-checked backups of both databases and
the matching host key for this update. Preserve these and the old image; do not
repeat backup work solely because the image reference changes. Finish/export
active workout drafts before recreation. Verify running health and existing
history/settings afterward, followed by the RPE controls; normal workout/device
acceptance remains separate. Rollback can select a known old image with the same
current volumes; never overwrite newer workouts with a stale database snapshot.

## Session-review release follow-up (local only, 2026-11-04)

Routine deployment continues to use latest with pull/up; do not restore digest
pins or pull_policy: never. This follow-up adds the logger-only `session_reviews`
table. Existing DB/key paths, external volumes, settings and host monitoring are
unchanged. Old histories/frozen trials are not backfilled. Keep newer logging
records and pending journals on rollback; older application images do not record
session-review evidence, and a stale backup must not overwrite newer workouts.

Finish or export active workout drafts before updating. Existing drafts and
frozen save identities remain valid and must not be replaced to add snapshots;
those without a captured initial prescription show review unavailable. On new
sessions, confirm original prescriptions survive edits/deletions/reload, LS on/
off still governs next-set weights, and saving completes the plan once. Verify
the description after normal save and from Recent; use mocks for fault recovery
and do not create a production test workout. Physical-device acceptance and
actual deployment of this change are pending. No commit/push/deployment occurred
as part of local implementation.

## Optional weight-source release follow-up (local, 2026-11-05)

Use the normal latest-based update workflow after a separately authorized
publication/deployment. Startup adds exercise_refs.auto_weights with default 1;
existing records/settings remain intact and no databases or keys move. No
historical workouts/trials/reviews are regenerated. No local container build or
production data experiment is needed for this UI/preference change.

On the device, tap the selected e1RM/TM tile again: neither should be selected,
LS should be disabled, and supplied weights should remain unchanged through
RPE edits and reload. Loading another session for that exercise should remember
the choice. Another exercise should retain its settings. Selecting either source
again should restore the existing auto/LS behavior without changing completed or
fixed/manual weights. Use mocks for fault recovery; verify a normal save/review
without producing a test Hevy workout. Preserve pending save identities before
rollback; older images cannot parse new manual-basis review evidence in pending
requests. Keep the current logger database rather than restoring a stale copy.

## Provisional advice release follow-up (local, 2026-11-05)

Use the existing latest pull/up workflow after authorized publication. This
follow-up adds three logger-only advisory tables; existing databases, volumes,
credentials/settings, models, frozen trials and source-selection boundaries are
unchanged. Finish/export active drafts as usual. Legacy frozen requests remain
valid without advisory links and must not receive replacement save identities.
No real-account experiment or extra production test workout is part of release.

Device acceptance: complete a daily check-in, load a fresh planned session, open
its provisional advice and inspect evidence/date/uncertainty. Accept and Modify
must only record intent; sets/reps/weights/program must stay unchanged until the
user edits them. Dismiss collapses repeat similar advice; Not now can be reopened
on the same record. Reload must retain the recorded decision. Source-off and LS
on/off weight behavior must remain intact. Advice unavailability must not block
ordinary logging. Refresh reads recorded decisions, not a fresh evaluation after
changed inputs. Current evidence is immutable and labelled as such.

During the next normal save, verify one Hevy workout and one journal completion,
with exact actual dose separate from the chosen intent. Review/Recent should show
matches/mismatches and only later date-only check-ins in the follow-up window.
Use disposable mocks for interrupted decision responses, concurrent decisions,
rejected-identity correction, failed local outcome commit and reconciliation.
Linked outcome failure leaves local completion pending and must never cause a
remote repost. Keep current databases and all pending identities on rollback;
older images do not understand advisory links. Do not restore stale snapshots
over newer workouts. Physical-device/deployed acceptance of this follow-up is
pending; local implementation did not restart or deploy production services.

## AI training-review release follow-up (local, 2026-11-05)

No deployment is part of implementation. After separately authorized release, use
the existing latest-based pull/up workflow and retain both databases/key material.
Startup adds only host coaching_conversations and coaching_turns tables; no logger
migration or rewrite of existing workouts, plans, trials or settings is required.
The old image can ignore the additive tables; preserve current databases and any
pending workout-save identities during rollback. Never restore stale workout data
merely to remove AI conversations. Conversation history and evidence are personal
training data stored with the host database.

On the deployed device, open AI, retain the existing model/key settings and choose
Review my training. Confirm evidence date/window, known session counts, actual
movement exposure intervals and unknown historical targets before assessing advice.
Confirm it distinguishes an inferred phase from a recorded goal. Discuss a goal or
proposed phase, reload, and reopen the saved review on another device. Both turns
and original evidence date must survive without another provider request. A new
review should include recent training and bounded previous conversation excerpts.
Verify no plan/workout inputs change. Interrupted responses should be labelled and
not resent. Physical device, live-provider quality/cost and deployed-data acceptance
remain separate checks; do not create test Hevy workouts for this feature.

## AI model selector release follow-up (local, 2026-11-05)

After separately authorized publication, use the unchanged latest pull/up workflow.
This selector refresh has no schema or credential migration. On an existing device,
confirm its saved model remains selected (as Custom model if no longer a preset).
Select a budget preset, check its input/output price hint and reload to confirm
selection persistence. The next review turn should record that exact ID. A new
browser with no saved preference should default to GPT-6.1 Terra. Provider access
and actual live costs remain separate checks; no production AI requests were used
for verification. Existing review evidence/history and workout behavior are retained.

## Motivation check-in release follow-up (local, 2026-11-06)

After separately authorized release, keep the latest pull/up update workflow.
Startup adds the logger-only session_motivation table; there is no host-schema,
credential or model migration. Finish/preserve pending drafts and keep both current
databases and key material. Existing frozen requests without motivation remain
valid. Pending requests containing motivation require this version to preserve
that metadata; retain their identities and do not automatically repost on rollback.

Device acceptance: load a normal session and confirm motivation starts unanswered.
Select a rating/reason/note, reload, and confirm preservation without changes to
sets, loads or fatigue scores. Clear returns it to unknown. During the next normal
workout, save once and check the answer in its review/Recent. Start a new AI training
review and inspect motivation_checkins for the saved answer/reason/note. Existing
AI review evidence must not change silently. Motivation edited after a working set
was marked complete is labelled as later context. No production test workout is
needed; live-device/deployed-data acceptance remains pending.
