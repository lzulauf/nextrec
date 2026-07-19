# Plan: Behavioral Test Coverage

## Status

Drafting

## Goal

Use coverage gap reports to identify and add tests for behaviorally significant code paths that are currently untested. Not aiming for 100% — only targets worth testing.

Strategy:
1. **Refactor first**: separate output/UI logic from pure business logic by extracting data-returning functions
2. **Then test the extracted functions**: pure functions need no mocking; session-based functions use existing `fake_playwright` fixture
3. **Monkeypatch only as last resort**: for thin Typer command wrappers that remain after extraction, use monkeypatch to mock heavyweight dependencies

## Methodology

Coverage report (`pytest --cov=nextrec --cov-report=term-missing`) classified each uncovered line by behavioral significance:

- **High**: affects user-visible results or error handling
- **Medium**: recovery paths, input validation, data transformations
- **Low**: platform-specific branches, debug logging, defensive `continue`/`pass`, parser internals

Excluded from targeted gap-filling: `tui/app.py` widget methods (compose, actions, event handlers) — these require a Textual test harness. Their business logic IS extracted and tested.

## Scope

**Extraction work**:
- Move `_parse_date`, `_parse_time`, `_resolve_chrome` from `cli/main.py` → new `cli/helpers.py`
- Extract constraint-building logic (duplicated between `book` and `tui` CLI commands, ~40 lines) → `cli/helpers.py`
- Extract `_async_book`'s core search + slot-fetching into `search_facilities(session, ...) -> dict` (returns data, no `typer.echo`). `_async_book` becomes a thin formatting wrapper
- Extract TUI `_run_search`'s facility-processing core into `fetch_facility_slots(session, ...) -> list[SlotInfo]`
- Extract form-value parsing from `tui/app.py:_read_constraints` → `cli/helpers.py`
- Then add tests for all extracted functions

**Monkeypatch-only** (no refactor needed, thin wrappers):
- Typer command `book()` — monkeypatch `_resolve_chrome`, `_ensure_auth_session`, `_async_book`, `typer.echo`
- Typer command `tui()` — same pattern
- Typer command `auth()` — monkeypatch `_resolve_chrome`, `_auth_async`, `typer.echo`
- These are thin orchestration wrappers; their value is verifying arg plumbing

**New tests**:
- ~12 targeted tests in existing test files for uncovered behavior in `scrapers/perfectmind.py`, `auth.py`, `browser.py`, `cart.py`, `tui/timeline.py`
- ~10 tests for extracted CLI/TUI helpers in new test files
- Each test covers a meaningful behavioral path (error handling, filtering, fallback, input validation, config building)

## Out of Scope

- Integration/end-to-end tests for CLI or TUI
- Coverage for platform-specific paths (macOS, Linux Chrome discovery)
- Full Textual widget test harness
- Debug-only logging lines
- Defensive `continue` on unexpected non-dict items in loops
- Internal parser escape-character handling

## Uncovered Code by Priority

### High (behavior-changing control flow)

| File | Lines | What it does | Why it matters |
|------|-------|-------------|----------------|
| `perfectmind.py` | 436-448 | Time window filtering of slot results (`time_window_start`/`end`) | Controls which slots users see — untested filtering logic |
| `perfectmind.py` | 116, 121 | `raise ScrapeError` for malformed API responses (non-dict, non-list) | Error resilience when API format changes |
| `perfectmind.py` | 220, 227 | `raise ScrapeError` when service_id or calendar_id missing in config | Error handling for malformed facility page |
| `perfectmind.py` | 278, 282 | `raise ScrapeError` for non-dict slot response / non-list availabilities | API format validation |
| `auth.py` | 158-159 | `except LoginFailedError` fallback when auto-login fails and no storage path | User-visible error when credentials are wrong |
| `browser.py` | 120 | `_get_context_options` loads existing `storage_state` file | Auth state loading on context creation |
| `cart.py` | 43 | `raise CartError` on CSRF token timeout | Booking failure on slow page load |

### Medium (edge cases and validation)

