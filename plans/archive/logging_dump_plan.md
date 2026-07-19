# Plan: Log Dump on TUI Exit

## Status

Done

## Goal

When the TUI exits, dump all buffered log output to stderr so users can review what happened during their session without running with `--verbose` (which pollutes stderr in real time).

## Scope

- Add an in-memory buffering `logging.Handler` that captures all `nextrec.*` log records
- Install it automatically in `tui/app.py` at import time alongside the existing `TextualHandler`
- After `app.run()` returns in `cli/main.py`, dump the buffered logs to stderr
- The dump should use the same format as the existing TextualHandler: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- CLI commands (`book`, `auth`, etc.) are out of scope — they already log directly to stderr via `--verbose`

## Out of Scope

- Persistent log files or log rotation
- Log levels or filtering in the dump handler (it captures all levels)
- Real-time log viewing during TUI operation
- Truncating/trimming the buffer (full session is kept in memory)
- `--log-file` CLI flag (can be added later)
- Unit tests for the handler itself

## Technical Design Details

### New class: `DumpOnExitHandler`

A simple `logging.Handler` subclass that stores `LogRecord` objects in a list. On dump, it formats them and writes to a stream.

```python
class DumpOnExitHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def dump(self, stream: TextIO = sys.stderr) -> None:
        fmt = self.formatter or logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        for record in self.records:
            stream.write(fmt.format(record) + "\n")
```

### Changes to `src/nextrec/tui/app.py`

At module level, alongside the existing `_textual_handler`:

```python
_dump_handler = DumpOnExitHandler()
_dump_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
logging.getLogger("nextrec").addHandler(_dump_handler)
```

Add a module-level function:

```python
def dump_logs() -> None:
    """Write all buffered log records to stderr."""
    _dump_handler.dump()
```

### Changes to `src/nextrec/cli/main.py`

After `app.run()` (line 434):

```python
    from nextrec.tui.app import NextRecApp, dump_logs
    app = NextRecApp(chrome_exe=chrome_exe, auth_path=auth_path, initial_constraints=initial)
    app.run()
    dump_logs()
```

### Mermaid diagram

```mermaid
flowchart LR
    subgraph "During TUI (app.run)"
        L["nextrec.* loggers"] --> TH["TextualHandler<br/>(→ TUI RichLog)"]
        L --> DH["DumpOnExitHandler<br/>(→ memory buffer)"]
    end
    subgraph "After app.run()"
        DH -->|dump_logs()| STDERR["sys.stderr"]
    end
```

### Edge cases

- If no logs were generated during the session, `dump()` prints nothing (empty stderr is fine)
- If `app.run()` raises, the `dump_logs()` call would be skipped. We could use `try/finally`:
  ```python
  try:
      app.run()
  finally:
      dump_logs()
  ```
  This ensures logs are dumped even on crash.

## Testing Approach

No automated test changes required for this feature. The handler is a simple data structure with no external dependencies. If desired, a quick smoke test can be run manually:

- `nextrec tui -v` (with verbose to see live stderr + dump on exit)
- `nextrec tui` (no verbose, dump only on exit)

**Test delta**: none (manual verification only).

Rationale: The handler is a trivial logging.Handler subclass with no I/O, failure modes, or complex logic. The integration point is two lines in cli/main.py.

## Documentation Approach

**Docs delta**: none.

Rationale: This is an invisible quality-of-life improvement. Users don't need to configure or opt into it.

## Progress Checklist

- [x] Phase 1: `DumpOnExitHandler` class written and installed in `tui/app.py`
- [x] Phase 2: `dump_logs()` called after `app.run()` in `cli/main.py` (with `finally`)
- [x] Tests pass (130/130, zero warnings)

## Phases

### Phase 1: Buffered handler

**Files**: `src/nextrec/tui/app.py`

- Add `DumpOnExitHandler` class before the existing module-level logging setup
- Create module-level `_dump_handler` instance and add it to `logging.getLogger("nextrec")`
- Expose `dump_logs()` function

### Phase 2: Wire up dump on exit

**Files**: `src/nextrec/cli/main.py`

- Update the import line to import `dump_logs` alongside `NextRecApp`
- Wrap `app.run()` in `try/finally` and call `dump_logs()` in the `finally` block

### Phase 3: Verify

- Run `pytest tests/ -v --tb=short -W error::RuntimeWarning` — 128 passed, zero warnings
- Manual: verify `nextrec tui` produces log output on stderr after quitting

## Execution Order

Phase 1 → Phase 2 → Phase 3

## Implementation Notes

- No implementation notes yet.

## Acceptance Criteria

1. After quitting the TUI (Ctrl+C or clicking Quit), all `nextrec.*` log messages from the session are printed to stderr
2. The format matches the TextualHandler format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
3. Existing test suite passes with zero warnings
4. No impact on TUI performance or display during operation
