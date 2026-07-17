Decision title: TUI Framework Selection

Problem statement
-----------------
Choose a terminal UI framework for the `nextrec` CLI/TUI that balances development speed, UX flexibility, and testability. Candidates: `Typer` (simple CLI), `Textual` (rich TUI), `Rich` components for nicer output.

Why this matters now
--------------------
The TUI choice affects how users provide credentials, view results, and perform manual login capture. It also impacts testability and how quickly we can deliver a usable CLI.

Goals and decision criteria
--------------------------
Goals
- Fast developer iteration and low complexity for initial MVP.
- Good UX for credentials capture and presenting search results.
- Testability in automated CI and unit tests.

Decision criteria
- Implementation effort (lower is better)
- User interaction richness (higher is better)
- Automation/test friendliness
- Cross-platform support

Constraints and assumptions
- Primary users will run this on macOS, Linux, and Windows terminals.
- The MVP should be scriptable and support a `--headed` mode to open the browser.

Options considered
------------------

1) Typer (click-based CLI) + Rich for output
2) Textual (full TUI app built on Rich)
3) Plain argparse with minimal output

Tradeoff analysis
-----------------

Option 1 — Typer + Rich
- What this means: Build a CLI with Typer for commands and use Rich to render tables, progress, and prompts. Use `prompt_toolkit` for password input or rely on `getpass`.
- Pros: Fast to implement, familiar patterns, easy to script, testable. Rich integrates well with printing structured results. Minimal runtime footprint.
- Cons: Not a full-screen interactive TUI; less immersive than Textual for complex flows.
- Criteria impact: Implementation effort=Low, UX richness=Medium, Automation=High, Cross-platform=High.

Option 2 — Textual
- What this means: Build a full-screen TUI with interactive panes, selection lists, and embedded browser-like views in terminal.
- Pros: Best UX for selection and review; visually rich and interactive; supports complex flows like multi-step booking wizards.
- Cons: Higher implementation cost, steeper learning curve, harder to automate in CI, less scriptable for non-interactive automation.
- Criteria impact: Implementation effort=High, UX richness=High, Automation=Medium, Cross-platform=High.

Option 3 — Plain argparse
- What this means: Minimal CLI surface, plain text output, simple `--json` for machine consumption.
- Pros: Very low effort, highly scriptable.
- Cons: Poor interactive UX for credential entry and manual login capture guidance.
- Criteria impact: Implementation effort=Very Low, UX richness=Low, Automation=High, Cross-platform=High.

Recommendation
--------------
Choose Option 1: `Typer` for command scaffolding plus `Rich` for output. This gives a fast MVP path, scriptability, and good UX for listing/filtering and prompts. Reserve `Textual` for a later major release if users request a richer interactive experience.

Confidence and risks
--------------------
- Confidence: High for MVP suitability.
- Risk: If users demand a full-screen interactive experience, we may need to migrate to `Textual`, which will require a separate plan and UI rewrite.

Follow-up actions
-----------------
- Create `.plans/tui_textual_migration_plan.md` if/when migration to `Textual` is approved.
- Start CLI scaffolding with Typer and add `Rich` dependency.
