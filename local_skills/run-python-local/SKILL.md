---
name: run-python-local
description: 'Instructions for running Python and project commands in this repository (.venv + pip based, no pdm or pyenv).'
argument-hint: 'What do you want to run? e.g. "run tests", "install deps", "run CLI"'
user-invocable: true
reusable: false
---

# Run Python in this repository

## Important: package source layout

This project uses `hatchling` with `source = "src"` in `pyproject.toml`, so the `nextrec` package lives under `src/`. The package is installed in editable mode via `pip install -e .` into the `.venv`.

## Setup

The `.venv` already exists at the repo root. All Python commands use it directly:

```powershell
.\.venv\Scripts\python.exe             # Python interpreter
.\.venv\Scripts\nextrec.exe            # Installed CLI entry point
```

No `pdm`, `pyenv-win`, or `PYTHONPATH` manipulation needed — the editable install handles resolution.

## Running common tasks

| Task | Command |
|---|---|
| Run all tests | `.\.venv\Scripts\python.exe -m pytest tests/` |
| Run auth tests | `.\.venv\Scripts\python.exe -m pytest tests/unit/nextrec/test_auth.py -v` |
| Run browser tests | `.\.venv\Scripts\python.exe -m pytest tests/unit/nextrec/test_browser_manager.py -v` |
| Run with coverage | `.\.venv\Scripts\python.exe -m pytest --cov=src` |
| Run specific test | `.\.venv\Scripts\python.exe -m pytest tests/...::TestClass::test_method` |
| Reinstall package | `.\.venv\Scripts\python.exe -m pip install -e .` |
| Reinstall with dev deps | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` |
| Run CLI | `.\.venv\Scripts\nextrec.exe book --help` |
| Import check | `.\.venv\Scripts\python.exe -c "import nextrec; print(nextrec.__file__)"` |

## Notes

- The entry point `nextrec.exe` is at `.venv\Scripts\nextrec.exe`. It resolves from the repo root when invoked as `.\.venv\Scripts\nextrec.exe`.
- Playwright browsers must be installed once: `.\.venv\Scripts\python.exe -m playwright install`