| File | Lines | What it does | Why it matters |
|------|-------|-------------|----------------|
| `perfectmind.py` | 389-390 | `fetch_slots` days calculation when `end_date >= target_date` | Date range boundary logic |
| `perfectmind.py` | 201-202 | `json.loads` failure returns `None` | Services parser resilience |
| `perfectmind.py` | 170-174 | `_extract_services_json` returns `None` when patterns not found | Already covered by test_returns_none_when_not_found |
| `tui/timeline.py` | 78-79 | Date separator with day labels for multi-day results | Visual formatting of timeline |
| `browser.py` | 171-172, 177-178, 183-184 | `close()` swallows exceptions from context/browser/playwright | Cleanup safety |
| `auth.py` | 95 | Submit button click when button selector found | Login form interaction path |

### Low (excluded from plan)

Platform paths (browser.py:73-76), defensive `continue` on non-dict items (perfectmind.py:232, 242, 300, 304, 148, 154), escape-char parser internals (perfectmind.py:183, 185), capacity parsing failure (perfectmind.py:132-133), debug logging (perfectmind.py:478), `_parse_availability` int/bool guard (perfectmind.py:148).

## Technical Design Details

### Phase 0: Extract testable helpers

**Target: `cli/main.py`**

Move these into a new `src/nextrec/cli/helpers.py`:

```python
def parse_date(s: str) -> date:
    """Parse a date string (YYYY-MM-DD or flexible format) into a date."""
    return dateparser.parse(s, default=datetime.today()).date()


def parse_time(s: str) -> time:
    """Parse a time string (HH:MM) into a time, or raise."""
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {s!r}")
    return time(int(parts[0]), int(parts[1]))


def resolve_chrome(chrome_path: Optional[Path] = None) -> str:
    """Find Chrome executable or raise typer.Exit."""
    exe = str(chrome_path) if chrome_path else find_system_chrome()
    if not exe:
        raise RuntimeError("Chrome executable not found")
    return exe


def build_search_config(
    config_path: Optional[Path],
    cli_params: dict,
    defaults: Optional[dict] = None,
) -> dict:
    """Load config file, merge CLI overrides, normalize fields, return structured config.

    Returns dict with keys: constraint, duration_min, days_count,
    num_attendees, kw_list.
    """
    defaults = defaults or {}
    raw = {}
    if config_path:
        raw = load_config(config_path)

    cli_overrides = {
        k: v for k, v in cli_params.items()
        if v is not None
    }
    merged = merge_configs(cli_overrides, raw)

    # Handle --date aliasing to start_date/end_date
    if merged.get("date"):
        d = merged["date"]
        merged.setdefault("start_date", d)
        merged.setdefault("end_date", d)

    constraint = Constraint(
        keywords=None,
        start_date=parse_date(merged["start_date"]) if merged.get("start_date") else None,
        end_date=parse_date(merged["end_date"]) if merged.get("end_date") else None,
        time_window_start=parse_time(merged["start_time"]) if merged.get("start_time") else None,
        time_window_end=parse_time(merged["end_time"]) if merged.get("end_time") else None,
    )

    raw_kw = merged.get("keywords", [])
    if isinstance(raw_kw, str):
        kw_list = [raw_kw]
    elif isinstance(raw_kw, list):
        kw_list = raw_kw
    else:
        kw_list = []

    return {
        "constraint": constraint,
        "duration_min": merged.get("duration", 60),
        "days_count": merged.get("days", 7),
        "num_attendees": merged.get("number_of_attendees", 1),
        "kw_list": kw_list,
    }
```

Then `cli/main.py` commands simplify to:
```python
cfg = build_search_config(config, {
    "keywords": keywords, "start_date": start_date, ...
})
# use cfg.constraint, cfg.duration_min, etc.
```

**Target: `tui/app.py`**

The `_read_constraints` method currently mixes `self.query_one(Input).value.strip()` with date/time parsing. Split into two layers:

- `tui/app.py:_read_constraints()` handles UI extraction (query_one calls)
- New helper `parse_constraint_form_values(values: dict) -> Constraint` in `cli/helpers.py` handles the actual parsing

The `_read_keywords` method (lines 328-332) is already a pure function in spirit — the `_read_num` method (lines 377-382) similarly.

### Phase 0c: Extract business logic from `_async_book`

`_async_book` (130 lines) mixes three concerns:
1. Core search pipeline (search facilities → fetch configs → fetch slots)
2. Output formatting (`typer.echo`)
3. Booking logic (CartManager, checkout browser, wait for Enter)

Extract concern 1 into a data-returning function:

