---
name: critical-bug-hunt
description: 'Inspect recent commits to find and fix only high-severity correctness bugs. Use for data loss, crashes, security exposure, silent corruption, write-loss races, and major user-facing breakage.'
argument-hint: 'Target branch/commit range and risk area to inspect'
user-invocable: true
disable-model-invocation: false
---

# Critical Bug Hunt

## Outcome
Produce a high-confidence result from recent changes:
- A minimal fix for a confirmed critical bug, with validation evidence.
- Or a short no-critical-bugs-found summary (expected most runs).

## Severity Scope
Only treat issues as in-scope when they can cause one of:
- Data loss or corruption
- Crash in a critical path
- Security hole (including auth/permission bypass)
- Significant user-facing breakage

Ignore style, low-impact UX nits, speculative risks without a concrete trigger, and minor edge cases.

## Inputs To Gather
1. Establish inspection target:
   - default branch and current branch
   - commit range to inspect
2. Enumerate changed files and behavioral diffs.
3. Identify high-blast-radius paths:
   - persistence and migrations
   - API request/auth boundaries
   - background sync/import loops
   - hot user flows
   - external API sync chains (especially swallowed exceptions that mark failed syncs as successful)
   - Uncertain finding => document findings only, do not open PR

## Procedure
1. Map behavioral changes
   - Read diffs and classify each change by risk type (storage, concurrency, auth, lifecycle, parsing).
   - Prioritize diffs that alter write paths, state transitions, or permission checks.
2. Trace full execution path
   - Walk caller chain from entrypoint to sink (database write, external call, response contract).
   - Include downstream effects and rollback/failure behavior.
3. Test trigger plausibility
   - Construct a concrete scenario that would trigger failure in production.
   - Require realistic preconditions, not contrived assumptions.
4. Decide severity gate
   - If no concrete high-severity scenario exists, do not mark as critical.
   - If scenario is concrete and impact is high, proceed to fix.
5. Implement minimal fix
   - Make the smallest safe change that closes the root cause.
   - Avoid broad refactors in the same change set.
6. Validate
   - Run targeted tests and/or focused runtime checks for the failing path.
   - Add/update tests when practical to lock behavior.
7. Report outcome
   - If fixed, provide bug, impact, root cause, fix summary, and validation evidence.
   - If none found, provide short no-critical-bugs-found summary.

## Decision Points
- Criticality decision:
  - Concrete trigger + high impact => critical bug
  - Missing trigger or low impact => not critical
- Action decision:
  - Critical bug with high confidence => implement fix
  - Uncertain finding => report to Slack, do not open PR
- PR decision:
  - Open PR only when bug reality and fix correctness are both high confidence

## Quality Checks Before PR
- Trigger scenario is explicit and reproducible.
- Root cause explains why existing checks did not prevent failure.
- Fix addresses root cause directly, not only symptoms.
- Validation demonstrates behavior is corrected.
- Change scope is minimal and avoids unrelated refactors.

## Output Contract
If fixed, always include:
- Bug and impact
- Root cause
- Fix and validation performed

If no critical bug is found, output:
- no critical bugs found
