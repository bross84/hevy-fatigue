# Production deployment configuration

`production.compose.yml` is the Git-tracked source for production configuration.
It uses `ghcr.io/bross84/hevy-fatigue:latest` with the default pull policy,
restoring `docker compose pull && docker compose up -d`. Existing external
volumes, the host key path and the already-approved write-enabled state remain:
`HEVY_WRITES_ENABLED=1`, `RACKBOOK_READ_ONLY_PREVIEW=0`.

The root `docker-compose.yml` remains a development/build configuration with
workout writes disabled by default. The older `docker-compose.cutover-review.yml`
is the write-disabled pre-cutover template, not the current production state.
Do not use either as a substitute for this production file.

## What is tracked

- Container/project `hevy-fatigue`, port 8125, restart policy and healthcheck.
- External existing volumes `hevy-fatigue_hevy-data` and
  `hevy-fatigue_training-data`, with separate database paths and the host key path.
- External existing network `hevy-fatigue_hevy-net`.
- Exact CasaOS icon, title, launcher and metadata.
- The published `latest` image and both write-policy flags.

No databases, encryption keys, credentials or backups belong in this directory.
Old Rackbook is deliberately not a service in this file and stays stopped.
Cloudflare and Tailscale routing are unchanged, separately managed infrastructure.

## Read-only validation and comparison

CI renders the file and validates the deployment contract; it never uses this
production file to start a container. Application tests use the separate test
image with writes blocked, fake clients and disposable SQLite.

From a checkout:

```sh
docker compose -f deploy/production.compose.yml config --format json | python3 deploy/check_config.py validate -
python3 -m unittest discover -s deploy/tests -v
```

To compare the Git-tracked file with the currently active server stack, run the
following from that checkout on the homelab. It only renders configuration and
inspects container metadata; it never calls `up`, `start`, `stop`, `restart`,
`pull`, any application endpoint or SQLite. Audit files stay private locally.

```sh
umask 077
audit_dir=$(mktemp -d)
export audit_dir
sudo docker compose -f deploy/production.compose.yml config --format json > "$audit_dir/github.json"
sudo python3 - <<'PY' > "$audit_dir/server.json"
import json, subprocess
host = json.loads(subprocess.check_output(['docker', 'inspect', 'hevy-fatigue'], text=True))[0]
labels = host['Config']['Labels']
command = ['docker', 'compose', '--project-directory', labels['com.docker.compose.project.working_dir'],
           '--project-name', labels['com.docker.compose.project']]
for path in labels['com.docker.compose.project.config_files'].split(','):
    command.extend(['-f', path])
print(subprocess.check_output(command+['config', '--format', 'json'], text=True))
PY
python3 deploy/check_config.py compare "$audit_dir/github.json" "$audit_dir/server.json"
```

Expected output is `matches: true` with no differing fields. The comparison is
strict: it ignores JSON object key order only, not missing metadata, extra
settings, nulls, list order, image references or write flags. It reports field paths
without disclosing their values. Inspect differences rather than auto-applying.
The initial captured/rendered canonical JSON SHA-256 is
`f5a8c0389ff14452f63ff94f43305be04e7e204bb541dca2bcd8ffb38d221281`
(sorted object keys, compact separators, UTF-8); this identifies the capture,
not an image or database digest.

## Historical server provenance

The current container still records the earlier source files in Docker metadata:

1. `/var/lib/docker-data/AppData/hevy-fatigue/docker-compose.yml`
2. `/var/lib/docker-data/AppData/hevy-fatigue/phase1-eb76a99.override.yml`
3. `/var/lib/docker-data/AppData/hevy-fatigue/phase1-eb76a99.writes.yml`

Those resolved settings are represented by this one tracked file. Versioning
them requires no restart, database migration or edit to the active server files.
This reconciliation does not claim the current container was recreated from the
new filename. No source-file replacement or container operation is part of it.

## Normal updates (restored at the user's request, 2026-11-04)

Install this tracked file once as the server's active Compose file, preserving
its existing project, external volumes and network. From the server directory:

```sh
cd /var/lib/docker-data/AppData/hevy-fatigue
docker compose pull && docker compose up -d
```

Use `sudo` on each Docker command if required by the server. Application updates
now require no image-pin edits or configuration PR. The main-branch publisher
updates `latest`; pulling downloads it, and `up -d` recreates the app as needed.
Publishing alone does not restart the server. There is no local build step.
The separate named volumes retain both databases and the host encrypted settings
and key. No volume removal, data migration between stores, or credential reset
is part of this configuration change. Finish or export active workout drafts
before updating; existing pending-save identities must be retained.

Future changes to storage, settings, ports, network or CasaOS metadata still go
through a GitHub PR. The old migration instructions using immutable digests and
`pull_policy: never` are historical and do not govern normal application updates.
The read-only validator now requires this repository's `latest` image, rejects
local builds and blocked pull policies, and retains the existing storage/settings
checks. For rollback, use the known previous release against the same preserved
volumes; do not restore older database snapshots over newer workouts. A digest
can still identify a specific rollback image without being the normal workflow.
