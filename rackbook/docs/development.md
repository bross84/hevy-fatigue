# Rackbook development workflow

Read `rackbook-context.md`, then `backlog.md`, and the root `AGENTS.md` / `CLAUDE.md` before working. The coding assistant handles design, implementation, and validation directly; Brian reviews the result on his phone.

## Implementation

- Work on one requested feature at a time. Inspect the existing behavior before editing.
- Diagnose root causes and explain meaningful design choices. Ask one focused question when a material tradeoff remains unresolved.
- Implement routine code and UI changes directly. Do not require a separate implementer or handoff prompt.
- Keep FastAPI routes thin, models explicit, SQLite queries parameterized, and business logic in service or pure modules.
- Verify columns with `PRAGMA table_info` before querying unfamiliar tables. Read `DB_PATH` from the environment.
- Keep each frontend page self-contained with inline vanilla JavaScript and CSS. Preserve working-tree CRLF line endings.
- Preserve behavior outside the requested scope; hide or retire UI rather than permanently deleting features unless explicitly requested.

## Validation

- Add meaningful tests for non-trivial logic and critical paths. A small presentation change does not require tests that merely mirror its markup.
- Check edited JavaScript syntax and review the layout at phone width where appropriate.
- Run `python -m unittest discover -s tests -t .` before pushing.
- Mock every Hevy write in tests and previews. Never save a real workout during verification.
- Use temporary databases for tests. Do not put test rows into the live database.

## Delivery

- Report what changed, how it was checked, and any material limitation.
- Use conventional commits and keep each commit focused on one logical change.
- Commit and push finished work when authorized; push only after the required checks pass.
- Update project context and backlog when behavior or workflow changes.
