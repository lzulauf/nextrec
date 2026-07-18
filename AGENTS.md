# AGENTS.md

Guidance for coding agents and contributors working in this repository.

## Skill Discovery

Skills live in two directories, registered in `opencode.json`:

- **`skills/`** — reusable conventions that apply across projects (e.g. testing patterns, commit messages, naming rules). Each has `reusable: true` in frontmatter.
- **`local_skills/`** — guidance specific to this repository (e.g. how to run Python with pdm, find Chrome on Windows). Each has `reusable: false` in frontmatter.

The agent discovers and selects skills automatically by reading frontmatter `name` and `description` fields.

## Maintenance

Place new skills in `skills/` if they describe general conventions; place them in `local_skills/` if they describe repo-specific tooling or workflows. Ensure every skill has proper frontmatter (`name`, `description`, `argument-hint`, `user-invocable`, `reusable`).
