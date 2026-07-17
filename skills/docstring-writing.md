---
name: docstring-writing
description: 'Write and update Python docstrings with consistent style, accurate behavior contracts, argument/return/error details, and examples when they improve clarity.'
argument-hint: 'Describe the API or module and this skill will produce concise, accurate docstrings aligned with repository conventions'
user-invocable: true
---

# Docstring Writing

Use this skill to add or refine docstrings in chordelia so public behavior is clear, stable, and testable.

Companion skills: function-naming for API naming consistency, readme-writing when usage examples or contracts require docs updates, and test-writing when behavior clarifications reveal missing tests.

## When To Use

- Adding docstrings to new public modules, classes, or functions
- Tightening unclear or stale docstrings after behavior changes
- Standardizing mixed docstring formats within a file
- Documenting parameter constraints, return contracts, and exceptions
- Adding concise usage examples for non-obvious APIs

## Preferred Style

1. Format
- Use triple double quotes.
- Keep the summary line in imperative mood and end with a period.
- Prefer a short one-line summary; add detail paragraphs only when needed.

2. Scope
- Prioritize public APIs first.
- Add private helper docstrings only when behavior is non-obvious.

3. Content order
- Summary
- Optional detail paragraph (behavior, constraints, context)
- Args
- Returns
- Raises
- Examples (optional, only when it improves clarity)

4. Section format
- Use Google-style section headers: Args:, Returns:, Raises:, Examples:.
- Keep section entries concise and behavior-focused.
- Wrap lines for readability without awkward breaks.

## Authoring Rules

1. Describe behavior, not implementation
- Document observable outcomes, invariants, and edge-case contracts.
- Avoid internal algorithm details likely to churn.

2. Keep docstrings truthful
- Update docstrings in the same change when signatures or behavior change.
- Remove stale claims instead of preserving historical wording.

3. Be explicit about constraints
- Note accepted value domains, units, and defaults.
- Call out immutability and mutation behavior where relevant.

4. Document failures intentionally
- Include Raises entries only for exceptions that are part of the contract.
- Mention validation expectations when caller misuse is common.

5. Keep examples minimal and executable in spirit
- Use short examples that reflect real usage.
- Prefer deterministic examples; avoid timing, randomness, or hardware assumptions unless required.

6. Avoid redundancy
- Do not repeat obvious type info already clear from annotations unless it adds constraints.
- Keep module, class, and function docstrings complementary rather than duplicated.

## Review Checklist

- [ ] Public APIs in changed files have accurate docstrings.
- [ ] Summary line is concise and ends with a period.
- [ ] Args, Returns, and Raises sections are present when needed and accurate.
- [ ] Constraints, units, defaults, and mutation semantics are explicit when relevant.
- [ ] Behavior changes include docstring updates in the same change.
- [ ] Non-obvious APIs include a minimal, realistic example when helpful.
- [ ] No stale or contradictory wording remains.

## Related Files

- src/chordelia/*.py
- docs/api-overview.md
- README.md
