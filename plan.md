# Hevy Fatigue - Local Plan Snapshot

Last updated: 2026-05-15 (Scoring Scale 0-20 Migration)

## Latest Maintenance Update (2026-05-15, Scoring Scale 0-20 Migration)

- Migrated readiness scoring scale in `main.py` from 0-10 to 0-20 by updating multiplier call sites that consume `_subjective_fatigue()` output.
- Updated fatigue threshold defaults in `_CALIBRATION_DEFAULTS`:
	- large decrease: `15.0`
	- decrease: `13.0`
	- continue: `8.0`
	- increase: `6.0`
- Updated `_combined_recommendation()` band thresholds to 0-20 equivalents.
- Updated objective score scaling factors and clamp ranges used in readiness endpoints and diagnostics (`*10` objective ratio scale and `0.0..20.0` clamps).
- Updated neutral subjective fallback defaults from `5.0` to `10.0` where combined/fatigue score paths require a midpoint fallback.
- Kept `_subjective_fatigue()` unchanged (still returns `0.0..1.0`).
- Kept training modifier behavior and bounds unchanged (`±1.5`).
- Updated chart rendering scale in `static/index.html`:
	- ATL/CTL bar percentage denominator from 10 to 20
	- readiness background bands to new 0-20 tier boundaries
	- readiness chart y-axis max from 10 to 20
- Validation status:
	- static diagnostics report no errors in `main.py` and `static/index.html`

## Latest Maintenance Update (2026-05-14, Critical Bug-Hunt Skill Added)

- Added a new workspace skill at `.github/skills/critical-bug-hunt/SKILL.md`.
- Skill captures a reusable high-severity bug-finding workflow focused on concrete-trigger correctness failures:
	- data loss/corruption
	- crash in critical paths
	- auth/permission bypass and security exposure
	- significant user-facing breakage
- Includes explicit decision gates for:
	- criticality threshold (concrete trigger + high impact)
	- fix vs report-only behavior when confidence is uncertain
	- PR safety bar (high confidence required)
- Includes output contract for both outcomes:
	- fixed bug report with impact, root cause, fix, and validation
	- no-critical-bugs-found summary

## Latest Maintenance Update (2026-05-09, Canonical Mapping Sync + Startup Mapping Migration)

- Updated canonical save flows in `main.py` so when a canonical title is saved (direct canonical API and conflict resolve API), the canonical title is synchronized into `exercise_mappings`.
- New canonical-to-mapping sync behavior:
	- carries over an existing mapping pattern when one exists (prefers previous canonical title mapping, then latest Hevy title mapping for the same `exercise_id`)
	- inserts an unassigned mapping row when no prior pattern exists
	- removes the old mapping title entry after carry-over so canonical title becomes the active mapping key
- Added startup migration flag `migration_canonical_mapping_sync_v1` in `database.py`.
- Migration behavior inserts unassigned `exercise_mappings` rows for canonical titles that are missing from `exercise_mappings` (case-insensitive existence check).
- Validation status:
	- `python -m py_compile main.py database.py` passes

## Latest Maintenance Update (2026-05-09, Canonical Sync Root-Cause + Movement Trend ID Join + Backfill)

- Updated `importer.py` pre-write canonical resolution to re-check `exercise_canonical` by `exercise_id` during sync processing, addressing stale map timing within long import runs without adding any post-write rewrite path.
- Updated movement analytics APIs in `main.py`:
	- `/api/movements/search` now resolves display titles via canonical + mapping join path and returns `items[{exercise_id,title}]` for stable selection.
	- `/api/movements/session-trend` and `/api/movements/volume-trend` now support `exercise_id` filtering and resolve movement titles through canonical/mapping joins instead of raw title equality.
- Updated Movement Trend UI wiring in `static/index.html` to select/store `exercise_id` from autocomplete items and query trend endpoints via `exercise_id` (with title fallback for compatibility).
- Added one-time historical canonical backfill migration in `database.py` (`migration_canonical_title_backfill_v1`) that updates `workout_logs.exercise_title` from `exercise_canonical.canonical_title` where `exercise_id` matches.
- Updated `canonical_gate.py` Gate checks to verify canonical storage using direct SQL against `workout_logs` filtered by `exercise_id`.
- Added `movement_trend_gate.py` with Gate #3 validating exercise_id-based session trend aggregation after backfill.
- Validation status:
	- static/file diagnostics report no syntax errors in edited files
	- live gate scripts are blocked until local API is running at `http://127.0.0.1:8000`

## Latest Maintenance Update (2026-05-08, AI Tab Overflow Height Handoff)

- Updated `static/index.html` so `body.ai-open` now sets both `overflow: hidden` and `height: 100vh`.
- Added `body.ai-open main` constraints (`padding: 0`, `overflow: hidden`, `height: calc(100vh - 54px)`, flex column, full width behavior) to prevent page-level scroll conflict while AI tab is open.
- Updated `.tab-content#tab-ai.active` to `flex: 1`, `height: 100%`, and `overflow: hidden`, removing previous `calc(100vh - 54px)` dependency.
- Updated mobile AI override to use `height: 100%` for `.tab-content#tab-ai.active`.

## Latest Maintenance Update (2026-05-07, AI Tab Body Overflow Lock)

- Added `body.ai-open { overflow: hidden; }` in `static/index.html` to lock page scroll while AI tab is active.
- Updated AI tab activation path in `activateTab(tabName)` to toggle `document.body.classList` with `ai-open` for AI vs non-AI tabs.
- Kept `tab-content#tab-ai.active` height/overflow rule intact and scoped changes to requested CSS/JS only.

## Latest Maintenance Update (2026-05-07, AI Chat Full Height Sticky Layout)

- Replaced `static/index.html` AI tab active layout with a full-height column (`height: calc(100vh - 54px)`) and hidden overflow.
- Replaced AI chat card and message area rules to a full-height scrollable layout with sticky input row and no legacy fixed message-area heights.
- Updated user/assistant message-role rules to the requested subtle right bubble for user and no-bubble full-width assistant style.
- Updated `@media (max-width: 900px)` AI overrides to only enforce tab height and `ai-chat-messages { min-height: 0; }`.

## Latest Maintenance Update (2026-05-07, AI Chat Surface Token Alignment)

- Updated `static/index.html` AI chat message area surface to `var(--bg)` and explicitly removed box shadow while keeping border removed.
- Updated model selector/input controls in `#ai-model-field` to use `background: var(--card)` and `color: var(--text)`.
- Updated `.ai-chat-input` to use `background: var(--card)` and `color: var(--text)`.

## Latest Maintenance Update (2026-05-07, AI Chat Card Shell Removal)

- Updated `static/index.html` so `#tab-ai .ai-chat-card` uses a transparent shell (`background: transparent !important; border: none !important; box-shadow: none;`) with centered `max-width: 760px` layout and `padding: 0 16px`.
- Added compact inline model control styling for `#tab-ai #ai-model-field select` and `#tab-ai #ai-model-field input` (auto width, 160px minimum, compact padding).
- Scope remained CSS-only with no HTML or JS changes.

## Latest Maintenance Update (2026-05-07, AI Chat Plain Text Stack)

- Updated `static/index.html` AI chat message presentation to plain stacked text (no bubble background, radius, or per-bubble border styling).
- Removed row-style alignment wrappers by switching message containers to block layout and text alignment by role.
- Set `#tab-ai .ai-chat-card` to a centered 760px column and adjusted message pane sizing/background to the requested standard chat column style.

## Latest Maintenance Update (2026-05-07, AI Chat Standard UI Revert)

- Reverted `static/index.html` AI chat window from terminal styling to a standard modern chat UI using theme tokens (`var(--card)`, `var(--border)`, `var(--bg)`).
- Removed terminal artifacts: `$`/`>` prefixes, cursor animation, hardcoded dark colors, and the `ai-chat-clear` button element/CSS.
- Applied requested message bubble layout, input sizing, model-label typography, scrollbar styling, and three-dot typing indicator styling.

## Latest Maintenance Update (2026-05-07, AI Terminal Bar Removal)

- Removed the `terminal-bar` element and its three colored dot children from the AI chat card in `static/index.html`.
- Deleted the `.terminal-bar` and `.terminal-dot*` CSS rules from `static/index.html`.
- Kept all other HTML and CSS unchanged.

## Latest Maintenance Update (2026-05-07, AI Chat UX Alignment Pass)