```python
async def search_facilities(
    session: BrowserSession,
    constraint: Constraint,
    duration_min: int,
    days_count: int,
    num_attendees: int,
    kw_list: list[str],
) -> dict:
    """Search facilities, fetch configs and slots.

    Returns dict with:
      - facilities: list[Facility]
      - slots_by_facility: dict[str, list[dict]]
      - book_target: Optional[tuple[str, FacilityConfig, TimeSlot]]
    """
    scraper = PerfectMindScraper(session)
    try:
        facilities = await search_multi(session, kw_list, constraint) if kw_list else await scraper.search(constraint)
    except ScrapeError:
        raise  # caller handles logout/cleanup

    book_target = None
    slots_by_facility = {}
    for f in facilities:
        try:
            config_obj = await scraper.fetch_config(f.id)
            slot_date = constraint.start_date or date.today()
            slots = await scraper.fetch_slots(f.id, slot_date, config_obj, ...)
        except ScrapeError:
            continue

        available = [s for s in slots if not s.is_disabled]
        slots_by_facility[f.id] = [
            {"date": str(s.date), "start_time": str(s.start_time), "end_time": str(s.end_time)}
            for s in available
        ]
        if book_target is None and available:
            book_target = (f.id, config_obj, available[0])

    return {"facilities": facilities, "slots_by_facility": slots_by_facility, "book_target": book_target}
```

Then `_async_book` becomes a wrapper that calls `search_facilities` and handles output + booking:

```python
async def _async_book(...):
    session = BrowserSession(...)
    await session.start()
    await session.manager.load_storage_state(auth_path)
    try:
        result = await search_facilities(session, constraint, ...)
    except ScrapeError as e:
        typer.echo(f"ERROR: {e}", err=True)
        await session.manager.save_storage_state(auth_path)
        await session.stop()
        raise typer.Exit(1)
    # ... format and print result, handle booking ...
```

`search_facilities` lives in `cli/helpers.py` and is testable with `fake_playwright` fixture.

### Phase 0d: Extract business logic from TUI `_run_search`

Similarly, `_run_search`'s facility-processing loop (lines 409-431 in `tui/app.py`) can be extracted:

```python
async def fetch_facility_slots(
    scraper: PerfectMindScraper,
    facilities: list[Facility],
    constraint: Constraint,
    duration_min: int,
) -> list[SlotInfo]:
    """Fetch config and slots for all facilities. Returns (fid, config, slot) tuples."""
    results: list[SlotInfo] = []
    for f in facilities:
        try:
            config_obj = await scraper.fetch_config(f.id)
            slot_date = constraint.start_date or date.today()
            slots = await scraper.fetch_slots(f.id, slot_date, config_obj, ...)
        except ScrapeError:
            continue
        for s in slots:
            if not s.is_disabled:
                results.append((f.id, config_obj, s))
    results.sort(key=lambda x: (x[2].date, x[2].start_time))
    return results
```

This lives in `cli/helpers.py` (shared between TUI and CLI). The parallelization from the parallel search plan can be applied here later without changing the signature.

### New file structure

```
src/nextrec/cli/
  __init__.py
  config_loader.py    (unchanged — load_config, merge_configs)
  helpers.py          (NEW — parse_date, parse_time, resolve_chrome,
                       build_search_config, parse_constraint_form_values,
                       search_facilities, fetch_facility_slots)
  main.py             (updated — delegate to helpers)
```

### Tests

```
tests/unit/nextrec/cli/
  __init__.py
  test_helpers.py     (NEW — ~15 tests: pure helpers + search_facilities + fetch_facility_slots)
  test_config_loader.py  (NEW — ~4 tests)
  test_main.py        (NEW — ~3 tests: Typer command wrappers with monkeypatch)
```

### Test targets and approach

**1. `perfectmind.py` — time window filtering (lines 436-448)**

`fetch_slots` applies three different filters after grouping:
- Both `time_window_start` and `time_window_end` set: filter by range
- Only `time_window_start`: filter start time ≥
- Only `time_window_end`: filter end time ≤

Add 3-4 parameterized tests to `TestFetchSlots` using a fake response with slots at various times.

**2. `perfectmind.py` — error handling for malformed APIs (lines 116, 121, 220, 227, 278, 282)**

Test that `_parse_facilities` raises `ScrapeError` when given:
- Non-dict raw response
- Dict without a facility-containing key (bad structure)
- `ParseFacilities` class already exists — extend it

