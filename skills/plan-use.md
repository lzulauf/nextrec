---
name: plan-use
description: 'Create and maintain implementation plans in .plans with clear scope, technical depth, pseudocode, diagrams, phases, checklists, milestones, acceptance criteria, and cross-links to related plans or skills. Use when preparing or re-scoping work.'
argument-hint: 'Describe the initiative and constraints to generate a phased execution plan'
user-invocable: true
---

# Plan Use

Use this skill to draft clear, execution-ready planning documents and keep them structurally accurate as scope evolves.

Companion skills: plan-implementation for phase-by-phase execution, function-naming for naming standards, immutable-types for immutable-model constraints, decision-writing for approach-selection docs, and readme-writing for README/docs ownership and update flow.

## When To Use

- Starting a multi-step feature or refactor
- Aligning existing APIs to conventions before a major change
- Breaking large work into phases and milestones
- Creating prerequisite plans and dependency ordering
- Defining success criteria before coding
- Re-scoping phases when requirements change
- Planning public API or behavior changes that require documentation updates

## Out Of Scope

- Executing implementation phase checklists step-by-step (use plan-implementation)
- Preparing per-phase PR/commit choreography and commit messages (use plan-implementation with commit-message-writing)
- Recording day-by-day execution logs while coding (use plan-implementation implementation notes flow)

## Plan Location and Naming

- Store plan files in .plans.
- Keep active (Drafting, Approved, or Implementing) plans at the .plans root.
- Archive finished plans under .plans/archive/.
- Use concise snake_case names ending in _plan.md when possible.
- Keep one primary goal per plan.
- Add cross-links when one plan depends on another.

Examples:
- .plans/conventions_alignment_plan.md
- .plans/archive/degree_support.md

## Required Plan Sections

Include these sections in order unless there is a strong reason not to:

1. Status
2. Goal
3. Why this comes first (optional but recommended)
4. Scope
5. Out of scope
6. Technical design details
7. Testing approach
8. Documentation approach
9. Progress checklist
10. Phases (numbered, with concrete deliverables)
11. Execution order recommendation
12. Implementation notes (append-only log; may be initialized empty during drafting)
13. Risks and mitigations (optional)
14. Acceptance criteria

## Status Section Rules

- Include an explicit section named "Status" at the top of every plan, immediately before "Goal".
- Allowed values are exactly:
	- Drafting
	- Approved
	- Implementing
	- Done
	- Rejected
- Lifecycle rules:
	- Default new-plan state is Drafting.
	- When a draft is accepted and ready to execute, update status to Approved.
	- Approved indicates implementation can start without further design edits unless scope changes.
	- When implementation begins, update status to Implementing as the first implementation step.
	- When implementation completes successfully, update status to Done and move the plan to .plans/archive/.
	- If the plan is declined, update status to Rejected and move the plan to .plans/archive/.
- Active plans in .plans/ should use Drafting, Approved, or Implementing only.
- Archived plans in .plans/archive/ must use Done or Rejected only.
- Update status whenever checklist state or plan lifecycle changes.
- For plans that remain in Drafting, include at least 1-3 concrete draft-improvement suggestions in planning updates.

## Technical Design Details Rules

- Include an explicit section named "Technical design details" for any plan that changes code.
- This section should be specific enough that implementation can begin without rediscovering major design choices.
- Cover at least:
	- Canonical types/data models and invariants.
	- API signatures for new or changed public methods.
	- Module/file touchpoints (where each change will occur).
	- Error and validation semantics (what raises, accepted forms).
	- Compatibility and migration notes (what breaks, what is removed, and when).
- Prefer explicit examples for ambiguous contracts (for example input and output forms).
- If design uncertainty remains after this section, create/link a decision doc before coding.

### Technical depth requirements

- For non-trivial behavior changes, include light pseudocode representations of core algorithms.
- For new apis, include sample calling code that demonstrates usage.

### Diagram requirements

- For non-trivial class relationships, calling sequences, etc. include diagrams that visually represent the logic or relationships.
- Mermaid diagrams and/or ascii art can be used as appropriate.
- Keep diagrams small and focused; brevity and broad understanding are more important than showing every possible detail.

## Testing Approach Section Rules

- Include an explicit section named "Testing approach" in each plan.
- Describe intended coverage by type (for example unit, integration, regression).
- Identify key test targets and critical edge cases.
- Describe mocking/fixture strategy and whether shared fixtures are needed.
- Include how tests will be run and what constitutes passing validation.
- Include expected test delta classification: new tests, updated tests, both, or no test delta.
- If no test changes are expected, state that explicitly with rationale under a "No test delta rationale" note.

## Documentation Approach Section Rules

- Include an explicit section named "Documentation approach" for plans that change public APIs, parsing behavior, validation behavior, examples, or user-facing workflows.
- Identify documentation touchpoints directly (for example README.md, docs/README.md, docs/api-overview.md, and affected guides).
- Include expected docs delta classification: README updates, docs updates, both, or no docs delta.
- If no documentation changes are expected, state that explicitly with rationale under a "No docs delta rationale" note.
- Include how documentation changes will be validated (for example example snippets updated, link paths checked, terminology consistency verified).