- Updated `static/index.html` so AI chat messages are constrained to `max-width: 75%`, with user messages right-aligned and assistant messages left-aligned.
- Preserved terminal-style differentiation with `>` and `$` prefixes and role-specific text colors.
- Added an `#ai-typing-indicator` element and CSS visibility/animation hooks for in-flight response feedback.
- Updated AI chat textarea placeholder copy and enforced touch/iOS-safe input/button sizing.

## Latest Maintenance Update (2026-05-07, Settings Grid Equal Height)

- Updated `static/index.html` so `#tab-settings.active` stretches grid items instead of aligning them to the start.
- Added `height: 100%` to `#tab-settings .settings-card` so each settings card fills its grid cell height.
- Scope remained CSS-only and limited to the settings grid equal-height behavior.

## Latest Maintenance Update (2026-05-07, Settings Grid 2x2 Layout)

- Updated `static/index.html` so `#tab-settings.active` uses a 2x2 named-area layout: `api`, `sync`, `diagnostics`, and `ai`.
- Added the missing `#tab-settings .ai-settings-card { grid-area: ai; }` assignment.
- Removed the full-width AI settings card override so the named grid-area controls placement.

## Latest Maintenance Update (2026-05-07, AI Chat Terminal Restyle)

- Restyled the AI chat card in `static/index.html` to read as a terminal window with a scoped dark shell, title bar, and monospace title treatment.
- Added a new `terminal-bar` element with red, yellow, and green dots immediately before the existing `AI Chat` title.
- Flattened user and assistant message bubbles into terminal-style lines with `>` and `$` prefixes while preserving existing AI chat behavior.

## Latest Maintenance Update (2026-05-07, Mobile Drawer Docs Link)

- Added `Docs` link to the mobile drawer in `static/index.html`.
- Placed the link after the last existing mobile nav tab (`Settings`) and pointed it to `/static/docs.html`.
- Scope intentionally limited to mobile drawer markup only.

## Latest Maintenance Update (2026-05-07, AI/Settings/Mobile UI Stabilization)

- Updated `static/index.html` to keep top navigation persistently visible on mobile:
	- set mobile nav to fixed positioning at the top
	- adjusted `main` top padding at mobile breakpoints to avoid content overlap
	- simplified very-small-screen nav rules to prevent 2-row wrapping behavior
- Updated mobile drawer offset so it opens beneath the fixed top nav (`top: 54px`).
- Fixed AI chat card alignment on desktop:
	- centered active AI tab content container
	- constrained chat card width with centered margins
- Fixed Settings tab layout imbalance:
	- forced `AI Settings` card to span full grid width on desktop (`grid-column: 1 / -1`)
- Reduced mobile AI input zoom/keyboard friction:
	- increased `.ai-chat-input` font size to `16px`
	- added textarea input attributes (`autocomplete`, `autocorrect`, `autocapitalize`, `spellcheck`, `enterkeyhint`) for better mobile behavior
- Validation:
	- static diagnostics report no errors in `static/index.html`

## Latest Maintenance Update (2026-05-07, Docs CSS Variables and Importer List Styling Fix)

- Updated `static/docs.html` `:root` wiki override mappings to define missing variables used by existing styles:
	- `--text-primary: var(--text)`
	- `--text-secondary: var(--text)`
	- `--text-muted: var(--muted)`
	- `--bg-code: color-mix(in srgb, var(--card) 72%, black 28%)`
	- `--border-accent: var(--border)`
	- `--accent-border: color-mix(in srgb, var(--accent) 40%, transparent)`
- Added `.doc-list` and `.doc-list li` CSS rules to standardize importer bullet styling.
- Applied `class="doc-list"` to the unordered list in the `#importer` section only.
- Verified section badge sequencing remains correct:
	- `05` (modalities), `05b` (title tagging), `05c` (importer), `06` (movement patterns)
- Validation: static diagnostics report no errors in `static/docs.html`.

## Latest Maintenance Update (2026-05-07, Diagnostics Page Outlined in Docs)

- Added a dedicated `Diagnostics page` section to `static/docs.html` (`id="diagnostics"`) to clearly document purpose and usage.
- Added a new Notes sidebar link to `#diagnostics` for quick wiki-style navigation.
- Expanded documentation coverage with:
	- when to use diagnostics
	- panel-by-panel outline (session volume, 7-day, 28-day, raw session data)
	- a recommended debugging workflow block
	- practical note about observational vs corrective actions
- Updated importer Diagnostics callout to link to the full diagnostics section (`§10 Diagnostics page`).
- Renumbered trailing sections to preserve order:
	- Limitations: `10` -> `11`
	- References: `11` -> `12`
- Validation:
	- diagnostics sidebar link and section anchor both present in `static/docs.html`
	- static diagnostics report no errors in `static/docs.html`

## Latest Maintenance Update (2026-05-07, Remove Divergences from RTS TRAC Section)

- Removed the entire `Divergences from RTS TRAC` section from `static/docs.html`.
- Removed the corresponding sidebar TOC link to `#divergences` in the Notes group.
- Updated an Overview paragraph to remove the in-page link to the removed section.
- Renumbered subsequent sections to keep ordering contiguous:
	- `Known limitations` changed from section 11 to 10
	- `References` changed from section 12 to 11
- Validation:
	- no remaining `divergences` references in `static/docs.html`
	- static diagnostics report no errors in `static/docs.html`

## Latest Maintenance Update (2026-05-07, Docs Wiki Sidebar Restoration)

- Reworked `static/docs.html` to restore wiki-style section navigation while retaining index theme colors.
- Added a fixed left sidebar Table of Contents on desktop and a slide-in mobile drawer on small screens.
- Added mobile navigation controls:
	- hamburger menu button in top nav
	- tap-to-close overlay
	- responsive open/close behavior with ARIA state updates
- Added requested Training load TOC links in sidebar:
	- `Title tagging` (`#title-tagging`)
	- `Workout importer` (`#importer`)
- Added new docs sections between §05 and §06:
	- `§05b Workout title tagging convention`
	- `§05c Workout importer`
- Added section-aware sidebar highlighting via `IntersectionObserver` and smooth-scroll behavior for TOC links.
- Kept index-compatible visual theme tokens (`--bg`, `--card`, `--border`, `--text`, `--accent`, etc.) while preserving docs-specific layout.

## Latest Maintenance Update (2026-05-07, Docs Page Navbar Integration)

- Added "Docs" link to the navbar in `static/index.html` 
  - Added as an external link in the nav-tabs section, styled to match existing nav elements
- Refactored `static/docs.html` to match `static/index.html` styling:
  - Replaced custom color scheme with index.html's theme variables (dark: `#2e282a`, `#3d3638`, etc.)
  - Added sticky navbar at top with logo, nav links, and "← Dashboard" return button
  - Removed sidebar layout (previously a fixed left sidebar with navigation sections)
  - Converted main content area from `margin-left: var(--sidebar-w)` to centered `main` with `max-width: 900px`
  - Updated typography: headings, body text, and inline code now use index.html's font sizes and colors
  - Updated component styling:
    - Formula blocks: new background/border colors matching theme
    - Info cards: updated with new color scheme
    - Tables: header and cell styling aligned with index.html
    - Inline code: updated background/border/text colors
  - Updated mobile responsiveness for new navbar layout
  - Simplified JavaScript: removed sidebar nav link tracking, kept only smooth scroll for anchor links

## Latest Maintenance Update (2026-05-03, Backlog source-of-truth established)

- Removed the Diagnostics page AI Assistant section from `static/diagnostic.html`.
- Deleted AI section HTML controls and containers:
	- model selector
	- context preview toggle and preview area
	- chat message window
	- input row, send/clear controls, and status line
- Removed AI-only JavaScript from `static/diagnostic.html`:
	- `OPENROUTER_API_KEY` and `OPENROUTER_URL`
	- `chatHistory` and `readinessContext`
	- `buildSystemPrompt()`, `sendMessage()`, `clearChat()`, `appendMessage()`, `escapeHtml()`, `setStatus()`, `setContextPreview()`, and `toggleContextPreview()`
	- removed readiness-context assignment from `loadAndRender()`
	- removed AI input listeners from `DOMContentLoaded`
- Removed AI-only CSS selectors (`.ai-*`) from `static/diagnostic.html`.
- Removed `marked.js` CDN script tag from `static/diagnostic.html` because no markdown parsing remains in that file.
- Preserved non-AI diagnostics functionality and controls:
	- Engine Snapshot render path remains intact
	- Pattern Sensitivity and Session Processing cards remain unchanged
