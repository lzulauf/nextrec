---
name: readme-writing
description: 'Create and maintain README and docs content with clear ownership boundaries: onboarding-first main README, deep guides in docs, strong cross-linking, and minimal duplication.'
argument-hint: 'Describe the documentation change and this skill will produce a concise README/docs split and navigation structure'
user-invocable: true
---

# README Writing

Use this skill when creating or restructuring project documentation, especially when splitting content between a top-level README and deeper docs pages.

Companion skills: plan-use for documentation migration planning and test-writing when documentation changes require test updates.

## When To Use

- Writing a new project README
- Refactoring an oversized README into docs pages
- Defining ownership boundaries between README and docs/
- Reducing duplicated examples across documentation files
- Updating navigation and cross-links after docs moves
- Updating documentation after public API, behavior, or user-workflow changes

## Change-Triggered Documentation Rules

- If a change affects public APIs, parsing/validation behavior, user-visible output, or documented examples, update README/docs in the same change.
- For API and behavior changes, prioritize updates to docs/api-overview.md and relevant guides before merging.
- Keep top-level README onboarding-focused; move details to docs/ and link from README rather than duplicating full content.
- If no documentation changes are needed, include a brief "No docs delta rationale" note in the task summary or plan update.

## Ownership Rules

### Main README Ownership

Keep the top-level README focused on onboarding:

1. Project identity and value proposition
2. High-level feature summary
3. Minimal installation path
4. One compact quickstart snippet
5. Docs navigation links
6. Contribution and license entry points

### Docs Ownership

Move detailed material into docs/:

1. Full installation matrices and environment notes
2. Deep tutorials and domain-specific guides
3. Immutability and design deep dives
4. API catalogs and reference summaries
5. Development, release, and publishing procedures

## Structure Rules

- Create docs/README.md as the docs index.
- Use short, purpose-specific pages rather than one large catch-all doc.
- Prefer stable, descriptive filenames (installation.md, quickstart.md, api-overview.md).
- Keep guides grouped under docs/guides/ when practical.

## Cross-Linking Rules

- Each docs page should link back to docs/README.md and the project README.
- The project README should link to all major docs entry points.
- Avoid orphan pages with no inbound links.
- Prefer relative links so docs work locally and in repository viewers.

## Anti-Duplication Rules

- Keep summary content in README and full details in docs pages.
- Do not maintain two full copies of the same walkthrough.
- If duplication is needed, keep README version short and link to the full guide.
- After refactors, remove stale copied sections rather than leaving parallel versions.

## Update Workflow

1. Inventory existing README sections.
2. Classify each section as keep, move, or summarize-plus-link.
3. Create or update destination docs pages.
4. Trim README to onboarding-first content.
5. Run a link and formatting pass.
6. Re-check docs for overlap and remove redundancy.

## Review Checklist

- README is concise and onboarding-first.
- Docs index exists and routes to major guides.
- Each deep section has one clear source-of-truth page.
- Links between README and docs are valid and discoverable.
- No orphan docs pages remain.
- No high-value content was dropped during restructuring.
- Public API/behavior changes are reflected in docs and README summaries where relevant.
- If no docs changed, a "No docs delta rationale" is explicitly documented.
