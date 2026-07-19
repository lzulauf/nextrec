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

## Commands

| Command | Description |
|---|---|
| `book` | Search facilities and optionally book the first available slot |
| `auth` | Open headed browser for manual login and save session |
| `generate-config` | Generate a constraints config file for use with `book --config` |
| `debug-browse` | Open headed browser, interact freely, then analyze captured network traffic |
