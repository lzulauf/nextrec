---
name: run-python-local
description: 'Instructions for running Python and project commands in this repository (pdm + pyenv-win details, and pip fallback).'
argument-hint: 'What do you want to run? e.g. "capture discovery", "run tests", "install deps"'
user-invocable: true
reusable: false
---

# Run Python / PDM in this repository

## Important: package source layout

This project uses `hatchling` with `source = "src"` in `pyproject.toml`, so the `nextrec` package lives under `src/`. To import `nextrec` (e.g. when running tests), you **must** set `PYTHONPATH` or install the package in editable mode.

## Decision tree — use this every time

```
Can you run "pdm" successfully on PATH?
  ├── YES → use pdm run python ... / pdm run pytest ...
  └── NO  → use .venv\Scripts\python.exe directly
             (always set $env:PYTHONPATH first)
```

## Required: resolve the nextrec package

Before running any command that imports `nextrec` (tests, scripts, CLI):

**Option A — set PYTHONPATH (quick, no install):**
```powershell
$env:PYTHONPATH = "src"
.\\.venv\\Scripts\\python.exe -m pytest tests/...
```

**Option B — editable install (one-time):**
```powershell
.\\.venv\\Scripts\\python.exe -m pip install -e .
```

## Setup

### With pdm (preferred)

```powershell
python -m pip install --user pdm
pdm install --dev
pdm run playwright install
```

### Without pdm (venv fallback)

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e .[dev]
playwright install
```

If `pyenv-win` is installed but `python` is not on PATH:
```powershell
$env:Path = "$env:USERPROFILE\\.pyenv\\pyenv-win\\bin;$env:USERPROFILE\\.pyenv\\pyenv-win\\shims;$env:Path"
```

## Running common tasks

| Task | Command (with pdm) | Command (without pdm / fallback) |
|---|---|---|
| Run all tests | `pdm run pytest tests/` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/` |
| Run auth tests | `pdm run pytest tests/unit/nextrec/test_auth.py -v` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/unit/nextrec/test_auth.py -v` |
| Run browser tests | `pdm run pytest tests/unit/nextrec/test_browser_manager.py -v` | Same pattern with `$env:PYTHONPATH` |
| Run with coverage | `pdm run pytest --cov=src` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest --cov=src` |
| Run specific test case | `pdm run pytest tests/...::TestClass::test_method` | Same pattern |
| Capture discovery | `pdm run python scripts/capture_oakland_discovery.py --headed` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/capture_oakland_discovery.py --headed` |
| Session capture CLI | `pdm run python -m nextrec.scripts.session_capture` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m nextrec.scripts.session_capture` |
| Import check | `pdm run python -c "import nextrec; print(nextrec.__file__)"` | `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -c "import nextrec; print(nextrec.__file__)"` |

## Troubleshooting

- **"ModuleNotFoundError: No module named 'nextrec'"** — always set `$env:PYTHONPATH = "src"` before running, or do `pip install -e .`
- **"pdm is not recognized"** — don't chase pdm. Use `.\.venv\Scripts\python.exe` directly (the venv already exists).
- **Playwright not found** — run `playwright install` after activating venv.
- **Test collection errors** — confirm `PYTHONPATH` includes `src/` (use absolute path if relative doesn't resolve).

See also: `local_skills/run-programs-local\SKILL.md` for Windows shell and browser detection.
