---
name: next-work-selection
description: 'Prioritize the next work item from .plans using status, dependency order, and checklist progress, then recommend a concrete immediate action.'
argument-hint: 'Describe planning horizon and constraints to get a ranked next-work recommendation'
user-invocable: true
---

# Next Work Selection

Use this skill to choose the best next implementation target from .plans.

Companion skills: plan-use for plan authoring/re-scoping, plan-implementation for in-flight status/checklist updates, and decision-writing when dependency order is blocked by unresolved approach choices.

## When To Use

- User asks "what's next" or "what should we do next"
- User asks to prioritize or rank plans in .plans
- User asks for execution order across multiple active plans
- User asks which plan to start first after recent completions

## Out Of Scope

- Implementing features directly without user confirmation
- Writing full plan contents from scratch (use plan-use)
- Making architecture decisions that require a decision doc (use decision-writing)

## Required Workflow

1. Gather active plan state
- Inspect all root .plans/*.md files.
- Read each plan's Status section.
- Count open and completed checklist items.

2. Apply prioritization gates
- Exclude plans already marked Done/Complete.
- Prefer Implementing plans over Approved plans over Drafting plans.
- Prefer plans with low remaining checklist count when closeout is cheap.
- Prefer plans explicitly marked "Why this comes first" when present.
- Respect dependency order from cross-plan references and execution-order sections.

3. Identify blocking and hygiene work
- Flag completed plans that still live in root .plans and recommend archiving.
- Flag status drift where a plan is Drafting but substantial implementation already landed.
- Flag unresolved dependency gates before recommending downstream work.

4. Produce a ranked recommendation
- Return a numbered list of next candidates with short rationale.
- Include one concrete immediate next action for the top candidate.
- Call out optional alternatives when multiple paths are valid.

## Prioritization Rules

- Rule 1: Finish nearly complete active work before starting broad new initiatives.
- Rule 2: Prioritize by lifecycle readiness: Implementing > Approved > Drafting.
- Rule 3: Resolve foundation plans that reduce cross-module inconsistency before feature expansion.
- Rule 4: Prefer plans that unblock multiple downstream plans.
- Rule 5: Defer large speculative plans when smaller high-leverage plans are available.
- Rule 6: Keep plan lifecycle clean (Done plans archived, active plans in root).

## Output Format

- Top recommendation first with one-sentence reason.
- Follow with 2-5 ranked options.
- For any Drafting option listed, include 1-3 concise suggestions to improve draft readiness.
- End with a proposed "start now" action that can be executed immediately.

## Review Checklist

- Root .plans status was inspected before ranking.
- Dependency and execution-order notes were considered.
- Recommendation includes rationale, not just file ordering.
- Completed-plan archiving hygiene is addressed when needed.
- Output includes one concrete immediate next step.
