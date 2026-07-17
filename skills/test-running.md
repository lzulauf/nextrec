---
name: test-running
description: 'Run tests in chordelia with focused pytest commands, slow-test controls, failure triage, and coverage reporting using pytest --cov=src.'
argument-hint: 'Describe what tests to run and this skill will choose fast, targeted pytest commands and coverage checks'
user-invocable: true
---

# Test Running

Use this skill when you need to execute tests, debug failures, or measure coverage.

Companion skills: test-writing for adding or refactoring tests and function-naming for canonical API naming during failure triage.

## When To Use

- Running the full suite before merge
- Running focused tests while developing a change
- Reproducing and debugging a failing test
- Checking coverage impact after code changes
- Running slow tests intentionally

## Core Commands

1. Run all tests
- pytest tests/

2. Run one test file
- pytest tests/unit/chordelia/test_scales.py

3. Run one test class
- pytest tests/unit/chordelia/test_scales.py::TestScaleModes

4. Run one test case
- pytest tests/unit/chordelia/test_scales.py::TestScaleModes::test_major_scale_modes

5. Run tests by keyword expression
- pytest -k "mode and not slow"

## Slow Test Controls

- Slow tests are marked with pytest.mark.slow.
- Slow tests are skipped by default.
- Include slow tests explicitly with:
  - pytest --runslow
- Run all tests including slow tests:
  - pytest tests/ --runslow

## Coverage Commands

1. Check coverage for source package
- pytest --cov=src

2. Run full suite with coverage
- pytest tests/ --cov=src

3. Add missing-line report for local debugging
- pytest tests/ --cov=src --cov-report=term-missing

4. Generate HTML coverage output
- pytest tests/ --cov=src --cov-report=html

## Failure Triage Workflow

1. Re-run only failing tests first.
2. Narrow scope to a single file or test case.
3. Use -k expressions to isolate related behavior.
4. Confirm fix with targeted run, then full run.
5. Run coverage check for touched modules.

## Practical Defaults

- Prefer focused runs during iteration for speed.
- Run pytest tests/ before finalizing changes.
- Use pytest --cov=src before merge when behavior changed.

## Review Checklist

- Correct test scope selected (file/class/case/full suite).
- Slow test behavior is intentional (default skip vs --runslow).
- Failing tests reproduced and re-verified after fix.
- Coverage checked with pytest --cov=src.
- Final run completed for confidence before merge.
