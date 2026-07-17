---
name: plan-implementation
description: 'Execute an existing .plans document phase by phase with explicit status updates, implementation notes, and one prepared commit message per PR boundary.'
argument-hint: 'Reference the plan file and current phase to get a structured implementation workflow'
user-invocable: true
---

# Plan Implementation

Use this skill to execute an existing plan in controlled, reviewable increments.

Companion skills: plan-use for plan authoring/re-scoping, test-writing for required test deltas, test-running for validation, readme-writing for docs updates, and commit-message-writing for commit message quality.

## When To Use

- User asks to implement an existing plan
- Work is expected to land in multiple phases or PRs
- You need strict progress/status hygiene while coding
- You need implementation notes that capture what actually landed
- You need per-PR commit message preparation tied to concrete deltas

## Out Of Scope

- Creating a new plan from scratch (use plan-use)
- Replacing unresolved architecture decisions with implementation guesses (use decision-writing)
- Combining unrelated phases into one PR when the plan defines separate review boundaries

## Required Preconditions

Before coding any phase:

1. Open the plan file in `.plans/` and verify required sections exist.
2. Confirm `Status` is set to `Approved` or `Implementing`.
3. If status is `Approved`, update it to `Implementing` as the first execution step before code changes.
4. Confirm the target phase has explicit deliverables and acceptance checks.
5. Confirm test/docs expectations for the phase are explicit.
6. If these are missing or stale, update the plan with `plan-use` first.

## Phase-By-Phase Execution Loop

Repeat this loop for each phase, in order:

1. Select exactly one active phase.
- Do not start the next phase until the current phase checklist outcomes are complete or explicitly re-scoped.

2. Define PR/commit boundary for the phase.
- Default rule: one implementation phase maps to one PR.
- Default rule: prepare one primary commit message per PR boundary.
- If a phase must be split across multiple PRs, record the split rationale in the plan before coding.

3. Implement only phase-scoped changes.
- Keep changes constrained to listed modules/files for that phase.
- Defer out-of-scope cleanup unless it blocks acceptance criteria.

4. Validate phase outcomes.
- Run the focused tests named in the plan's Testing approach.
- Run broader regression checks when the plan requires them.
- Ensure docs/examples are updated when the phase includes user-visible behavior/API changes.

5. Update plan tracking immediately.
- Mark completed checklist items at once.
- Update phase progress markers (not-started/in-progress/completed language if present).
- Keep `Status: Implementing` until final completion.

6. Append implementation notes.
- Maintain an append-only `Implementation notes` section in the plan.
- Add one dated entry per phase completion with:
  - what changed,
  - what tests/docs were updated,
  - known follow-ups or deferred items.

7. Prepare commit message for the PR.
- Generate the message from staged phase deltas only.
- Use commit-message-writing conventions unless the user requests a different template.
- Include behavior/API/test/docs highlights and any compatibility caveats.

8. Finalize phase readiness.
- Confirm plan and code state match.
- Confirm commit message scope matches exactly what is staged for that phase PR.

## Status and Archival Rules During Implementation

- `Approved` means the plan is accepted and ready to execute but coding has not started.
- Keep `Status: Implementing` while any plan phase remains open.
- When all acceptance criteria are met:
  - set `Status: Done`,
  - add a final implementation note summarizing closure,
  - move the plan to `.plans/archive/`.
- If the effort is halted permanently:
  - set `Status: Rejected`,
  - record why in implementation notes,
  - move to `.plans/archive/`.

## Implementation Notes Format

Use this structure inside the plan under `## Implementation notes`:

```md
### YYYY-MM-DD - Phase N
- Scope completed: ...
- Code touchpoints: ...
- Tests: ...
- Docs: ...
- Commit/PR: ...
- Follow-ups: ...
```

Rules:

- Append new entries; do not rewrite prior historical entries except factual corrections.
- Keep entries concise and outcome-focused.
- Include commit hash/PR link when available.

## PR and Commit Preparation Rules

- Keep each PR tied to one coherent phase outcome.
- Do not mix unrelated plan phases in a single PR by default.
- Prepare commit messages after staging the intended phase-only delta.
- If additional fixes are required during review, record whether they are phase-scope or follow-up scope.

## Review Checklist

- Correct plan file selected and status is `Implementing`.
- Current phase scope is explicit and bounded.
- Current phase checklist outcomes are complete before moving on.
- Test/docs requirements for the phase were executed.
- `Implementation notes` were appended with a dated phase entry.
- Commit message prepared from staged phase-only changes.
- Plan status/archive actions were applied correctly at completion.