- Validation:
	- static diagnostics report no errors in `static/diagnostic.html`
	- no `OPENROUTER_API_KEY`, `marked`, or removed AI function/id references remain in `static/diagnostic.html`

## Latest Maintenance Update (2026-05-06, AI Prompt Recent Session Detail Rewrite)

- Replaced the recent-session section in `_build_ai_system_prompt()` in `main.py` with direct database queries over `WorkoutSession` and `WorkoutLog`.
- The AI system prompt now includes only the last 3 sessions ordered by `workout_date DESC, start_time DESC` instead of a snapshot-derived 7-day window.
- Each session line now includes:
	- workout date
	- workout title
	- modality
	- duration in minutes
	- sRPE
- Each session now expands into per-exercise detail aggregated from `WorkoutLog` grouped by `exercise_title`, including:
	- set count
	- total reps
	- total volume (`weight_lbs * reps`)
	- top weight
	- average RPE when present
- Session ATL/CTL/TSB values were intentionally left out of the session line because current-day training load context already appears in the prompt's `Training Load` section.
- Validation:
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-06, AI Prompt Scale Reference)

- Updated `_build_ai_system_prompt()` in `main.py` to include a `SCALE REFERENCE (critical for correct interpretation):` section immediately after the prompt header/date block.
- Revised the scale guidance to emphasize subjective-input semantics:
	- all subjective inputs now share a common 0-4 interpretation where `2` is normal expected training fatigue and only `3` or `4` should trigger caution/modification recommendations
	- combined and subjective scores are explicitly defined as `0 = fully fresh/recovered, 10 = maximum fatigue`
	- objective score is clarified as a neutral 0-10 recent-volume context signal rather than a readiness score
	- TSB and volume ratio definitions remain explicit for load-context interpretation
- Validation:
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-06, AI Chat Raw JSON SSE Alignment)

- Updated AI chat streaming contract between `main.py` and `static/index.html` to preserve upstream OpenRouter JSON SSE payloads instead of flattening deltas into plain-text proxy chunks.
- Changed `_stream_openrouter(...)` in `main.py` to forward upstream `data:` payloads unchanged:
	- still buffers `iter_text()` manually on `\n\n` SSE boundaries
	- now emits `data: {raw_json}\n\n` for each upstream JSON event
	- preserves `[DONE]` pass-through and keeps response/client cleanup in `finally`
- Refactored `sendAIMessage()` in `static/index.html` to match the working diagnostic-style parser against raw JSON SSE lines:
	- reads stream chunks with `ReadableStream` + `TextDecoder`
	- buffers incomplete lines across chunks
	- processes `data: ` lines individually instead of joining multiple payload lines
	- parses each JSON payload and appends `choices[0].delta.content` (with `text` fallback) to `assistantText`
	- keeps incremental `marked.parse(assistantText)` rendering and scroll-to-bottom behavior
- Resulting architecture keeps backend key secrecy intact while aligning the chat parser with the working raw-JSON SSE model used elsewhere.
- Validation:
	- `python -m py_compile main.py` passes
	- editor diagnostics report no errors in `main.py` or `static/index.html`

## Latest Maintenance Update (2026-05-06, Session-Scoped AI Model Selection)

- Moved AI model selection out of persisted settings and into the AI chat UI in `static/index.html`:
	- AI tab now renders a model dropdown above the context preview with six preset OpenRouter models plus `Custom model…`
	- session-only state is stored in `aiSelectedModel`, defaulting to `openai/gpt-4o-mini` on page load
	- selecting `Custom model…` reveals a text input and chat requests use that custom string for the current browser session only
- Simplified the Settings-tab AI card in `static/index.html` to API-key-only:
	- removed the model selector from Settings
	- preserved API key preview, encrypted-key save flow, and lock/change behavior
	- updated copy so Settings manages only the API key while model choice happens in the AI tab
- Reduced the backend AI settings contract in `main.py`:
	- `AISettingsInput` now accepts only `api_key`
	- `GET /api/settings/ai` now returns only `configured` and `api_key_preview`
	- `PUT /api/settings/ai` now validates/stores only encrypted `ai_api_key`
	- code no longer reads or writes `ai_model`
- Updated request-scoped chat model handling in `main.py`:
	- `AIChatRequest` now includes `model` with default `openai/gpt-4o-mini`
	- `POST /api/ai/chat` now uses the request model with the stored API key when calling `_stream_openrouter(...)`
	- `sendAIMessage()` now posts `{ message, history, model }`
- Validation:
	- `python -m py_compile main.py` passes
	- editor diagnostics report no errors in `main.py` or `static/index.html`
	- isolated API smoke checks confirmed `PUT /api/settings/ai` succeeds with only `api_key`, `GET /api/settings/ai` returns no `model` field, chat requests pass through the selected request model, and only `ai_api_key` is persisted

## Latest Maintenance Update (2026-05-05, OpenRouter-Only AI Simplification)

- Simplified backend AI integration in `main.py` to OpenRouter-only:
	- removed provider field from `AISettingsInput`
	- `_get_ai_settings(db)` now returns only `(model, api_key)` and no longer reads `ai_provider`
	- removed multi-provider stream helpers (`_stream_anthropic`, `_stream_gemini`) and provider-specific payload builders
	- renamed `_stream_openai_family(...)` to `_stream_openrouter(...)` and hardcoded OpenRouter chat completions URL
	- removed provider dispatch from `POST /api/ai/chat`; endpoint now always uses OpenRouter path via `_openai_compatible_messages(...)`
- Simplified AI settings API contract in `main.py`:
	- `PUT /api/settings/ai` now accepts/stores only `model` and `api_key` (encrypted)
	- `GET /api/settings/ai` now returns `configured`, `model`, and `api_key_preview` only (no `provider` field)
- Confirmed `_safe_sse_chunk()` behavior in `main.py` keeps only carriage-return sanitization:
	- `clean = (delta or "").replace("\r", "")`
	- no newline replacement and no `.strip()`
- Simplified AI settings UI/JS in `static/index.html`:
	- removed provider dropdown from Settings tab AI card
	- replaced chip/provider model controls with a single free-text model input and helper note
	- removed provider-switching frontend logic and provider-bearing save payloads
	- `saveAISettings()` now sends `{ model, api_key }`
	- updated AI copy to OpenRouter-specific wording
- Kept chat card behavior unchanged (including SSE streaming and final markdown render on completion).
- Validation:
	- static diagnostics: no errors in `main.py` and `static/index.html`
	- `python -m py_compile main.py` passes

## Latest Maintenance Update (2026-05-05, Stage 5 Frontend: AI Chat Card)

- Added AI chat card UI in `#tab-ai` inside `static/index.html` with:
	- collapsed context preview (`show context` / `hide context`) using monospace pre-wrapped display
	- scrollable message window with user bubbles right-aligned and assistant bubbles left-aligned
	- markdown rendering for assistant content via `marked.parse()`
	- auto-resize textarea input row with Enter-to-send and Shift+Enter newline behavior
	- Send/Clear buttons and status line for `Thinking...` and error states
- Added marked.js CDN to `static/index.html` head (`cdnjs marked 9.1.6`).
- Added frontend state in `static/index.html`:
	- `aiChatHistory = []`
	- `aiReadinessContext = null`
- Implemented `loadAIContext()` in `static/index.html`:
	- fetches `GET /api/diagnostics/snapshot`
	- builds context preview string client-side using the same field set/labels as `_build_ai_system_prompt()` in backend
	- refreshes on every AI tab activation
- Updated AI tab activation flow in `static/index.html`:
	- `activateTab('ai')` now runs `loadAISettings().then(() => loadAIContext())`
- Implemented `sendAIMessage()` in `static/index.html`:
	- posts `{ message, history: aiChatHistory }` to `POST /api/ai/chat`
	- reads SSE stream into a plain-text streaming assistant bubble
	- renders assistant markdown with `marked.parse()` once after the stream completes
	- finalizes exchange into `aiChatHistory`
- Implemented `clearAIChat()` in `static/index.html`:
	- resets `aiChatHistory`
	- restores message window placeholder and clears status/input state
- Added unconfigured-state chat gating:
	- when AI settings are not configured on tab activation, chat notice is shown and Send is disabled
	- when configured, notice is hidden and Send is enabled
- Validation:
	- static diagnostics on `static/index.html` pass (no errors)
	- inline JS brace counts balanced (`open=close` for both inline script blocks)
	- marked.js CDN reference confirmed in `static/index.html`