Test that `_parse_slots_response` raises `ScrapeError` when given:
- Non-dict raw response
- Dict with non-list `availabilities`
- `ParseSlotsResponse` class already exists — extend it

Test that `fetch_config` raises `ScrapeError` when services JSON is missing service_id or calendar_id:
- `TestFetchConfig` class already exists — extend it

**3. `auth.py` — login failure fallback (lines 158-159)**

`ensure_logged_in` falls through to `raise AuthError("No credentials provided...")` when:
- Auto-login raises `LoginFailedError` (not `CaptchaDetectedError`)
- No `storage_state_path` for manual fallback

Add test to `TestEnsureLoggedIn` for this path.

**4. `browser.py` — storage state loading (line 120)**

`_get_context_options` includes `storage_state` only when the path exists. Two branches are tested:
- Path exists → include in options (currently NOT tested)
- Path doesn't exist → empty options (currently tested in `test_load_storage_state_without_launch`)

Add a test `test_launch_loads_existing_storage_state` to `TestBrowserManager`.

**5. `cart.py` — CSRF timeout (line 43)**

`_extract_csrf` raises `CartError` when `page.locator(...).get_attribute("value")` times out. Already tested by `test_add_to_cart_raises_on_store_failure` and `test_add_to_cart_raises_on_validate_failure`, but those mock at a higher level. A direct test of `_extract_csrf` with timeout would be more precise.

Add test `test_extract_csrf_raises_on_timeout` to `TestCartManager`.

**6. `perfectmind.py` — end_date calculation (lines 389-390)**

When `end_date` is set and `>= target_date`, `fetch_slots` recalculates `days_count`. Test with a fake response.

Add test `test_fetch_slots_with_end_date_expands_days` to `TestFetchSlots`.

**7. `tui/timeline.py` — date separator labels (lines 78-79)**

In multi-day timeline (full mode), the separator between days shows `── {month}/{day} ──`. Already partially covered by `test_full_two_facilities`. Need a multi-day case in full mode to hit the non-first-day branch.

Add `test_full_two_days_date_separator` to `TestBuildTimelineRows`.

**8. `browser.py` — close() exception swallowing (lines 171-184)**

`close()` wraps each `await` in try/except/pass. Test that an exception from any of the three close operations doesn't prevent cleanup from continuing.

**9. `auth.py` — submit button click (line 95)**

`try_auto_login` finds submit button → clicks it (vs. the `else` branch which presses Enter). The Enter path is tested (no button found). Need a test where the button exists.

## Testing Approach

- All new tests go into **existing test classes** — no new test files
- Use existing mocking patterns (`fake_playwright` fixture, `Mock`, `AsyncMock`)
- Test delta: **~12 new test methods** across 5 test files
- All tests run via `pytest tests/ -v --tb=short -W error::RuntimeWarning` — 140+ passed, zero warnings

### Mocking strategy per target

| Target | Mocking approach |
|--------|-----------------|
| `parse_slots_response` time filtering | Call the static method directly with constructed dict — no Playwright mocks needed |
| `_parse_facilities` error cases | Call the method directly — pure function |
| `fetch_config` error cases | Mock `_ensure_page` → mock page with stubbed `goto`/`content`/`locator` |
| `auth.py` login failure | Mock session/page, make `try_auto_login` raise `LoginFailedError`, no `storage_state_path` |
| `browser.py` storage state | Use `fake_playwright`, set up a real temp file, verify context options |
| `cart.py` CSRF timeout | Mock `page.locator(...).get_attribute` to raise `PwTimeout` |
| `fetch_slots` with end_date | Use `_parse_slots_response` on returned data + verify days calculation |
| `timeline.py` date separators | Call `build_timeline_rows` with multi-day data in full mode |
| `browser.py` close exceptions | Patch `_context.close` to raise, verify cleanup continues |
| **Extracted functions** (`search_facilities`, `fetch_facility_slots`, `build_search_config`, etc.) | Use `fake_playwright` fixture + `Mock`/`AsyncMock` for scraper/session — no `typer.echo` to mock |
| **Typer command wrappers** (`book()`, `tui()`, `auth()`) | `monkeypatch` to replace `_resolve_chrome`, `_ensure_auth_session`, `_async_book`, `typer.echo` with `Mock`/`AsyncMock` |

## Documentation Approach

**Docs delta**: none. Internal improvements only.

