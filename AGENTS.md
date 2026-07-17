# AGENTS.md

Guidance for coding agents and contributors working in this repository.

## Purpose

Use skills as the primary source of detailed implementation conventions. Keep this file focused on where those conventions live and when to load them.

## Available Skills

### test-writing

- Path: skills/test-writing.md
- Use when:
	- Writing or updating unit tests
	- Adding regression coverage for bug fixes
	- Expanding edge-case/validation matrices with parametrization
	- Testing optional dependency paths with deterministic mocks
	- Implementing behavior or public contract changes that require test deltas

### test-running

- Path: skills/test-running.md
- Use when:
	- Running full or focused pytest commands
	- Reproducing and triaging test failures
	- Running slow tests with --runslow intentionally
	- Checking coverage with pytest --cov=src

### plan-use

- Path: skills/plan-use.md
- Use when:
	- Creating or updating plans in .plans before implementation starts
	- Breaking initiatives into phases, milestones, and checklists
	- Defining scope, out-of-scope, prerequisites, and acceptance criteria
	- Coordinating dependency order between multiple plans
	- Declaring expected test delta (new, updated, none-with-rationale) for planned code changes

### plan-implementation

- Path: skills/plan-implementation.md
- Use when:
	- Executing an existing plan one phase at a time
	- Updating in-flight plan status/checklists during implementation
	- Recording dated implementation notes while phases are completed
	- Preparing one commit scope/message per phase PR boundary
	- Closing out plans (Done/Rejected) and archiving after implementation

### next-work-selection

- Path: skills/next-work-selection.md
- Use when:
	- Prioritizing what to do next from .plans
	- Ranking active plans by status, dependencies, and remaining checklist work
	- Deciding whether to close out near-complete work or start new draft plans
	- Identifying planning hygiene tasks (archive completed plans, resolve status drift)

### readme-writing

- Path: skills/readme-writing.md
- Use when:
	- Creating or restructuring README and docs content
	- Splitting a large README into focused docs pages
	- Defining ownership boundaries between README.md and docs/
	- Reducing duplicated documentation content and improving cross-links
	- Updating README/docs for public API, behavior, or usage changes

### docstring-writing

- Path: skills/docstring-writing.md
- Use when:
	- Writing or updating Python docstrings
	- Standardizing docstring structure across modules/classes/functions
	- Clarifying parameter constraints, return behavior, and raised exceptions
	- Adding concise examples for non-obvious public APIs
	- Refreshing stale docstrings after API or behavior changes

### skill-writing

- Path: skills/skill-writing.md
- Use when:
	- Creating a new skill in skills/
	- Refactoring existing skills for clarity and concision
	- Reviewing skills to remove redundant instructions
	- Updating AGENTS.md routing for new or changed skills

### decision-writing

- Path: skills/decision-writing.md
- Use when:
	- Creating architecture or approach decision documents
	- Comparing alternative technical strategies and tradeoffs
	- Recommending a specific approach/technology
	- Linking decisions to implementation plans when execution should proceed

### function-naming

- Path: skills/function-naming.md
- Use when:
	- Naming or renaming public APIs
	- Choosing between query, transform, conversion, and constructor names
	- Defining relation-based cross-type names (for, at, on, from)
	- Picking canonical names and alias/deprecation strategy

### immutable-types

- Path: skills/immutable-types.md
- Use when:
	- Adding or refactoring immutable value objects
	- Defining __slots__ and deciding whether __dict__ is needed
	- Implementing copy-constructor APIs (with_*)
	- Applying immutable-specific copy-constructor naming constraints
	- Enforcing tuple-backed collection returns and immutable conventions

### commit-message-writing

- Path: skills/commit-message-writing.md
- Use when:
	- Generating commit messages from current workspace changes
	- Applying required commit-message templates (summary, blank line, detailed bullets)
	- Choosing conventional commit types and scopes from mixed file deltas
	- Summarizing behavior, API, test, and docs changes accurately

### Skill Selection Rule

- If a user asks to generate, rewrite, or refine a commit message, ALWAYS load commit-message-writing first.
- If a task is primarily about test coverage or test refactoring, load test-writing.
- If a task changes behavior, parsing, validation, or public contracts, load test-writing even if the user did not explicitly request tests.
- If a task is primarily about running tests, triaging failures, or checking coverage, load test-running.
- If a task is primarily about creating, updating, or restructuring execution plans, load plan-use.
- If a task is primarily about implementing an existing plan phase-by-phase, load plan-implementation.
- If a task is primarily about selecting or ranking the next plan in .plans, load next-work-selection.
- If a task changes public APIs, parsing/validation behavior, or user-facing workflows/examples, load readme-writing to update docs/README or record a no-docs-delta rationale.
- If a task is primarily about adding, updating, or standardizing docstrings, load docstring-writing.
- If a task is primarily about choosing between implementation approaches, load decision-writing.
- If a task is primarily about README/docs structure or documentation ownership boundaries, load readme-writing.
- If code changes alter public API behavior or contracts, load docstring-writing with test-writing and/or readme-writing as needed.
- If a task is primarily about creating or reviewing skill files, load skill-writing.
- If a task is primarily about naming strategy, load function-naming.
- If a task is primarily about immutable model design, load immutable-types.
- If a task is primarily about generating or refining commit messages, load commit-message-writing.
- If both apply, load both skills: function-naming for global naming and immutable-types for immutable-specific constraints.
- If plan work includes naming or immutable model constraints, load plan-use with the relevant companion skill(s).
- If plan work includes both authoring and execution in the same request, load plan-use first, then plan-implementation.
- If plan work starts with choosing what to do next, load next-work-selection before plan-use.
- If plan execution includes commit preparation, load plan-implementation with commit-message-writing.
- If plan work includes user-facing API or behavior changes, load plan-use with readme-writing.
- If plan work includes documentation restructuring, load plan-use with readme-writing.
- If plan work includes skill creation or skill refactoring, load plan-use with skill-writing.
- If plan work includes unresolved approach choices, load plan-use with decision-writing and create a decision doc in decisions/.
- If test work includes naming or immutable constraints, load test-writing with function-naming and/or immutable-types as needed.
- If test work includes both authoring and execution, load test-writing with test-running.

## Maintenance Rule

- Keep test authoring and coverage conventions in skills/test-writing.md.
- Keep test execution and coverage command conventions in skills/test-running.md.
- Keep plan authoring and re-scoping standards in skills/plan-use.md.
- Keep phase-by-phase implementation execution standards in skills/plan-implementation.md.
- Keep next-work prioritization and ranking standards in skills/next-work-selection.md.
- Keep README/docs structuring conventions in skills/readme-writing.md.
- Keep docstring conventions in skills/docstring-writing.md.
- Keep skill authoring/review conventions in skills/skill-writing.md.
- Keep decision-document conventions in skills/decision-writing.md.
- Keep global naming conventions in skills/function-naming.md.
- Keep immutable-specific modeling constraints in skills/immutable-types.md.
- Keep commit message formatting and decision rules in skills/commit-message-writing.md.
- Keep AGENTS.md focused on skill discovery and when to load each skill.