## Latest Maintenance Update (2026-05-05, Stage 4 Fix: Move AI Settings To Settings Tab)

- Moved the full AI settings card markup (provider/model/API key + save/change controls) from `#tab-ai` to `#tab-settings` in `static/index.html`.
- Left `#tab-ai` in the DOM but empty to reserve it for Stage 5 chat UI.
- Kept AI settings logic unchanged:
	- `loadAISettings()` unchanged
	- `saveAISettings()` unchanged
	- AI tab activation still calls `loadAISettings()` for configured-state refresh
- No backend changes.
- No CSS changes required.
- Validation:
	- static diagnostics on `static/index.html` pass (no errors)
	- markup checks confirm AI card is now inside Settings tab and AI tab is empty

## Latest Maintenance Update (2026-05-04, Stage 4 Frontend: AI Settings Card)

- Updated `static/index.html` navigation to add `AI` as the fifth tab in both desktop and mobile tab lists.
- Added new `#tab-ai` panel in `static/index.html` with an AI settings card containing:
	- provider selector (`OpenRouter`, `Anthropic`, `Gemini`, `ChatGPT (OpenAI)`, `DeepSeek`)
	- dynamic model control area
	- encrypted API key input with show/hide toggle
	- inline result feedback and save/change actions
- Added provider-aware model control behavior in `static/index.html`:
	- OpenRouter uses free-text model input plus quick-pick chips:
		- `google/gemini-flash-1.5`
		- `anthropic/claude-sonnet-4-5`
		- `meta-llama/llama-3.3-70b-instruct`
		- `deepseek/deepseek-chat`
		- `openai/gpt-4o`
	- Anthropic models: `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-3-5`
	- Gemini models: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-pro`
	- OpenAI models: `gpt-4o`, `gpt-4o-mini`, `o3-mini`
	- DeepSeek models: `deepseek-chat`, `deepseek-reasoner`
- Added AI settings API wiring in `static/index.html`:
	- `loadAISettings()` -> `GET /api/settings/ai` on AI tab activation
	- `saveAISettings()` -> `PUT /api/settings/ai`
	- inline `422`/validation detail extraction and display
	- empty API key client-side validation (request blocked)
	- success lock flow: fields disabled + masked preview shown + `Change` unlock action
- Validation:
	- static diagnostics for `static/index.html` report no errors
	- existing tab activation branches preserved with added `ai` activation load hook

## Latest Maintenance Update (2026-05-04, Stage 3 Backend: AI Chat Proxy Endpoint)

- Added `AIChatMessage` and `AIChatRequest` models in `main.py`.
- Added `POST /api/ai/chat` in `main.py`:
	- returns `422` when AI settings are not configured
	- builds system prompt using `_build_ai_system_prompt(db)`
	- dispatches by stored provider (`openrouter`, `openai`, `deepseek`, `anthropic`, `gemini`)
- Implemented provider-specific streaming helpers using `httpx` with streamed upstream responses:
	- OpenRouter/OpenAI/DeepSeek via shared OpenAI-compatible path and message format
	- Anthropic via `https://api.anthropic.com/v1/messages` with required headers and Anthropic message format
	- Gemini via `.../{model}:streamGenerateContent?key=...` with Gemini contents format
- SSE proxy behavior:
	- forwards chunks as `data: {delta}\n\n`
	- terminates with `data: [DONE]\n\n`
- Provider error mapping:
	- upstream HTTP errors are surfaced as `502` with provider error detail
	- avoids raw Python traceback leakage in response detail
- Validation:
	- `python -m py_compile main.py` passed
	- Stage 3 gate checks passed in deterministic mocked-stream harness:
		- no AI settings configured -> `422`
		- bad API key -> `502` with provider message
		- OpenAI-compatible stream yields at least one `data:` chunk and ends with `[DONE]`
		- Anthropic stream yields at least one `data:` chunk and ends with `[DONE]`
		- history payload propagation verified with follow-up context response

## Latest Maintenance Update (2026-05-04, Stage 2 Backend: System Prompt Builder)

- Refactored diagnostics snapshot logic into shared helper `_build_diagnostics_snapshot(db)` in `main.py`.
- Updated `GET /api/diagnostics/snapshot` in `main.py` to return `_build_diagnostics_snapshot(db)` so route output remains unchanged while enabling internal reuse.
- Added `_build_ai_system_prompt(db)` helper in `main.py` that consumes the same diagnostics snapshot data and builds a structured system prompt containing:
	- date
	- combined/subjective/objective scores
	- check-in detail fields
	- joint advisory
	- ATL/CTL/TSB
	- volume baseline
	- last 7 days of sessions
- Missing-data handling in `_build_ai_system_prompt(db)`:
	- emits `No check-in recorded for today` when no check-in exists for today
	- emits `No sessions in the last 7 days` when no sessions match the last-7-day window
	- normalizes missing values to `N/A` (no literal `None` output)
- Validation:
	- `python -m py_compile main.py` passed
	- Stage 2 gate checks passed via isolated temp DB snippet:
		- with today's check-in: output contains `Combined Score`, `Tiredness`, `ATL`, and at least one `Session:` line
		- with no check-in today: output contains `No check-in recorded for today` and does not contain literal `None`
		- with no sessions in last 7 days: output contains `No sessions in the last 7 days`

## Latest Maintenance Update (2026-05-04, Stage 1 Backend: Encrypted AI Settings Storage)

- Added `AISettingsInput` in `main.py` with fields `provider`, `api_key`, and `model` for AI settings payloads.
- Added `_get_ai_settings(db)` helper in `main.py`:
	- reads `ai_provider`, `ai_model`, and `ai_api_key` from `app_settings`
	- decrypts `ai_api_key` via `_decrypt()`
	- returns `(None, None, None)` when any value is missing or decryption fails
- Added `GET /api/settings/ai` in `main.py`:
	- always returns stable shape `{ configured, provider, model, api_key_preview }`
	- maps unset/missing state to `configured: false` with null `provider`, `model`, and `api_key_preview`
	- never returns raw API key
- Added `PUT /api/settings/ai` in `main.py`:
	- validates provider allowlist: `openrouter`, `anthropic`, `gemini`, `openai`, `deepseek`
	- returns `422` on invalid provider
	- trims and validates non-empty `model` and `api_key` (`422` on empty)
	- encrypts API key with `_encrypt()` and stores `ai_provider`, `ai_model`, `ai_api_key` in `app_settings`
	- returns same shape as GET with masked preview only
- Validation:
	- `python -m py_compile main.py` passed
	- API gate checks passed (isolated temp DB + TestClient):
		- unset `GET /api/settings/ai` returns `200` and stable `configured: false` null-shape
		- valid `PUT /api/settings/ai` returns `200`, `configured: true`, preview suffix matches key tail, raw key absent
		- invalid provider returns `422`
		- empty key returns `422`
		- post-save `GET /api/settings/ai` returns correct provider/model, raw key absent
		- DB `app_settings.ai_api_key` stored encrypted (Fernet token prefix `gAAA`, not plaintext)

## Latest Maintenance Update (2026-05-03, Backlog Source-of-Truth)

- Added `backlog.md` in project root with release blockers, bookmarked items, low-priority items, and recently completed context.
- Outstanding work tracking now uses `backlog.md` as the source of truth.
- `plan.md` open-items section is retained as historical context only.

## Latest Maintenance Update (2026-05-03, Initial Import Verification-State Preservation)

- Updated `initial_import()` in `importer.py` to preserve manual verification fields across full reimport wipes.
- Before deleting `workout_sessions`, importer now snapshots existing rows into a dict keyed by `hevy_workout_id` containing:
	- `verification_status`
	- `verified_at`
	- `srpe`
- After replaying Hevy workouts and rebuilding `workout_sessions`, importer now restores those preserved fields onto rebuilt rows where `hevy_workout_id` matches.
- This prevents full reimports from resetting previously verified/manual session state back to default pending values.
- No changes made to `incremental_sync()`.
- No changes made to `_process_workout()`.
- Validation: `python -m py_compile importer.py` passed.

## Latest Maintenance Update (2026-05-03, Exercises Tab Cleanup)

- Removed `Exercise Name Overrides` card and all associated frontend JS/state from `static/index.html`.
- Removed `Rename Exercise` card and all associated frontend JS/state from `static/index.html`.
- Updated `Exercise Names - Needs Review` card to be collapsible with a header toggle:
	- Expanded by default when unresolved conflicts exist.
	- Collapsed by default when no unresolved conflicts exist.