## Progress Checklist

- [ ] Phase 0a: Extract pure CLI helpers (`parse_date`, `parse_time`, `resolve_chrome`, `build_search_config`, `parse_constraint_form_values`) → `cli/helpers.py`
- [ ] Phase 0b: Extract `search_facilities` from `_async_book` → `cli/helpers.py`
- [ ] Phase 0c: Extract `fetch_facility_slots` from TUI `_run_search` → `cli/helpers.py`
- [ ] Phase 0d: Update `_async_book` and `_run_search` to delegate to extracted functions
- [ ] Phase 0e: Tests for extracted functions (~15 tests in `test_helpers.py`)
- [ ] Phase 0f: Tests for `config_loader.py` (~4 tests in `test_config_loader.py`)
- [ ] Phase 0g: Typer command wrapper tests with monkeypatch (~3 tests in `test_main.py`)
- [ ] Phase 1: High-priority gap tests (time filtering, API error handling, auth fallback, storage state, CSRF timeout)
- [ ] Phase 2: Medium-priority gap tests (end_date, timeline separators, close exception handling, submit button)
- [ ] Phase 3: Full suite passes with zero warnings; review coverage gain

## Phases

### Phase 0: Extract CLI helpers

**Files**: `src/nextrec/cli/helpers.py` (NEW), `src/nextrec/cli/main.py` (update)

