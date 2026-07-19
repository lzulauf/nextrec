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

Environment detection rules
- All Python commands use `.venv\Scripts\python.exe` at the repo root.
- The CLI is available at `.venv\Scripts\nextrec.exe`.
- Playwright browsers are installed under `.venv\Scripts\`.
- Find Chrome by checking well-known install paths first, then falling back to `Get-Command chrome`.

Chrome detection

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

Running Python and Playwright

```powershell
.\.venv\Scripts\python.exe -m pytest tests/
.\.venv\Scripts\python.exe -m playwright install
.\.venv\Scripts\nextrec.exe book --help
```