- Added inline `Add Override` flow inside the expanded Needs Review card:
	- Debounced autocomplete search using `GET /api/movements/search`.
	- Canonical name input with Save/Cancel actions.
	- Save posts to `POST /api/exercises/canonical` with `{ exercise_id, canonical_title }`.
	- Inline error handling on save failures.
- Enforced one-open-editor rule in Needs Review:
	- Opening Add Override closes any conflict inline edit.
	- Opening conflict inline edit closes Add Override form.
- Preserved existing conflict table actions and nav badge behavior.
- Backend compatibility update in `main.py`:
	- `GET /api/movements/search` now also returns `items` with `{ exercise_id, title }` while preserving existing `results` title list for back-compat.
- Validation: static diagnostics on `static/index.html` passed (no errors).

## Latest Maintenance Update (2026-05-03, Sync Cooldown Removal)

- Removed sync cooldown enforcement from `POST /api/sync` in `main.py`.
- Removed `_SYNC_COOLDOWN_SECONDS` and the cooldown response path (`status="cooldown"`, `retry_after_seconds`).
- Preserved `_sync_lock` behavior so concurrent sync runs are still prevented (`status="already_running"`).
- Validation: `python -m py_compile main.py` passed.

## Latest Maintenance Update (2026-05-03, Incremental Sync Gate)

- Added `incremental_sync_gate.py` with gate-runner structure aligned to existing gate scripts (`dedup_gate.py`, `conflict_gate.py`).
- Script includes preflight checks for app reachability and `GET /api/sync/last-sync` availability.
- Implemented gates:
	- Gate 1: clears DB `last_sync`, triggers sync, verifies `workout_sessions > 0` and `last_sync` repopulated.
	- Gate 2: triggers second sync and verifies `last_sync` strictly advanced with unchanged `workout_sessions` count.
	- Gate 3: simulates delete path by directly removing one workout from `workout_sessions` and `workout_logs`, then verifies both are gone.
	- Gate 4: verifies canonical title substitution integrity for `exercise_canonical` rows, with SKIP when no canonical entries exist.
	- Gate 5: verifies `last_sync` strictly advances after another sync.
- CLI args: `--base-url`, `--db-path`, `--sync-timeout-seconds`, `--poll-interval-seconds`.
- Final output includes per-gate PASS/FAIL (or SKIP), summary counts, and non-zero exit on failures.
- Validation: `python -m py_compile incremental_sync_gate.py` passed.

## Latest Maintenance Update (2026-05-03, Incremental Sync Migration + API)

- Added one-time startup migration in `database.py:init_db()` guarded by `app_settings.migration_incremental_sync_v1`.
- On first startup after deploy (flag missing), migration deletes `app_settings.last_sync` to force a fresh `initial_import`, then writes the migration flag so subsequent restarts skip it.
- Added `GET /api/sync/last-sync` in `main.py` (before static mounts), returning `{ "last_sync": <value|null> }` from `app_settings`.
- Validation: `python -m py_compile database.py` and `python -m py_compile main.py` passed.

## Latest Maintenance Update (2026-05-03, Importer Sync Refactor)

- Refactored `importer.py` into a two-mode sync flow with extracted `_process_workout(db, workout, canonical_map)` logic shared by:
	- `initial_import(db, canonical_map)` for full `GET /v1/workouts` pagination
	- `incremental_sync(db, last_sync, canonical_map)` for `GET /v1/workouts/events?since=...`
- Preserved existing importer behavior inside `_process_workout()` for:
	- canonical title substitution
	- modality classification and verification resolution
	- `ensure_exercise_mapped()` exercise mapping flow
	- `WorkoutSession` upsert behavior, including verified-session preservation
	- set-level `WorkoutLog` upsert behavior that only updates titles on conflict
- `initial_import()` now clears `workout_logs`, `workout_sessions`, and auto/unreviewed `exercise_mappings` before replaying paginated workout imports.
- `incremental_sync()` now applies Hevy workout events:
	- `deleted` events remove matching `workout_logs` and `workout_sessions`
	- `updated` events re-run `_process_workout()` on the supplied workout payload
- Import sync cursor now persists to `app_settings.last_sync` after successful full or incremental sync passes.
- Updated importer callers in `main.py`, `canonical_gate.py`, and `conflict_gate.py` to use the new `import_hevy_data(db)` entrypoint.
- Validation: `python -m py_compile importer.py` and `python -m py_compile main.py canonical_gate.py conflict_gate.py` passed.

## Latest Maintenance Update (2026-05-03)

- Added `HevyClient.get_workout_events(since, page=1, page_size=10)` in `hevy_client.py` for `GET /v1/workouts/events`.
- Method builds the events URL inline, uses `self.session.get(..., timeout=30)`, clamps `page_size` to the API max of `10`, and returns `{ page, page_count, events: [] }` for `404` responses.
- Method now raises explicit client-side errors for unauthorized, HTTP, JSON decode, connection, timeout, and unexpected failure paths without expanding the repo to a new config/error abstraction.
- Validation: `python -m py_compile hevy_client.py` passed.

## 1) Current Product State

- Today recommendation state now uses a combined score model:
	- `combined_score = 0.80 * subjective_score + 0.20 * objective_score`
	- `subjective_score` comes from the daily check-in (fallback `5.0` when missing)
	- `objective_score` comes from 7-day session volume versus 6-month weekly average volume
- Fatigue score now excludes joint values:
	- `0.45 * tiredness + 0.30 * recovery + 0.25 * soreness`
- Joint health contributes through `recommendation_v2.joint_advisory` (upper/lower advisory and warning states), not through fatigue score weighting.
- Daily recommendation and Today cards are served from `/api/training-load` with shared frontend payload caching.

## 2) Frontend Status (Stage 7 Progress)

- Today, Trend, Workouts, Exercises, Log, Settings tabs are active in single-page `static/index.html`.
- Diagnostics page AI panel script fixes completed in `static/diagnostic.html`:
	- readiness context prompt is now built only after async data load completes inside `loadAndRender()`
	- refresh button handler now closes before `ai-input` listeners are attached, preventing delayed or duplicate listener registration
	- AI assistant JS block indentation normalized to 4-space style to match surrounding script formatting
	- AI assistant now renders markdown: `marked.js` (9.1.6) added via CDN; assistant message bubbles use `marked.parse()` instead of `escapeHtml()`; user message bubbles retain `escapeHtml()` for XSS safety
- Trend view is now the home for chart diagnostics:
	- ATL/CTL/TSB trend chart
	- pattern ATL trend chart
	- Training Stress (Legacy) chart removed entirely (requirement 2.3)
	- Chart window behavior fixed per requirement 2.1:
		- All Trend charts now display a fixed 30-day date range ending today
		- Time Range selector (3 Day/7 Day/14 Day labels) controls chart smoothing only via trailing moving average windows
		- Date axis/x-axis labels remain constant (same 30-day span) regardless of selector choice
		- Trend tooltips now read plotted (smoothed) dataset values so tooltip numbers match line values
	- Legacy dashboard chart/table blocks removed from check-in area:
	- removed orphan `tsbZoneChart` markup
	- removed legacy `tl-wrap` card
	- removed legacy recent workouts summary table
- Log tab: Rec column removed from session log table (column header + cells stripped).
- Movement Trend redesigned in Workouts tab (2026-05-01):
	- Backend movement trend endpoints now aligned to redesigned client contract in `main.py`:
		- added `GET /api/movements/session-trend?exercise=&window=`
		- added `GET /api/movements/volume-trend?exercise=&window=`
		- removed legacy `GET /api/movements/weekly-trend`
		- window validation: `8w|6m|1y|all` (default `6m`)
		- session-trend returns per-session `session_date`, `top_set`, `avg_weight`, `e1rm` for verified sessions
		- volume-trend returns Monday-start weekly `week_start`, `weekly_volume` for verified sessions
		- session `e1rm` uses best set-level value from `calculate_e1rm(weight, reps, rpe, rir)`
		- syntax validation: `python -m py_compile main.py` passed
	- Card remains between Session Verification Queue and Session Log
	- Search row uses placeholder `Search movements...` + clear button and 300 ms debounced autocomplete (`/api/movements/search?q=`)
	- Controls now use two toggle groups on one row:
		- Metric: `e1RM`, `Top Set`, `Avg Weight`, `Volume`
		- Window: `8W`, `6M`, `1Y`, `All`
	- Endpoint routing by metric:
		- `e1RM`/`Top Set`/`Avg Weight` -> `/api/movements/session-trend?exercise=&window=`
		- `Volume` -> `/api/movements/volume-trend?exercise=&window=`
	- Chart rebuilt as single line chart with markers (`spanGaps: false`), sparse x-axis labels (`maxTicksLimit: 6`), and y-axis metric label
	- Y-axis auto-range now applies dynamic 10% padding around finite values
	- Theme redraw retained in `applyTheme()` while Workouts tab is active and movement data is loaded
	- Outside-click dropdown close integrated into existing document click listener using `event.target.closest()` without changing mobile-nav behavior
	- Handler binding is idempotent (`mvtHandlersBound` guard) to prevent duplicate listeners
	- Static diagnostics pass on `static/index.html`: no errors
	- Session Log with filtering, fatigue annotation, expandable detail views, and inline per-row edit
	- Session row panels hardened: Edit and Show Details are now mutually exclusive per row
	- Session Log default page now loads 50 rows, with API-backed Load More pagination
