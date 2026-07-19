# nextrec

CLI to locate and book facility reservations on PerfectMind-based municipal sites (Oakland Parks & Rec spike).

## Installation

```sh
git clone <repo>
cd nextrec
python -m venv .venv
.venv\Scripts\Activate.ps1   # or source .venv/bin/activate on Linux
pip install -e ".[dev]"
playwright install  # only needed for integration tests / live features
```

(Not yet published to PyPI — install from source as above.)

### Developer setup

Same as installation above.

## Quick Start

### 1. Authenticate

```sh
nextrec auth
```

Opens a headed browser. Log in to the site manually, then press Enter in the terminal to save the session to `session_state.json`.

### 2. Generate a constraints config

```sh
nextrec generate-config -k "Mosswood Tennis Court # 1" -k "pb" --start-time 11:00 --end-time 17:00 -c my_config.yaml
```

Creates `my_config.yaml` with keywords, time window, etc. Use `-c my_config.json` for JSON.

### 3. Search and book

```sh
nextrec book -c my_config.yaml --date 07/25
```

Override any constraint from the CLI (e.g. `--date`, `-k`). Add `--dry-run` to preview without booking.

### 4. Use the interactive TUI

```sh
nextrec tui -c my_config.yaml --start-date 7/25 --end-date 7/26
```

Opens a Textual-based terminal UI with a constraint form, facility timeline, and slot results list. Select multiple slots with Space and press F2 or Book to open checkout tabs.

## Config file format

The config file (JSON or YAML) accepts these fields:

| Field | Type | Description |
|-------|------|-------------|
| `keywords` | `string` or `list[string]` | Search keyword(s), one per query. Repeatable via `-k` |
| `start_date` | `string` | Start date for slot search (YYYY-MM-DD) |
| `end_date` | `string` | End date, inclusive |
| `date` | `string` | Single date (sets both start and end) |
| `start_time` | `string` | Earliest slot time (HH:MM) |
| `end_time` | `string` | Latest slot time (HH:MM) |
| `duration` | `int` | Slot duration in minutes (default: 60) |
| `days` | `int` | Number of days to look ahead (default: 7) |
| `number_of_attendees` | `int` | Attendee count (default: 1) |

Example (`pickleball.yml`):

```yaml
duration: 60
end_time: '17:00'
keywords:
  - 'mosswood tennis court # 1'
  - pb
number_of_attendees: 4
start_time: '11:00'
```

CLI flags always override file values.

## Commands

| Command | Description |
|---------|-------------|
| `book` | Search facilities and optionally book the first available slot |
| `auth` | Open headed browser for manual login and save session |
| `tui` | Interactive TUI for searching, filtering, selecting, and booking slots |
| `generate-config` | Generate a constraints config file for use with `book --config` |
| `debug-browse` | Open headed browser, interact freely, then analyze captured network traffic |

Use `nextrec <command> --help` for full option details.

## Debugging the TUI

The TUI uses Textual's devtools for persistent logging. To capture debug output:

1. **Terminal 1** — start the devtools console:
   ```sh
   textual console
   ```

2. **Terminal 2** — run the TUI with dev mode enabled:
   ```sh
   textual run -c "nextrec tui -c my_config.yaml --start-date 7/25 --end-date 7/26" --dev
   ```

   Or set the `TEXTUAL` environment variable directly:
   ```sh
   # PowerShell
   $env:TEXTUAL="devtools"; nextrec tui -c my_config.yaml --start-date 7/25 --end-date 7/26 --verbose
   ```

All `logger.debug()` output from the `nextrec` package appears live in the terminal running `textual console`.
