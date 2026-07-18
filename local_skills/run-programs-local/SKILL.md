---
name: run-programs-local
description: 'Instructions for running common programs used in this repository on Windows, including PowerShell, Chrome, Python, Playwright, and shell detection rules.'
argument-hint: 'What program do you need to run? e.g. python, powershell, chrome, playwright'
user-invocable: true
reusable: false
---

# Run Common Programs in this repository

Purpose
- Document how to run common tools in this repository using the local Windows shell, with fallback behavior when programs are not on PATH.
- Capture local learnings from repository discovery work such as using PowerShell when `pwsh` is unavailable and finding Chrome executables in standard install locations.

Environment detection rules
- Prefer `pdm` for Python-based project commands because this repo uses `pdm.lock`.
- If `pdm` is not on PATH but Python is available, run `python -m pdm`.
- On Windows, prefer `pwsh` when available; if not, use the built-in `powershell` executable.
- Find Chrome by checking well-known install paths first, then falling back to `Get-Command chrome`.
- When `python` is not available but `pyenv-win` is installed, add `pyenv-win\bin` and `pyenv-win\shims` to the session PATH.

PowerShell command examples
- Preferred when `pwsh` is absent:

```powershell
powershell -NoLogo -NoProfile -Command "Get-Content 'docs/discovery/oakland_capture.har' -Raw | ConvertFrom-Json | Select-Object -ExpandProperty log | Select-Object -ExpandProperty entries | Where-Object { $_.request.url -like '*GetFacilities*' } | Select-Object -First 3 | ForEach-Object { \"$($_.request.method) $($_.request.url)\"; $_.request.postData.text; \"---\" }"
```

- Use `-NoLogo -NoProfile` to avoid profile side effects when running one-shot commands.
- Quote carefully in PowerShell, especially when embedding strings with `"` or pipe operators.

Chrome detection
- Use a session PATH update or explicit path lookup to run Chrome for Playwright captures.

```powershell
$candidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
  "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) {
  $cmd = Get-Command chrome -ErrorAction SilentlyContinue
  if ($cmd) { $chrome = $cmd.Source }
}
if (-not $chrome) { Throw 'Chrome not found on the system' }
Write-Host "Using Chrome at: $chrome"
```

- Pass the discovered Chrome path to scripts that need a browser binary.

Running Python and Playwright
- Preferred project command:

```powershell
pdm run python scripts/capture_oakland_discovery.py --url "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List" --out docs/discovery --headed --wait 12 --chrome-path "$chrome"
```

- Install Playwright browsers from the project environment:

```powershell
pdm run playwright install
```

When `python` is missing but `pyenv-win` exists
- Update PATH in the current PowerShell session:

```powershell
$env:Path = "$env:USERPROFILE\.pyenv\pyenv-win\bin;$env:USERPROFILE\.pyenv\pyenv-win\shims;$env:Path"
# then run pdm or python commands
```

Fallback if `pdm` is unavailable
- Create and activate a venv, then install dependencies manually:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pdm run playwright install
```

Notes
- Prefer `pdm run` to ensure commands execute inside the repository virtual environment.
- Use `powershell` when `pwsh` is not present and `pwsh`-style quoting is not required.
- If a tool is not found on PATH, search for the executable in standard installation locations before installing anything new.
