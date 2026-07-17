---
name: test-writing
description: 'Write and update tests in chordelia using repo conventions: pytest-first structure, parameterized cases, deterministic mocks for external systems, optional dependency handling, and checklist-driven coverage for behavior and edge cases.'
argument-hint: 'Describe the code change and this skill will produce tests that match current suite style'
user-invocable: true
---

# Test Writing

Use this skill to write or update tests that match chordelia conventions.

Companion skills: function-naming for canonical API naming, immutable-types for immutable behavior checks, and readme-writing for documentation updates tied to behavior/API changes.

## Core Conventions

1. Framework
- Pytest is the default test style across unit tests.

2. Organization
- Tests are grouped by module under tests/unit/chordelia.
- Class-based grouping with names like TestNoteCreation, TestScaleModes.
- Test functions use explicit test_* names and short docstrings.

3. Assertions and errors
- Prefer direct assert statements in pytest tests.
- Use pytest.raises for validation and error behavior.
- Use match=... for message checks when message contracts matter.

4. Runtime controls
- Slow tests are controlled through @pytest.mark.slow and --runslow (see conftest.py).

## When To Use

- Adding tests for new APIs or behavior changes
- Expanding edge-case and validation coverage
- Refactoring tests to canonical API names
- Writing deterministic tests around optional dependencies (audio/MIDI)
- Adding regression tests for bug fixes

## Authoring Rules

1. Keep tests deterministic
- No reliance on wall-clock timing, hardware, or external services.
- Patch time.sleep, device APIs, and external library calls when needed.

2. Keep tests focused
- One behavior per test where practical.
- Prefer multiple small tests over one broad integration test in unit suites.

3. Cover behavior and constraints
- Happy path behavior
- Invalid input behavior
- Boundary values
- Immutability/no-mutation behavior for immutable models

4. Prefer parameterization for case matrices
- Use @pytest.mark.parametrize for compact, readable case sets.
- Use pytest.param with an explicit id for non-obvious cases.
- Prefer clear ids over inline comments to explain case intent.

5. Mock external dependencies consistently
- Use unittest.mock (Mock, patch, MagicMock, call) for mocking and patching.
- Use pytest fixtures for reusable setup and mocks.
- Keep fixtures in the test file when only used there.
- Move fixtures to conftest.py when shared across test files.
- Use pytest.importorskip for optional modules when needed.

6. Prefer canonical API names
- Write new tests against canonical method names.
- Keep alias tests only when compatibility is intentional.

7. Match local style in existing files
- If a file uses unittest style for a specific area (for example heavy playback mocking), follow local style unless intentionally migrating.

8. Require test deltas for behavior/API changes
- If a change modifies behavior, parsing, validation, public APIs, or canonical model semantics, add or update tests in the same change.
- If no tests are added or updated, include a short "No test delta rationale" note in the task summary or plan update.
- Valid rationale examples: docs-only edits, comment-only edits, pure refactor with proven behavioral equivalence and no contract changes.

9. Coordinate docs deltas for user-visible changes
- If a test delta confirms user-visible behavior/API changes, ensure matching README/docs updates are included or document a "No docs delta rationale".
- Load readme-writing when behavior/API changes alter examples, contracts, or usage guidance.

10. Restore mutable global state in fixtures
- For fixtures that mutate process/global runtime state, always snapshot previous state first, reset to a clean test baseline, then restore previous state in a finally block after yield.
- Prefer one fixture per mutable state domain (for example context, random singleton, backend adapters) and compose them via fixture dependencies when a test needs multiple domains isolated.
- Prefer whole-object restoration over piecemeal field restoration to avoid brittleness when context objects gain new fields.
- For Chordelia runtime context specifically, restore with positional context calls (for example `set_chordelia_context(previous_context)`) instead of setting `scale` and `default_note_duration` separately.
- Apply the same pattern to other mutable singletons/config stores (for example randomization singleton, backend runtime config), restoring full prior objects where possible.

## Checklist for New Test Work

- [ ] Canonical API names used in new tests
- [ ] Happy path covered
- [ ] Validation/error paths covered with pytest.raises
- [ ] Edge/boundary cases covered
- [ ] Deterministic mocks for external dependencies
- [ ] Parameterization used for repetitive case matrices
- [ ] Non-obvious parameterized cases use pytest.param with clear ids
- [ ] Fixture scope is appropriate (local file vs conftest.py)
- [ ] Fixtures that mutate global state snapshot, reset, and restore previous state
- [ ] Fixtures are split by state domain and composed for tests that need multiple domains
- [ ] Context restoration uses whole-context/object restore (for example positional set_chordelia_context)
- [ ] Immutability checks included where relevant
- [ ] Slow markers used only when needed
- [ ] Behavior/API changes include test additions or updates in the same change
- [ ] If no tests changed, "No test delta rationale" is explicitly documented
- [ ] User-visible behavior/API changes include matching docs updates or a "No docs delta rationale"

## Running Tests

- Run focused unit files during development.
- Run the full unit suite before merging.
- Use --runslow only when intentionally validating slow tests.

## Related Files

- tests/unit/chordelia/*.py
- conftest.py