- Create `cli/helpers.py` with `parse_date`, `parse_time`, `resolve_chrome`, `build_search_config`, `parse_constraint_form_values`
- Update `cli/main.py` — `book` command delegates to `build_search_config`; `_parse_date`, `_parse_time`, `_resolve_chrome` become wrappers that call helpers and convert errors to Typer exceptions
- Update `tui/app.py` — `_read_constraints` calls `parse_constraint_form_values` for the date/time parsing; `_read_num` and `_read_keywords` stay in TUI (they're trivial and UI-coupled)

### Phase 0b: Extract `search_facilities` from `_async_book`

**Files**: `src/nextrec/cli/helpers.py` (update), `src/nextrec/cli/main.py` (update)

- Create `search_facilities(session, constraint, duration_min, days_count, num_attendees, kw_list) -> dict` in helpers.py
- Returns structured dict with `facilities`, `slots_by_facility`, `book_target` — no `typer.echo` calls
- `_async_book` delegates to it, then handles formatting, booking, and checkout browser

### Phase 0c: Extract `fetch_facility_slots` from TUI `_run_search`

**Files**: `src/nextrec/cli/helpers.py` (update), `src/nextrec/tui/app.py` (update)

- Create `fetch_facility_slots(scraper, facilities, constraint, duration_min) -> list[SlotInfo]` in helpers.py
- Shared between TUI and CLI (both do the same facility loop)
- TUI `_run_search` delegates to it, then updates UI with results
- Future parallelization (from parallel search plan) applies here without changing callers

### Phase 0d: Update callers

- `cli/main.py:_async_book` calls `search_facilities`, then formats output with `typer.echo`
- `tui/app.py:_run_search` calls `fetch_facility_slots`, then calls `_on_search_done`
- Pure functions (parse_date, etc.) called via helpers module — old local versions become wrappers or are deleted

### Phase 0e: Tests for extracted helpers

**Files**: `tests/unit/nextrec/cli/test_helpers.py` (NEW)

Tests for pure helpers:
- `test_parse_date_valid` / `test_parse_time_valid` / `test_parse_time_invalid`
- `test_resolve_chrome_found` / `test_resolve_chrome_not_found`
- `test_build_search_config_minimal` / `test_build_search_config_with_date_alias` / `test_build_search_config_keywords_as_list`
- `test_parse_constraint_form_values_all_fields`

Tests for session-based helpers (use `fake_playwright` fixture + mock scraper):
- `test_search_facilities_happy_path` / `test_search_facilities_scrape_error`
- `test_fetch_facility_slots_happy_path` / `test_fetch_facility_slots_skip_on_scrape_error`

### Phase 0f: Tests for config_loader

**Files**: `tests/unit/nextrec/cli/test_config_loader.py` (NEW)

- `test_load_config_json` / `test_load_config_yaml` / `test_load_config_unsupported_format`
- `test_merge_configs_cli_overrides_file`

### Phase 0g: Typer command wrapper tests

**Files**: `tests/unit/nextrec/cli/test_main.py` (NEW)

These test the thin orchestration layer after extraction. Heavy monkeypatch use — acceptable here because the wrappers are simple delegation with no internal logic:

```python
def test_book_command_happy_path(monkeypatch):
    mock_echo = Mock()
    monkeypatch.setattr("nextrec.cli.main.typer.echo", mock_echo)
    monkeypatch.setattr("nextrec.cli.main._resolve_chrome", Mock(return_value="/fake/chrome"))
    monkeypatch.setattr("nextrec.cli.main._ensure_auth_session", AsyncMock(return_value="session.json"))
    mock_book = AsyncMock()
    monkeypatch.setattr("nextrec.cli.main._async_book", mock_book)

    book(keywords=["tennis"], start_date="2026-07-20", end_date="2026-07-20", ...)

    mock_book.assert_awaited_once()
```

Tests:
- `test_book_command_happy_path` — verifies correct delegation
- `test_tui_command_happy_path` — verifies TUI app is created and run
- `test_book_command_missing_chrome` — verifies error output

### Phase 1: High priority targets

| Test | File | Class | Lines covered |
|------|------|-------|-------------|
| `test_time_window_both_ends` | `test_perfectmind.py` | TestFetchSlots | 438-439 |
| `test_time_window_start_only` | `test_perfectmind.py` | TestFetchSlots | 445-446 |
| `test_time_window_end_only` | `test_perfectmind.py` | TestFetchSlots | 447-448 |
| `test_raises_on_non_dict_response` | `test_perfectmind.py` | TestParseFacilities | 116 |
| `test_raises_on_non_list_items` | `test_perfectmind.py` | TestParseFacilities | 121 |
| `test_raises_on_non_dict_slot_response` | `test_perfectmind.py` | TestParseSlotsResponse | 278 |
| `test_raises_on_non_list_availabilities` | `test_perfectmind.py` | TestParseSlotsResponse | 282 |
| `test_raises_on_missing_service_id` | `test_perfectmind.py` | TestFetchConfig | 220 |
| `test_raises_on_missing_calendar_id` | `test_perfectmind.py` | TestFetchConfig | 227 |
| `test_auto_login_failure_no_fallback` | `test_auth.py` | TestEnsureLoggedIn | 158-159 |
| `test_launch_loads_existing_storage_state` | `test_browser_manager.py` | TestBrowserManager | 120 |
| `test_extract_csrf_raises_on_timeout` | `test_cart.py` | TestCartManager | 43 |

### Phase 2: Medium priority targets

| Test | File | Class | Lines covered |
|------|------|-------|-------------|
| `test_fetch_slots_with_end_date` | `test_perfectmind.py` | TestFetchSlots | 389-390 |
| `test_services_json_parse_failure` | `test_perfectmind.py` | TestExtractServicesJson | 201-202 |
| `test_full_two_days_date_separator` | `test_timeline.py` | TestBuildTimelineRows | 78-79 |
| `test_close_swallows_exceptions` | `test_browser_manager.py` | TestBrowserManager | 171-184 |
| `test_submits_via_button_when_found` | `test_auth.py` | TestTryAutoLogin | 95 |

### Phase 3: Verify

- Run full suite: `pytest tests/ -v --tb=short -W error::RuntimeWarning`
- Check updated coverage report: roughly +2-3% overall

## Execution Order

Phase 1 (highest behavioral value) → Phase 2 → Phase 3

## Implementation Notes

- No implementation notes yet.

## Acceptance Criteria

1. All 128 existing tests still pass (zero regressions)
2. ~37 new tests added (~15 extracted helpers, ~4 config_loader, ~3 Typer wrappers, ~15 targeted gaps)
3. Coverage increases measurably:
   - `cli/helpers.py` (NEW) near 100%
   - `cli/config_loader.py` from 0% to ~90%
   - `cli/main.py` from 0% to ~15% (Typer wrappers)
   - Selected uncovered lines in `perfectmind.py`, `auth.py`, `browser.py`, `cart.py` covered
4. `search_facilities` and `fetch_facility_slots` testable without mocking Typer or Textual
5. Typer command tests use monkeypatch only for thin orchestration wrappers (acceptable — no business logic in wrappers after extraction)
6. Zero warnings from RuntimeWarning or DeprecationWarning
7. CLI and TUI produce identical results after extraction (no behavioral change)
