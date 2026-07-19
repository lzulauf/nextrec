---
name: run-python-local
description: 'Instructions for running Python and project commands in this repository (.venv + pip).'
argument-hint: 'What do you want to run? e.g. "run tests", "install deps", "run CLI"'
user-invocable: true
reusable: false
---

# Run Python in this repository

## Venv

Create the venv once using your system Python, then always run from it:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Running common tasks

All Python commands use the venv interpreter directly:

| Task | Command |
|---|---|
| Run all tests | `.\.venv\Scripts\python.exe -m pytest tests/` |
| Run specific test | `.\.venv\Scripts\python.exe -m pytest tests/unit/nextrec/test_auth.py -v` |
| Run with coverage | `.\.venv\Scripts\python.exe -m pytest --cov=src` |
| Reinstall package | `.\.venv\Scripts\python.exe -m pip install -e .` |
| Reinstall with dev deps | `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` |
| Run CLI | `.\.venv\Scripts\nextrec.exe book --help` |
| Playwright browser install | `.\.venv\Scripts\python.exe -m playwright install` |

## Important: package source layout

This project uses `hatchling` with `source = "src"` in `pyproject.toml`, so the `nextrec` package lives under `src/`. The package is installed in editable mode via `pip install -e .`, so imports resolve correctly from the venv without `PYTHONPATH` manipulation.
