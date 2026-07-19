# Contributing

## Setup

Requires Python 3.9+.

```sh
git clone <repo>
cd nextrec
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # or source .venv/bin/activate on Linux
pip install -e ".[dev]"
playwright install  # only needed for integration tests / live features
```

## Run tests

```sh
pytest -v
```

Unit tests mock Playwright, so they don't need a browser or live site access.

(No linter or type checker is configured yet.)

## Session capture

To re-capture network traces or refresh the login session:

```sh
nextrec debug-browse -o docs/discovery/oakland_endpoints.json
```

See `docs/discovery/run_capture.md` for the manual capture workflow.

## Project layout

- `src/nextrec/` — package source
  - `cli/` — Typer CLI commands and config loader
  - `tui/` — Textual TUI app
  - `scrapers/` — site-specific scrapers (PerfectMind)
  - `browser.py` — Playwright wrapper
  - `auth.py` — login automation
  - `search.py` — search orchestration
  - `cart.py` — add-to-cart automation
  - `models.py` — shared data types
- `tests/` — pytest test suite (unit, no browser required)
- `docs/discovery/` — network trace artifacts and capture instructions
- `plans/` — implementation plans and archived completed plans
- `decisions/` — architecture decision records
