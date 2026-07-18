---
name: run-python-local
description: 'Instructions for running Python and project commands in this repository (pdm + pyenv-win details, and pip fallback).'
argument-hint: 'What do you want to run? e.g. "capture discovery", "run tests", "install deps"'
user-invocable: true
reusable: false
---

# Run Python / PDM in this repository

Purpose
- Provide a single place in-repo describing how to run Python, create the project environment, and run common developer commands on Windows (and Unix-like shells).

Environment detection rules
- Prefer `pdm` if available in the user's PATH. Use `python -m pdm` when `pdm` is not on PATH but Python is available.
- If `pyenv-win` is installed, ensure its `bin` and `shims` paths are added to the session `PATH` before running `python` or `pdm`.
- Fallback: use a virtual environment created with `python -m venv .venv` and `pip install -r requirements.txt`.

Setup (recommended: pdm)

- Install `pdm` for your user (Windows):

```powershell
python -m pip install --user pdm
```

- Install project deps and dev deps with `pdm` (creates a venv and a `pdm.lock`):

```powershell
pdm install --dev
```

- Install Playwright browsers (required for capture & tests):

```powershell
pdm run playwright install
```

If `python` is not found but `pyenv-win` is installed
- Add `pyenv-win` to the session PATH before running the commands (PowerShell example):

```powershell
$env:Path = "$env:USERPROFILE\.pyenv\pyenv-win\bin;$env:USERPROFILE\.pyenv\pyenv-win\shims;$env:Path"
# then run the pdm commands above
```

Running common tasks
- Capture Oakland discovery (uses Playwright):

```powershell
pdm run python scripts/capture_oakland_discovery.py --url "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List" --out docs/discovery --headed
```

- Run the CLI (when implemented):

```powershell
pdm run nextrec --help
```

Fallback (pip / venv)
- Create venv and install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
playwright install
```

See also: `local_skills/run_programs.md` for Windows shell program detection and runtime guidance when `pwsh`, `powershell`, Chrome, or Python are missing.

Notes
- Prefer `pdm` for reproducible installs (`pdm.lock`) and editable installs during development.
- Use `pdm run` to ensure commands run inside the project's venv consistently across machines and CI.
- If a CI runner or contributor cannot use `pdm`, provide a generated `requirements.txt` via `pdm export -o requirements.txt --dev`.