- Today page behavior updates completed:
	- Recommendation card now shows combined-score-driven training-state label/detail text plus Subjective / Objective / Combined score tiles
	- Status card removed entirely (CHECK-IN / PENDING SESSIONS / LAST SYNC tiles removed)
	- Submitted-today check-ins now render as collapsed minimal state with `Edit / Backdate` toggle
	- Collapsed submitted state shows only success banner + `Edit / Backdate` button (no read-only values grid)
	- Toggle expands/collapses full form without saving; collapse resets form fields back to today's saved values
	- Check-in date picker now capped at today (future dates blocked) while still allowing past-date backfill
	- `todayStr()` now uses local date parts (`getFullYear/getMonth/getDate`) instead of UTC `toISOString()`, preventing timezone drift in submitted-state detection
	- `checkTodayReadiness()` is now called on every dashboard tab activation (not only on initial page load), keeping submitted-state display current
- Settings tab updates completed:
	- Session Processing section now includes both conditioning load scale and auto-verify confidence threshold
	- Auto-verify threshold input is populated from `/api/settings/v2` and uses placeholder `0.87`
	- Session Processing now includes local reclassification actions for existing sessions without using Hevy sync
	- Settings section spacing restored to use existing card/grid spacing tokens after inline margin regression
	- Settings container now uses explicit two-column card placement:
		- left column: Hevy API Key, Pattern Sensitivity, Hevy Sync
		- right column: Training State Thresholds, Session Processing
	- Settings tab load flow now always fetches `/api/settings/v2` values even if API-key metadata fetch fails
	- Training State Thresholds fields rehydrate from saved `app_settings` values on each Settings tab open
	- Added subtle Settings footer link to diagnostics page: `View engine diagnostics →` (small, low-contrast text, no button styling)
- Settings tab refactored to 3-card layout (2026-05-01):
	- Removed Pattern Sensitivity card from Settings tab; controls migrated to `static/diagnostic.html`
	- Removed Session Processing card from Settings tab; controls migrated to `static/diagnostic.html`
	- Settings desktop grid updated to `"api sync" / "diagnostics diagnostics"` (2-col top, full-width bottom)
	- Replaced `View engine diagnostics →` text link with a full-width card: title "Engine Diagnostics & Tweaks", explainer, and accent-coloured CTA button
	- `loadV2Settings()`, `savePatternSensitivity()`, `saveSessionProcessingSettings()`, `reclassifySessions()` removed from `static/index.html`
- Diagnostics page settings sections added (2026-05-01):
	- Added Pattern Sensitivity section to `static/diagnostic.html` with Stressed/Neutral threshold inputs, save button, and result feedback
	- Added Session Processing section to `static/diagnostic.html` with Auto-Verify Confidence Threshold input, pending and force reclassification buttons, and result feedback
	- `diagLoadV2Settings()` wired into `loadAndRender()` so inputs populate on page load and Refresh
- Diagnostics page engine snapshot updates completed:
	- Added backend endpoint `GET /api/diagnostics/snapshot` in `main.py`
	- Endpoint returns grouped snapshot payload for subjective/objective/combined score breakdowns, ATL/CTL/TSB, TSB thresholds, joint advisory (raw + current state), and last 10 session classifications
	- Objective/load volume in snapshot reuses `_session_volume()` for 7-day and 180-day aggregations (no inline `weight × reps` reimplementation)
	- Added `Engine Snapshot` section in `static/diagnostic.html` above S&C Assistant panel
	- Engine Snapshot renders grouped blocks: Score Breakdown formulas, Check-in Inputs, Volume Baseline, Training Load, Joint Advisory, TSB Thresholds, Last 10 Sessions
	- Exercise Rename Tool moved out of diagnostics and into the Exercises tab in `static/index.html`:
		- new `Rename Exercise` card above Exercise Movement Mappings
		- helper text: `Use this when an exercise title changes in Hevy. Updates all historical sets and the exercise mapping table.`
		- Current title now uses debounced autocomplete (`/api/movements/search?q=`, min 2 chars, 300 ms)
		- New title remains free-text input
		- submit posts to `POST /api/exercises/rename` and surfaces exact success/404/backend-detail messages
		- clearing Current title clears both inputs and result area
		- outside-click close for dropdown integrated into existing document click listener
		- handler setup is idempotent (`exRenameHandlersBound` guard)
	- Removed Exercise Rename Tool UI and JS handler from `static/diagnostic.html`
	- Added backend endpoint `POST /api/exercises/rename` in `main.py`:
		- body: `{ old_title, new_title }`
		- validates trimmed non-empty values and rejects unchanged rename target
		- transaction updates `WorkoutLog.exercise_title` (case-insensitive old-title match)
		- transaction updates `ExerciseMapping.exercise_title` when a mapping row exists
		- returns `{ updated_sets, mapping_updated }`
		- returns 404 when no WorkoutLog rows match old title
		- syntax validation: `python -m py_compile main.py` passed
		- static diagnostics: `static/index.html` and `static/diagnostic.html` report no errors
	- No-check-in-today state now renders a neutral placeholder while keeping available non-check-in diagnostics visible
- Exercise canonical-title stack implemented (2026-05-02):
	- Added `ExerciseCanonical` model/table in `database.py` with fields:
		- `exercise_id` (PK)
		- `canonical_title` (not null)
		- `created_at`, `updated_at`
	- Startup-safe schema creation added in `database.py:init_db()`:
		- explicit sqlite table-existence check for `exercise_canonical`
		- creates table when missing (idempotent alongside `Base.metadata.create_all`)
	- Import canonical substitution added in `importer.py`:
		- preloads `exercise_canonical` once per sync into dict keyed by `exercise_id`
		- set-level write path uses canonical title when mapping exists
		- falls back to Hevy API title unchanged when mapping missing
	- Canonical API endpoints added in `main.py` before static mounts:
		- `GET /api/exercises/canonical`
		- `POST /api/exercises/canonical`
		- `DELETE /api/exercises/canonical/{exercise_id}`
		- GET joins canonical rows with most-recent `workout_logs.exercise_title` per `exercise_id` (nullable)
	- Exercises tab UI updated in `static/index.html`:
		- Added `Exercise Name Overrides` card above `Rename Exercise`
		- card loads from `GET /api/exercises/canonical` on each Exercises-tab activation
		- table columns: `Hevy Title | Your Name | Action`
		- inline Edit/Save flow posts to `POST /api/exercises/canonical` and refreshes rows
		- empty state copy: `No overrides set. Exercises use names from Hevy.`
- Canonical gate script added (2026-05-02):
	- New `canonical_gate.py` validates canonical CRUD endpoints against running local app
	- Script simulates importer path with controlled fake-Hevy payload to verify set-title substitution deterministically
	- Outputs PASS/FAIL per gate and summary with exit code
- Dedup gate script added (2026-05-02):
	- New `dedup_gate.py` validates dedup/index protections against SQLite DB + running local API sync path
	- Gate 1 checks index existence for `uq_workout_logs_set` in `sqlite_master`
	- Gate 2 checks duplicate natural-key groups `(workout_id, exercise_id, set_number)` are zero
	- Gate 3 records row counts before/after `POST /api/sync` with `/api/sync/status` polling and enforces `delta <= 10`
	- Prints PASS/FAIL per gate with final summary and exits non-zero on failure
