---
name: decision-writing
description: 'Create structured decision documents in decisions/*.md with clear problem framing, alternatives (including do nothing and out-of-the-box options), tradeoffs, recommendations, and implementation follow-through.'
argument-hint: 'Describe the decision to make and this skill will produce a decision doc with options, tradeoffs, and recommendation'
user-invocable: true
---

# Decision Writing

Use this skill to create and review decision documents for architecture, tooling, and implementation approach choices.

Companion skills: plan-use for implementation planning and skill-writing when refining decision-document authoring conventions.

## When To Use

- Choosing between technical approaches or technologies
- Comparing multiple solution strategies with tradeoffs
- Recording rationale for significant engineering decisions
- Resolving uncertainty before creating an execution plan
- Updating a prior decision after new constraints emerge

## Location and Naming Rules

- All decision documents must be Markdown files in decisions/.
- Do not create decision docs outside decisions/.
- Use concise snake_case names ending in _decision.md when possible.
- Keep one primary decision per file.

Examples:

- decisions/midi_export_backend_decision.md
- decisions/sheet_music_renderer_decision.md

## Required Decision Sections

Include these sections in order unless there is a strong reason not to:

1. Decision title
2. Problem statement
3. Why this matters now
4. Goals and decision criteria
5. Constraints and assumptions
6. Options considered
7. Tradeoff analysis
8. Recommendation
9. Confidence and risks
10. Follow-up actions

## Goals And Criteria Rules

- Include a dedicated section named "Goals and decision criteria" before options are evaluated.
- Split this section into two short lists:
  - Goals: what the decision should achieve in plain language.
  - Decision criteria: how options will be judged.
- Keep criteria explicit and measurable where practical (for example: implementation effort, dependency risk, reversibility, runtime performance, portability, delivery speed).
- Ensure tradeoff scoring/matrices use criteria defined in this section, or explain why a criterion was added/removed later.
- If criteria are weighted, show weights in this section before the tradeoff table.
- Require each option section to include an explicit "Criteria impact" block that addresses every listed decision criterion.
- Allow compact labels (for example high/medium/low or +/0/-), but include a one-line rationale per criterion.

## Option Design Rules

- Present several alternative approaches, not variants of one idea only.
- Always include "Do nothing" as an explicit option.
- Include at least one out-of-the-box option that reframes the problem.
- Keep options mutually understandable with clear pros/cons.
- For layered decisions (for example strategy then product), include sub-sections:
  - Primary approach category
  - Via options (specific technologies/products)

## Option Expansion Rules

- For each option, include a short "What this means" description in plain language.
- For each option, include implementation shape details:
  - API or interface sketch (signatures or data contracts)
  - Execution/data flow summary
  - Dependency/runtime expectations
- Include at least one concrete example per option when practical (code, config, or pseudo-flow).
- Explain why listed pros/cons follow from the option mechanics, not just outcomes.
- Avoid one-line options; each option should be detailed enough that a reviewer can imagine implementation boundaries.
- Include a compact per-option mapping from option behavior to goals and decision criteria.

## Communication Aids Rules

- For medium/high-impact decisions, include at least one visual aid:
  - Mermaid diagram for architecture/flow, or
  - ASCII diagram when Mermaid is not suitable.
- For API/model decisions, include a small sample code sketch to demonstrate intended usage.
- Keep visuals scoped to decision points; avoid decorative diagrams.
- If scoring is used, include a compact comparison table with criteria and brief rationale.

## Tradeoff Rules

- Compare options using explicit criteria (for example complexity, cost, performance, maintainability, portability, delivery speed).
- Call out short-term vs long-term consequences.
- Separate facts, assumptions, and unknowns.
- Identify which risks are acceptable and which are blockers.
- Ensure each criterion references concrete option behavior (for example dependency model, migration cost, runtime path).
- Reuse the criteria declared in "Goals and decision criteria" as the source of truth.

## Analysis Depth Rules

Use a standard comparison for routine decisions and require deeper analysis for high-impact decisions.

### Standard analysis is enough when

- Decision affects one module or one optional integration path.
- Reversal cost is low (typically less than one short iteration).
- No new mandatory runtime/binary dependency is introduced.
- Security, licensing, and operational impact are minimal.

### Deeper analysis is required when

- Decision is hard to reverse or creates long-term lock-in.
- Decision introduces mandatory third-party dependencies, external binaries, or cross-language bridges.
- Decision affects public API shape, data model contracts, or multiple plans.
- Decision has meaningful security, licensing, compliance, or platform support impact.
- Estimated delivery effort or operating cost differs materially between options.

### When deeper analysis is required, include

- A weighted criteria matrix with explicit scoring and rationale.
- One small feasibility spike/prototype for the top candidate(s) when practical.
- Dependency and operations notes: packaging, CI/CD, runtime footprint, and portability.
- A migration or rollback path if the recommendation underperforms.
- Option-level examples (code/config/flow) and at least one architecture or data-flow diagram.

## Recommendation Rules

- Recommend a specific approach and, when applicable, specific technology choices.
- Explain why alternatives were not chosen.
- State confidence level (high/medium/low) and key uncertainties.
- If conviction is strong enough and scope is implementation-ready, create a plan in .plans/ and link it.

## Plan Coupling Rules

- When creating a plan that depends on unresolved approach decisions, create a decision document first (or in the same workstream).
- Link plans to their decision docs and decision docs to implementation plans.
- Avoid starting execution phases that depend on undecided options.

## Review Checklist

- Document is in decisions/ and uses .md format.
- Problem statement and urgency are explicit.
- Goals and decision criteria section exists and is concrete.
- Options include both do-nothing and out-of-the-box alternatives.
- Options are detailed enough to understand implementation shape and dependency impact.
- Every option includes explicit criteria impact coverage for all declared criteria.
- Tradeoffs are criteria-based and non-redundant.
- Pros/cons are justified by concrete option mechanics.
- At least one diagram and one usage sketch are included for medium/high-impact decisions.
- Recommendation is clear, justified, and actionable.
- Plan linkage exists when implementation should proceed.
