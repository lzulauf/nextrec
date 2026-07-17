---
name: commit-message-writing
description: 'Generate concise, accurate commit messages from the current change set using a clear subject line, blank-line separation, and structured explanatory bullets.'
argument-hint: 'Describe the desired commit style or constraints and this skill will produce a ready-to-use commit message.'
user-invocable: true
---

# Commit Message Writing

Use this skill to generate high-quality commit messages that reflect the actual staged or unstaged changes in the repository.

Companion skills: readme-writing when docs changes are a meaningful part of the commit scope.

## When To Use

- User asks to "generate a commit message"
- User asks for conventional commit formatting
- User asks for a custom message template (for example: short summary, blank line, then details)
- Changes span multiple files and need concise grouping
- You need a message that captures tests/docs/plan updates clearly

## Mandatory Trigger Rules

- Always load this skill when the user asks to generate, rewrite, or refine a commit message.
- If the user says "staged commit" or equivalent, inspect staged changes (`git diff --cached --name-status` and `git diff --cached --stat`) before drafting.
- If staged/unstaged scope is not specified, inspect `git status --short` and summarize the visible working-tree change set.

## Out Of Scope

- Creating commits automatically unless explicitly requested
- Rewriting repository history
- Inventing changes not present in the working tree

## Workflow

1. Inspect the actual change set first.
- Run `git status --short`.
- If needed, inspect diff summaries to identify the dominant scope.
- For staged-only requests, prefer cached diff commands over working-tree summaries.

2. Determine message shape from user constraints.
- If user specifies a template, follow it exactly.
- If no template is specified, default to:
  - one-line summary
  - blank line
  - longer summary
  - Short descriptions of key changes and important decisions to note (consider bullet point lists)
  - add any caveats

3. Build the summary line.
- Prefer imperative mood.
- Use a plain English sentence that starts with an imperative verb.
- Do not use conventional commit prefixes (`feat:`, `fix:`, `chore:`) or scoped tokens (`type(scope):`) unless the user explicitly requests conventional commit format.
- Do not include a trailing period.
- Capitalize the first character
- Fit in 72 characters

4. Build the detailed body.
- Group bullets by meaningful outcomes, not file-by-file noise.
- Include key behavior changes first.
- Include API contract changes and defaults explicitly.
- Include docs updates when present.
- Include test updates when they represent meaningful behavior or contract coverage changes.

5. Handle validation notes conservatively.
- Treat passing tests/lint/format checks as baseline expectations.
- Do not add generic validation bullets such as "tests pass" unless explicitly requested.
- Include validation details only when they add material context: failing-then-fixed scenarios, newly introduced critical coverage, required release gates, or when a user/repo template asks for them.

6. Add compatibility notes when needed.
- If behavior is breaking, mark it clearly.
- By default, keep the summary as a plain imperative sentence and include `BREAKING CHANGE:` details in the body.
- Use `!` in the summary only when the user explicitly requests conventional commit formatting.

## Output Rules

- Respect explicit user formatting constraints exactly.
- Keep the summary concise and descriptive.
- Separate summary and body with exactly one blank line when body exists.
- Use flat bullet lists (no nested bullets) unless user asks otherwise.
- Always wrap the final commit message in a fenced markdown code block unless the user explicitly requests plain text.
- If the user explicitly asks for plain text output, do not use code fences.

## Completion Checklist

- Message reflects current workspace changes accurately.
- Summary line is specific and action-oriented.
- Summary line is a plain imperative sentence (no conventional-commit prefix unless requested).
- Body includes important behavior/API/test/docs information.
- Body avoids baseline-only validation noise unless requested.
- User-requested structure is followed exactly.
- Final message is wrapped in a fenced code block unless plain text was explicitly requested.
- No fabricated changes or unsupported claims.

## Quick Examples

- `Add immutable metadata copy constructors to Score`
- `Add per-event gate overrides to midi schedule builder`
- `Add articulation override examples for playback`