- Dedup DB migration fix applied (2026-05-02):
	- Root cause: `init_db()` never created index name `uq_workout_logs_set`; model-level `UniqueConstraint` (`uq_workout_set`) did not satisfy gate check
	- `database.py:init_db()` now runs startup dedup on `(workout_id, exercise_id, set_number)` keeping earliest `id`
	- `database.py:init_db()` now executes `CREATE UNIQUE INDEX IF NOT EXISTS uq_workout_logs_set ON workout_logs (workout_id, exercise_id, set_number)`
	- Migration is idempotent and enforces hard DB-level uniqueness independent of importer behavior
- Import pipeline updates completed:
	- Session modality now uses two-layer detection: title keyword pass first, then existing exercise-level fallback
	- Title keyword sets include abbreviation codes (` ST`, ` HYP`, ` CON`, ` CAR`) and `strongman`
	- `+` in title with any modality keyword/code forces mixed handling (`0.70` + mixed-session note), with dominant modality chosen by first keyword position
	- Import now parses title sRPE tags in format `@N` / `@N.N` (`0..10`) and stores parsed value to `workout_sessions.srpe`
	- Verification card display title strips `@N` tag for readability while stored session title remains unchanged
	- Valid sRPE title tag is a conditioning signal when no other modality keyword/code is present (`conditioning`, confidence `0.95`)
	- Conditioning/Cardio sessions can auto-verify when confidence `>= 0.87` only if sRPE came from title tag
	- Mixed title matches are flagged with a session note and reduced confidence to force manual review
	- Sync/reclassification guard added in `importer.py`: existing `verified` sessions now use metadata-only upsert updates (date/title/time/duration/updated_at) and preserve classification fields (`modality`, `modality_confidence`, `modality_note`, `verification_status`, `verified_at`, `srpe`)
	- WorkoutLog conflict policy updated in `importer.py` for set rows:
		- changed set insert from `on_conflict_do_nothing()` to `on_conflict_do_update()` on unique key (`workout_id`, `exercise_id`, `set_number`)
		- on conflict, only `exercise_title` and `workout_title` are updated so Hevy title renames propagate
		- all training data fields remain unchanged on conflict (`weight_lbs`, `reps`, `rpe`, `rir`, `estimated_1rm`, `is_conditioning`)
		- syntax validation: `python -m py_compile importer.py` passed
- Admin data-repair endpoint added (2026-05-01):
	- Added backend endpoint `POST /api/admin/backfill-sessions` in `main.py`
	- Endpoint backfills missing `workout_sessions` rows for `workout_id` values present in `workout_logs` but absent in `workout_sessions.hevy_workout_id`
	- For each missing workout id, source row is the earliest `WorkoutLog` record by `(date, id)` for deterministic mapping
	- Backfilled defaults:
		- `hevy_workout_id = workout_id`
		- `workout_date = earliest WorkoutLog.date`
		- `workout_title = earliest WorkoutLog.workout_title`
		- `modality = "strength"`
		- `modality_confidence = 0.0`
		- `verification_status = "verified"`
		- `verified_at = datetime.utcnow()`
		- `start_time/end_time/duration_minutes/srpe = null`
	- Response contract: `{ "backfilled": N }`
	- Syntax validation: `python -m py_compile main.py` passed
	- Runtime verification note: local API start currently blocked in this environment by missing dependency `cryptography` (`ModuleNotFoundError`)

## 3) Check-In UX (Latest Overhaul)

- Check-in card moved to first card in Today view (input before outputs).
- Form now renders immediately when today is pending; no click required.
- When today is already submitted:
	- form auto-hides
	- collapsed minimal submitted panel is shown (banner + `Edit / Backdate` only)
	- no read-only values grid is shown in either collapsed or expanded modes
- Check-in controls replaced with inline 0-4 button groups for all 8 fields:
	- tiredness, recovery
	- quad/knee, hip/posterior, upper push, upper pull
	- upper joint, lower joint
- Endpoint labels implemented per field scale direction:
	- Recovery: Poor -> Full
	- Joint fields: Good -> Pain
	- Others: None -> Extreme/Severe
- Date picker remains present and supports backdated submissions.
- Submit mapping and backend endpoint behavior are unchanged.

## 4) Validation Snapshot

- Joint-advisory backend gate script: PASS.
- Trend chart relocation lifecycle checks: PASS (first activation, tab switching, refresh stability, no duplicate chart instance behavior).
- Check-in UX checks: PASS for
	- first-card placement
	- pending immediate visibility
	- submitted collapse showing only banner + `Edit / Backdate` toggle
	- no read-only values grid rendered at any point in submitted mode
	- collapse without save resets editor fields to today's canonical values
	- no dropdowns
	- all 8 fields and group headers
	- endpoint direction labels and non-interactive endpoint text
	- date picker max bound set to today (past-date backfill preserved)
	- mobile 375px width, no overflow, 44px touch targets, full-width submit
	- backdated date submission behavior
- Workouts/session-processing backend gate script: PASS for
	- session-processing save/load and threshold validation range
	- edit behavior preserving status (`pending` stays pending, `verified` stays verified)
	- verification path still promoting pending sessions
	- pagination `limit`/`offset` behavior
	- auto-verify policy checks (strength/hypertrophy thresholding; conditioning/cardio pending unless sRPE title-tag auto-verify condition is met)
- Session processing default/migration updates: PASS
	- runtime default aligned to `0.87`
	- startup migration updates legacy stored `0.90` and `0.95` values to `0.87`
	- startup seeding still fills missing `auto_verify_confidence_threshold` with `0.87`
- Title modality detection gate script: PASS for
	- `CC4.1.1(A) ST` -> strength at confidence `0.95` (auto-verifies at threshold `0.87`)
	- `CC4.1.1(A) HYP` -> hypertrophy at confidence `0.95` (auto-verifies at threshold `0.87`)
	- `CC4.1.1(A) ST + CON` -> mixed handling with confidence `0.70`, mixed-session note present, pending queue
	- `CC4.1.1(A) HYP + CON` -> mixed handling with confidence `0.70`, mixed-session note present, pending queue
	- `STRICT PRESS` -> no ` ST` false-positive match (falls through)
	- `STRONGMAN Medley` -> conditioning at confidence `0.95`
	- `METCON` -> conditioning at confidence `0.95` and remains pending
	- `CC4.1.1(A)` (no code) -> falls through to existing exercise-level inference unchanged
	- case-insensitive title matching
	- legacy threshold values `0.90` and `0.95` migrated to `0.87` on startup
- sRPE title-tag gate script: PASS for
	- `CC4.1.6 CON @7` -> `conditioning`, `srpe=7.0`, auto-verified
	- `CC4.1.6 METCON @8` -> `conditioning`, `srpe=8.0`, auto-verified
	- `Saturday WOD @6.5` -> `conditioning`, `srpe=6.5`, auto-verified
	- `CC4.1.6 METCON` (no tag) -> `srpe=null`, pending queue behavior unchanged
	- `@11` / `@abc` invalid tags ignored
	- verification-card title strips `@N` tag for display
	- case-insensitive keyword matching remains intact alongside sRPE parsing
	- `CC4.1.1(A) ST @7` remains strength-classified (sRPE parsing does not override ST modality)
	- `CC4.1.6 @7` with no other modality keywords -> `conditioning`, `srpe=7.0`, auto-verified
	- aggregate result: `SRPE_TITLE_GATES_PASS`
- Local session reclassification gate script: PASS for
	- pending sessions reclassified from current stored workout data using current classifier rules
	- verified sessions skipped during normal reclassification runs
	- force-all reclassification updates verified sessions only when explicitly requested
	- result summary counts returned as expected
	- no Hevy API import/sync path invoked during reclassification
- Settings TSB reload gate script: PASS for
	- custom TSB thresholds saved (`40`, `15`, `-20`, `-50`)
	- settings payload re-read (tab reopen equivalent) returns saved values, not defaults
	- fresh DB session re-read (page refresh equivalent) returns saved values, not defaults
	- default auto-verify threshold baseline confirmed at `0.87`
- Settings layout fix: PASS
	- explicit two-column grouping matches intended UX
	- mobile collapse remains single-column under responsive breakpoint
- Today recommendation/status cleanup: PASS
	- no rendered fatigue/tier line on recommendation card
	- no Status card markup or render path remains
	- removed dead `.today-fatigue-line` CSS definition
- Combined-score Today recommendation switch: PARTIAL VALIDATION
	- backend recommendation state now comes from combined-score thresholds instead of TSB thresholds
	- Today recommendation card renders Subjective / Objective / Combined score tiles from `recommendation_v2`
	- formula explainer line added below score tiles: `Combined = (Subjective × 80%) + (Objective Load × 20%)`
	- pattern explainer text added below pattern grid describing the 7-day verified-session basis
