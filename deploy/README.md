# Production deployment configuration

`production.compose.yml` is the Git-tracked source for the existing production
configuration. It renders identically to the operator's captured running
three-file CasaOS stack. It pins application release `sha-eb76a99` by immutable
image digest and records the already-approved write-enabled state:
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
- The approved image digest and both write-policy flags.

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
settings, nulls, list order, image pins or write flags. It reports field paths
without disclosing their values. Inspect differences rather than auto-applying.
The initial captured/rendered canonical JSON SHA-256 is
`f5a8c0389ff14452f63ff94f43305be04e7e204bb541dca2bcd8ffb38d221281`
(sorted object keys, compact separators, UTF-8); this identifies the capture,
not an image or database digest.

## Current server provenance and future updates

The current container still records the earlier source files in Docker metadata:

1. `/var/lib/docker-data/AppData/hevy-fatigue/docker-compose.yml`
2. `/var/lib/docker-data/AppData/hevy-fatigue/phase1-eb76a99.override.yml`
3. `/var/lib/docker-data/AppData/hevy-fatigue/phase1-eb76a99.writes.yml`

Those resolved settings are represented by this one tracked file. Versioning
them requires no restart, database migration or edit to the active server files.
This reconciliation does not claim the current container was recreated from the
new filename. No source-file replacement or container operation is part of it.

For future changes, update this production file in a GitHub PR, review the
rendered diff and CI, merge the approved configuration, then use that committed
file during a separately authorized deployment/maintenance window. Do not
generate new untracked overlays or silently switch to `latest`. An approved
application update changes the image digest here; it does not enable writes as
a side effect. Publishing an image does not update this pinned deployment.

The existing main-branch image publisher remains unchanged. Merging this
configuration PR may publish an unused image, but cannot change the currently
pinned running container. Do not deploy or restart simply to record configuration.
