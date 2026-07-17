---
name: immutable-types
description: 'Design and implement immutable core models in chordelia. Use when adding or refactoring value objects, copy-constructor APIs, tuple-backed collections, slots, cached derived properties, and immutable-specific naming constraints for copy constructors.'
argument-hint: 'Describe the type or API change and this skill will apply chordelia immutable patterns'
user-invocable: true
---

# Immutable Types

Use this skill when creating or refactoring core value objects so they follow the immutable design conventions used in chordelia.

Companion skill: function-naming for global API naming decisions (queries, transforms, conversions, and cross-type relation names).

## When To Use

- Adding a new core model (for example Degree)
- Refactoring a mutable model to immutable behavior
- Designing copy-constructor methods
- Returning stable collection types from core APIs
- Applying immutable-specific naming constraints for copy constructors

## Codebase Patterns To Preserve

### 1) Immutable shape and storage

- Prefer explicit classes, not dataclass-first design.
- Use private backing fields with properties for public access.
- Use __slots__ for immutable models.
- Include __dict__ in slots only when cached_property or dynamic cached values are required.

Examples in this codebase:
- Note uses slots without __dict__ because it does not rely on cached_property.
- Scale and Chord include __dict__ in slots because they cache derived values like notes.
- CustomScale defines its own slots for custom pattern storage.

### 2) Constructor boundary normalization

- Normalize and validate input in __init__.
- Convert flexible inputs to canonical internal forms.
- Store collection state as tuples, never lists.

Common normalization patterns:
- str -> domain object (for example Note.from_string)
- Union inputs -> enum/object coercion helpers (for example from_unknown)
- iterable -> tuple for immutable storage

### 3) Copy-constructor API

- Property replacement methods must return new instances and never mutate.
- Use with_<field>(...) for single-field replacement.
- Provide with_(...) for multi-field replacement when useful.
- Preserve unchanged fields exactly.

Examples:
- with_root, with_quality, with_extension, with_bass, with_inversion
- with_octave and with_ patterns in Note

### 4) Naming in immutable context

- Use with_<field>(...) and with_(...) for property replacement copy constructors.
- Do not use with_* for semantic operations.
- Load function-naming for general API naming decisions (queries, transforms, conversions, cross-type methods).

### 5) Derived data and caching

- Use cached_property for expensive deterministic derived values.
- Cached values must be computed from immutable state only.
- Keep derived collections immutable (tuple returns).

### 6) Equality, hashing, and representation

- Implement __eq__ and __hash__ from immutable identity fields.
- Implement __repr__ and __str__ to aid debugging and API clarity.
- Include tuple conversions in hashing when needed.

### 7) Error and return conventions

- Raise ValueError for invalid user input with clear accepted examples.
- Core collection-returning APIs should prefer tuples.
- Multi-input operations should fail atomically for invalid input (no partial results).

## Implementation Procedure

1. Define immutable fields and slots.
2. Normalize constructor inputs to canonical internal forms.
3. Expose read-only properties.
4. Add with_* copy-constructors for field replacement.
5. Apply function-naming conventions from function-naming for non-copy-constructor API names.
6. Return tuples for model collections.
7. Add __eq__, __hash__, __repr__, __str__.
8. Add tests for immutability, copy-constructor behavior, and semantic operations.

## Review Checklist

- No public method mutates instance state.
- All replacement methods return new instances.
- Replacement methods use with_* and semantic operations do not.
- Collection internals and outputs are tuples.
- Invalid inputs raise ValueError.
- Docs and tests use canonical names only.

## Related Skills

- Load function-naming for general naming conventions and decision flow.
