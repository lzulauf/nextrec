# nextrec

CLI to locate and book facility reservations on PerfectMind-based municipal sites (Oakland Parks & Rec spike).

## Intended Flow

### 1. Generate a constraints config

```sh
nextrec generate-config -k "Mosswood Tennis Court # 1" -k "pb" --start-time 11:00 --end-time 17:00 -c my_config.yaml
```

Creates `my_config.yaml` with keywords, time window, etc. Use `-c my_config.json` for JSON.

### 2. Authenticate

```sh
nextrec auth
```

Opens a headed browser. Log in manually, then press Enter to save the session to `session_state.json`.

### 3. Search and book

```sh
nextrec book -c my_config.yaml --date 07/25
```

Override any constraint from the CLI (e.g. `--date`, `-k`). Add `--dry-run` to preview without booking.

### 4. Use the interactive TUI

```sh
nextrec tui -c my_config.yaml --start-date 7/25 --end-date 7/26
```

Opens a Textual-based terminal UI with a constraint form, facility timeline, and slot results list.

## Commands

| Command | Description |
|---|---|
| `book` | Search facilities and optionally book the first available slot |
| `auth` | Open headed browser for manual login and save session |
| `tui` | Interactive TUI for searching, filtering, selecting, and booking slots |
| `generate-config` | Generate a constraints config file for use with `book --config` |
| `debug-browse` | Open headed browser, interact freely, then analyze captured network traffic |

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

   Or set the `TEXTUAL` environment variable directly (no `textual run` needed):
   ```sh
   # PowerShell
   $env:TEXTUAL="devtools"; nextrec tui -c my_config.yaml --start-date 7/25 --end-date 7/26 --verbose
   ```

All `logger.debug()` output from the `nextrec` package will appear live in the terminal running `textual console`.
