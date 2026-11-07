# Hevy-Fatigue repository guidance

AGENTS.md and CLAUDE.md contain the same instructions; keep them synchronized.
Start with docs/hevy-context.md and docs/training-integration.md. Release and
rollback instructions are in docs/training-cutover.md.

## Application boundaries

- One FastAPI host, vanilla-JavaScript pages, no bundler/framework or redesign.
- Host monitoring owns SQLAlchemy and DB_PATH. Rackbook logging owns stdlib
  sqlite3 and RACKBOOK_DB_PATH, mounted at /training. Never merge their tables or
  assign the logging path to DB_PATH. Startup must explicitly initialize both.
- Preserve host daily/pattern models and Hevy-imported inputs. Exact local RPEs
  belong only to logging. Same-day cutoff, missing-data rules and trial model
  timing remain unchanged. Never regenerate frozen trial records.
- credentials.py owns active Hevy credentials, encryption and fallback behavior.
  Keep the host key with host encrypted settings. Do not copy credentials into
  logging storage or print keys/encrypted values/key-file contents.
- Keep package-relative imports and package-relative asset paths. No sys.path
  shims or temporary environment swapping to work around module collisions.
- Use the trainingUrl helper for training requests/dynamic navigation. Static
  training links/assets live under /training; host Settings is /#settings. The
  training worker scope must remain /training/ and network-only.
- Preserve TS pinning, TM behavior, low exact RPEs, canonical completed weights,
  keypad/tap stability, timers and microcycle completion only after save.

## Implementation and safety

Implement requested changes directly. Keep service logic separate from routes,
SQL parameterized and request models explicit. Preserve unrelated edits.
HEVY_WRITES_ENABLED defaults to 0; preview also blocks at the client layer.
Never use the real Hevy account or real databases in tests/experiments. Mock the
client below routes and use temporary SQLite. tools.preview_app provides an
entirely mocked disposable preview. Never deploy intermediate logging builds.

Every combined UI save supplies a persisted UUID and frozen payload. Commit
sending before remote I/O, remote ID before local effects, and all required local
records plus journal completion atomically. Never automatically repost sending
or uncertain attempts. Reconciliation is read-only and requires a full match.
Trial and monitoring refresh run after required local commit and are nonblocking.

Keep existing container identity, port 8125, network and CasaOS configuration.
Prepare/test locally; no incidental production cutover, service retirement or
source-project edits. Keep old database/key rollback material intact.

## Verification and delivery

- python -X utf8 -m unittest discover -s tests
- python -X utf8 -m unittest discover -s rackbook/tests -t .
- node tests/test_recommendation_ui.cjs
- node tests/test_draft_transfer.cjs
- node tests/test_save_recovery_ui.cjs
- Run every rackbook/tests/*.cjs, Docker build/startup, and mocked browser checks.
- Record baseline failures separately; do not weaken behavioral assertions.
- Report physical-device/deployed-data checks separately from automation.
- Update context, release evidence and cutover instructions with behavior changes.

Do not commit or push: the host context reserves commits for Brian's review.
Use conventional logical commits if that restriction is explicitly lifted.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for bross84/hevy-fatigue (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
