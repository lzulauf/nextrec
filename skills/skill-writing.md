---
name: skill-writing
description: 'Create, update, and review repository skills with consistent structure, clear scope, concise guidance, and no redundant instructions.'
argument-hint: 'Describe the skill purpose and this skill will produce a clean, non-redundant skill file plus AGENTS wiring'
user-invocable: true
---

# Skill Writing

Use this skill when creating or maintaining files in skills/ and when wiring those skills into AGENTS.md.

Companion skills: plan-use for planning complex migrations and readme-writing when documentation ownership rules are part of the skill.

## When To Use

- Creating a new repository skill
- Refactoring an existing skill for clarity
- Merging overlapping skill guidance
- Adding or updating AGENTS skill routing rules
- Reviewing skills for quality and maintainability

## Out Of Scope

- Runtime debugging or feature implementation work unrelated to skill files
- Non-documentation refactors outside skills/ and AGENTS.md
- Replacing domain-specific rules owned by another dedicated skill

## Required Skill Structure

Each skill should include:

1. YAML frontmatter
   1. name
   2. description
   3. argument-hint
   4. user-invocable
2. One-sentence purpose statement near the top
3. When To Use section with concrete triggers
4. Rules or conventions section with actionable guidance
5. Review checklist for validating output quality

## Writing Rules

- Keep language direct and operational.
- Prefer short bullets over long paragraphs.
- Keep one idea per bullet.
- Use concrete examples only where they improve understanding.
- Keep scope boundaries explicit with clear in-scope and out-of-scope guidance.

## Redundancy Control Rules

- Maintain one source of truth per concept inside a skill.
- If two sections overlap, keep the clearer section and remove the duplicate.
- Do not duplicate companion skill guidance; link to the companion skill instead.
- Consolidate synonymous rules into one canonical wording.

## AGENTS Integration Rules

- Add the new skill under Available Skills with path and use cases.
- Update Skill Selection Rule when routing should include the new skill.
- Update Maintenance Rule to keep ownership clear.
- Keep AGENTS.md as a discovery index, not a full duplicate of skill contents.

## Review Procedure

1. Read the full skill top to bottom for flow and consistency.
2. Mark any vague, repetitive, or conflicting guidance.
3. Rewrite for precision and brevity.
4. Remove duplicate rules and consolidate overlap.
5. Verify AGENTS.md references are present and accurate.
6. Re-check that the skill remains actionable after trimming.

## Clarity and Concision Checklist

- Skill scope is explicit and easy to identify.
- Out-of-scope boundaries are explicit.
- Sections are ordered logically and easy to scan.
- Guidance is concise and avoids filler language.
- No materially redundant instructions remain.
- Companion skills are referenced instead of duplicated.
- AGENTS wiring is complete and accurate.
