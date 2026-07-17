---
name: function-naming
description: 'Define consistent function naming across chordelia APIs. Use when naming constructors, queries, transforms, conversions, and cross-type relation methods (for, at, on, from), and when deciding canonical names vs aliases.'
argument-hint: 'Describe the API behavior and this skill will propose canonical names and alternatives'
user-invocable: true
---

# Function Naming

Use this skill when adding or renaming APIs so names encode intent and stay consistent across modules.

Companion skill: immutable-types for immutable-model-specific constraints like copy constructors and tuple-backed immutable state.

## When To Use

- Designing new public methods
- Renaming legacy methods for consistency
- Choosing names for query vs transform behavior
- Naming cross-type methods that return a different model
- Deciding canonical names and alias/deprecation strategy

## Core Naming Categories

### 1) Construction and parsing

- Use from_* for external representations and parsing.
- Keep constructor-style names explicit and type-oriented.

Examples:
- from_string(...)
- from_midi_number(...)

### 2) Conversion and export

- Use to_* for representation conversion.
- Use as_* for structural export views.

Examples:
- to_roman(...)
- to_int(...)
- as_dict(...)

### 3) Queries and predicates

- Query names should read as lookups or predicates.
- Use is_*, has_*, contains_*, or relation queries like *_for_*.
- Avoid get_* unless it is truly a lightweight accessor.

Examples:
- contains_note(...)
- degree_for_tone(...)

### 4) Semantic transforms

- Use verb names for operations that apply behavior.
- For context-dependent transforms, include relation context.
- Avoid get_* prefixes for transforms.

Examples:
- transpose(...)
- normalize(...)
- mode_from_degree(...)

### 5) Cross-type relation methods

- For methods returning a different domain type, prefer relation-based names.
- Patterns: <target>_for_<context>, <target>_at(...), <target>_on(...), <target>_from(...).

Examples:
- chord_for_degree(...)
- chords_for_degrees(...)
- mode_from_degree(...)

## Canonical Name Policy

- Choose one canonical public name per behavior.
- Keep aliases only for compatibility and mark them as aliases in docs/tests.
- New docs/examples should use canonical names only.

## Decision Flow

1. If creating from an external representation, use from_*.
2. If converting or exporting representation, use to_* or as_*.
3. If querying state, use predicate/query naming (is_*, has_*, contains_*, *_for_*).
4. If applying behavior, use a semantic verb (not get_*).
5. If returning another domain type, use relation-based naming.

## Review Checklist

- Name matches behavior category (construct, convert, query, transform).
- Transform names do not use get_* prefixes.
- Cross-type APIs use relation-based names.
- Canonical name is clear; aliases are intentional and documented.
- Tests and docs use canonical names.

## Related Skills

- Load immutable-types for immutable-model-specific constraints (copy constructors, slots, tuple-backed state, and immutability semantics).