## Progress Checklist Rules

- Use markdown checkboxes.
- Keep items outcome-based, not vague activity labels.
- Include both phase-level and milestone-level checks when relevant.
- Keep checklist wording stable so it can be updated over time.
- Keep checklist status up to date as work progresses.
- Mark checklist items complete immediately when the corresponding outcome is met.
- During implementation, checklist completion is performed via plan-implementation.

Checklist style example:
- [ ] Phase 0: Inventory complete
- [ ] Phase 1: Canonical names selected
- [ ] Milestone A complete

## Phase Design Rules

- Each phase should answer: what changes, where, and how success is verified.
- Prefer small, testable phase boundaries.
- Put compatibility and migration phases before cleanup/removal phases.
- Explicitly call out docs and tests phases.
- Include technical deliverables in each phase (for example signature updates, type migrations, parser behavior).
- For model/API phases, list target files/modules directly.
- Define intended PR boundaries by phase so plan-implementation can prepare one commit message per PR boundary.

## Implementation Notes Section Rules

- Include an explicit `Implementation notes` section in every active plan.
- During drafting, initialize with a placeholder bullet such as `- No implementation notes yet.`
- During execution, plan-implementation appends dated, phase-scoped notes.
- Keep this section append-only except for factual corrections.

## Naming and API Planning Rules

- Use canonical names in new plan sections.
- If aliases are needed, mark them as compatibility aliases with retirement intent.
- Avoid planning parallel permanent APIs that do the same thing.
- For naming decisions, load function-naming.

## Pre-Implementation Dependency Rules

- If a conventions or migration prerequisite exists, state it near the top as Prerequisite.
- Link dependent plans directly.
- Do not start downstream feature phases until prerequisite checklist gates are met.
- If a plan depends on unresolved approach choices, create a decision document in decisions/ as a Markdown file and link it from the plan.

## Plan Review Checklist

- Status section exists at the top and reflects current lifecycle state.
- Status value is one of: Drafting, Approved, Implementing, Done, Rejected.
- Archived plans explicitly show Done or Rejected status.
- Sections are complete and in logical order.
- Scope and out-of-scope are explicit.
- Technical design details are explicit, concrete, and implementation-ready.
- Technical design details include implementation pseudocode for non-trivial logic.
- Technical design details include usage pseudocode that demonstrates intended capabilities.
- Technical design details include Mermaid/ASCII diagrams when they materially improve clarity, or a rationale for omission.
- Testing approach section is explicit and actionable.
- Testing approach explicitly states expected test delta classification.
- Any "no test delta" claim includes rationale and is consistent with the planned code changes.
- Documentation approach section is explicit and actionable when user-facing behavior or APIs change.
- Documentation approach explicitly states expected docs delta classification.
- Any "no docs delta" claim includes rationale and is consistent with the planned code changes.
- Checklist is actionable and measurable.
- Checklist status is current and reflects real execution progress.
- Phases map to concrete files/modules.
- Test and documentation work are included.
- Acceptance criteria are unambiguous.
- Acceptance criteria include test validation evidence expectations (focused and full test runs, or justified exception).
- Acceptance criteria include documentation validation expectations (updated references/examples or justified exception).
- Dependencies and prerequisites are linked.
- Finished plans are moved to .plans/archive/.

## Update Procedure for Existing Plans

1. Preserve plan intent and existing completed checklist items.
2. Apply minimal edits for consistency with current conventions.
3. Ensure the top Status section exists and is accurate.
4. Update all internal references after renames.
5. Update testing and documentation approach if scope, risk, or validation strategy has changed.
6. Update implementation pseudocode, usage pseudocode, and diagrams when behavior or architecture changes.
7. Update checklist states to reflect the current project state.
8. Re-read full plan to ensure no stale names remain.
9. Note major deltas in commit/PR summary.

## Plan Completion and Archiving

- Treat a plan as finished when acceptance criteria are met and the progress checklist is complete.
- Before archiving a completed implementation, update the plan's top Status section to Done.
- If a plan is not being pursued, update status to Rejected before archiving.
- Add a brief completion note before archiving when useful (for example: completed date and any key follow-up links).
- Move the plan from .plans/ to .plans/archive/.
- Update references from active plans so links point to the archived file path.
- Keep archived plans as historical records and avoid substantive rewrites after archival.
- If implementation notes exist, preserve them verbatim as the execution record.

## Drafting Improvement Guidance

- When a plan is still Drafting, provide concrete suggestions to improve execution readiness.
- Suggest improvements in these categories when applicable:
	- missing API signatures/contracts,
	- unclear validation/test strategy,
	- missing docs delta classification,
	- ambiguous phase boundaries or dependencies.
- Keep suggestions concise and actionable (1-3 items by default).