- Pattern dot stress label fix: DONE
	- `_stress_level_label()` in `main.py` switched from 3-bucket status string to 5-point `dots_filled` int: `1→Fresh`, `2→Min. Stress`, `3→Normal Stress`, `4→Moderate Stress`, `5→High Stress`
	- JS fallback label in `static/index.html` updated to derive from `dots_filled` using same 5-label array
	- `main.py` syntax validated with `py_compile`
	- full local route execution remains blocked in the currently configured Python interpreter because it does not have FastAPI installed
- Diagnostics snapshot + importer verified-session sync guard: PARTIAL VALIDATION
	- `importer.py` now checks for existing session by `hevy_workout_id` before upsert
	- Existing `verification_status == verified` sessions are protected from reclassification on sync
	- New endpoint `GET /api/diagnostics/snapshot` added and wired to diagnostics UI
	- Snapshot objective/load volume calculations use `_session_volume()` helper for both 7-day and 180-day windows
	- Python syntax validation passed for `importer.py` and `main.py`; static diagnostics report clean for touched HTML files
	- Full live endpoint/runtime validation remains pending in a local environment with app dependencies installed
- Nav active class hardcode fix: DONE
	- Removed hardcoded `active` class from desktop `.nav-tabs` Today button and mobile `.mobile-drawer-nav` Today button in `static/index.html`
	- Runtime `activateTab()` already manages the `active` class; no JS changes needed
- Settings grid mobile fix: DONE
	- Removed invalid `grid-template-areas: none` from `@media (max-width: 900px)` block in `static/index.html`
	- Added `grid-area: auto` resets for all 5 `.settings-card-*` children within the same breakpoint so cards stack in DOM order
- Settings CSS corruption hotfix: DONE
	- Removed stray `grid-template-areas` string literals that were incorrectly inserted into the `[data-theme="light"]` variable block
	- Restored missing `html { ... }` wrapper in the Base CSS section
	- Removed misplaced `.today-chart-*` rules that were accidentally injected inside the dark theme token block and relocated those rules to the Today section
	- Restored mobile `.today-chart-wrap` sizing rule under a proper media query block
- TSB Settings card removal: DONE
	- Removed obsolete `Training State Thresholds` card from `static/index.html`
	- Removed frontend-only JS support for `saveTrainingStateThresholds()`, the four TSB inputs, and `tsb-result`
	- Rebalanced desktop Settings grid to `api/pattern` then `session/sync`; mobile reset now applies only to remaining Settings cards
- 7-day readiness trend: PARTIAL VALIDATION
	- Added `GET /api/readiness/combined-history` in `main.py` returning fixed day-by-day history with `date`, `objective_score`, `subjective_score`, and `combined_score`
	- Historical no-check-in days now return `objective_score` plus `subjective_score=null` and `combined_score=null`
	- Added Today-tab `7-Day Readiness Trend` Chart.js card in `static/index.html` below the recommendation card and above the pattern grid
	- Chart uses null gaps, short weekday labels, y-axis `0..10`, and five readiness-zone background bands
	- Updated readiness-zone band fills for stronger contrast and clearer state separation; current palette uses deep navy / cyan / green / amber / red bands
	- Updated readiness chart x/y gridline color to `rgba(128,128,128,0.15)` for light/dark visibility parity
	- Syntax/static validation passed for `main.py` and `static/index.html`; desktop Settings layout and Today card placement verified in-browser
	- Full live API/runtime verification and true sub-900px browser rendering remain pending in an environment with the app served normally
- CSS corruption repair verification: DONE
	- `<style>` block brace audit passed: opening and closing braces are equal and running depth never goes negative
	- Static diagnostics pass for `static/index.html` reports no errors
	- Runtime style check confirms body font stack and theme colors now apply from CSS instead of fallback defaults
- Canonical stack validation: PASS
	- `database.py` bootstrap check confirms `exercise_canonical` exists with requested columns and PK/nullability shape
	- Focused runtime check confirms importer stores canonical title in `workout_logs` when canonical mapping exists
	- Canonical CRUD route checks passed via local handler/runtime test
	- `canonical_gate.py` execution result: `SUMMARY: 6 passed, 0 failed`
	- Syntax/error checks passed for touched files: `database.py`, `importer.py`, `main.py`, `static/index.html`, `canonical_gate.py`
- Dedup gate validation: PARTIAL
	- Syntax check passed: `python -m py_compile dedup_gate.py`
	- Runtime gate execution against `/data/hevy_fatigue.db` pending environment-specific DB path availability
- Dedup index migration fix: PASS
	- `python -m py_compile database.py` passed after `init_db()` migration update
- Conflict gate script created: SYNTAX PASS
	- `conflict_gate.py` written with GateRunner, 7 gates, preflight, and cleanup blocks
	- `python -m py_compile conflict_gate.py` passed with no errors
	- Runtime execution blocked pending implementation of ExerciseConflict model, importer detection, main.py endpoints, and index.html conflict UI
- Conflict stack implementation: COMPLETE (syntax validated)
	- `database.py`: `ExerciseConflict` model added (exercise_id PK, hevy_title, stored_title, detected_at, resolved, resolved_at); `init_db()` migration block creates `exercise_conflicts` table on startup
	- `importer.py`: preloads `already_flagged` set and `stored_titles` dict per sync; upserts `ExerciseConflict` row when title drifts with no canonical and no existing open flag
	- `main.py`: `ExerciseConflictResolveInput` Pydantic model; GET `/api/exercises/conflicts`; POST `…/{id}/resolve` (upserts canonical, marks resolved); POST `…/{id}/dismiss` (marks resolved only)
	- `static/index.html`: Needs Review card (hidden until conflicts exist); nav badge on desktop + mobile exercises buttons; `loadExerciseConflicts()`, `renderExerciseConflictTable()`, `resolveExerciseConflict()`, `dismissExerciseConflict()` JS functions
	- `python -m py_compile` passed for all touched files; JS brace count balanced (842/842)
- Sync response contract + conflict detection refactor: COMPLETE (validated)
	- `main.py`: `POST /api/sync` success payload changed to `{ "status": "complete", "synced_at": "<utc iso>" }`; removed `new_sets` from sync response
	- `static/index.html`: `runSync()` now renders `Sync complete` with `synced_at` timestamp and no set-count messaging; existing cooldown/already-running behavior unchanged
	- `importer.py`: removed per-loop conflict logic (`already_flagged`, `stored_titles`, and inline `ExerciseConflict` upsert)
	- `importer.py`: added `detect_exercise_conflicts(db)` post-sync pass:
		- finds `exercise_id` values with multiple distinct `workout_logs.exercise_title`
		- excludes IDs with canonical mappings in `exercise_canonical`
		- excludes IDs with existing unresolved rows in `exercise_conflicts`
		- upserts conflict row using newest title by `date desc, id desc` and oldest title by `date asc, id asc`
	- Validation:
		- `python -m py_compile importer.py` — OK
		- `python -m py_compile main.py` — OK
		- `static/index.html` diagnostics — OK (`<script>`/`</script>`: 3/3, JS braces: 841/841)

## 5) Open Items / Next Backlog

Source of truth: see `backlog.md` for current outstanding work and release-priority tracking.
This section is historical context and may lag behind `backlog.md`.

Priority A

- Movement Trend live validation: browser click-through with real populated data (search → select → chart renders, week toggle reloads, clear resets, theme toggle rebuilds chart).
- Manual visual QA on real populated workout/check-in data for Trend and Session Log realism (including inline row edit, mutual exclusion of row panels, and verified/pending filters).
- Confirm final spacing/typography rhythm in Today card stack after check-in overhaul.
- Run cross-device pass (Safari iOS + Chrome Android) for check-in button groups and endpoint labels.
- Browser click-through regression pass for Workouts:
	- verify queue -> log immediate refresh
	- Edit/Cancel/Save flows on both pending and verified rows
	- Show Details expand/collapse while edit mutual exclusion remains enforced

Priority B

- Optional cleanup of obsolete helper names/comments that still reference legacy dashboard wording.
- Add a short release checklist for pre-commit UI and endpoint regression checks.

## 6) Quick Resume Prompt

Use this when you come back:

"Read plan.md first. Movement Trend feature is complete (backend + frontend). Continue from Priority A validation with real data. Preserve the new Today-first check-in flow, Trend-owned charts, and combined-score Today recommendation model."

