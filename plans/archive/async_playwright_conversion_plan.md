# Plan: Convert to async Playwright on Textual's event loop

## Status

Implementing

## Goal

Eliminate "It looks like you are using Playwright Sync API inside the asyncio loop" and "Cannot switch to a different thread" errors by running all Playwright operations on Textual's existing asyncio event loop, removing worker threads for Playwright work.

## Why this comes first

The current architecture has a fundamental mismatch: Textual runs an asyncio event loop on the main thread, while all Playwright operations use the sync API in worker threads. Sync Playwright internally creates its own asyncio loop per thread, which leaks when threads are reused. The only durable fix is to align on a single loop.

## Scope

- Convert `BrowserManager` and `BrowserSession` to async (using `playwright.async_api`)
- Convert `CartManager` to async
- Convert `PerfectMindScraper` to async
- Convert TUI search and booking from `@work(thread=True)` to `@work(thread=False)` (async)
- Wrap async calls in `asyncio.run()` for CLI commands (one-shot, no loop conflict)
- Convert `auth.py` to async

## Out of scope

- Changing the TUI framework (stays Textual)
- Changing the model/data classes
- Changing the timeline pure function (already stateless)
- Adding new features

## Technical design details

### Async conversion pattern

Every sync Playwright call maps directly to an async equivalent:

| Sync | Async |
|------|-------|
| `sync_playwright().start()` | `await async_playwright().start()` |
| `page.goto(url, wait_until="networkidle")` | `await page.goto(url, wait_until="networkidle")` |
| `page.request.post(url, ...)` | `await page.request.post(url, ...)` |
| `element.get_attribute("value")` | `await element.get_attribute("value")` |
| `page.content()` | `await page.content()` |
| `page.wait_for_selector(...)` | `await page.wait_for_selector(...)` |
| `context.storage_state(path=...)` | `await context.storage_state(path=...)` |
| `context.close()` | `await context.close()` |
| `browser.close()` | `await browser.close()` |

### File touchpoints

#### 1. `src/nextrec/browser.py`
- Replace `from playwright.sync_api import ...` with `from playwright.async_api import ...`
- Convert `BrowserManager` methods to `async def`:
  - `launch()`, `close()`, `new_page()`, `save_storage_state()`, `load_storage_state()`, `fetch_json()`
- Convert `BrowserSession` methods to `async def`:
  - `start()`, `stop()`
- Store `_request_log` as before (sync list access is fine)

#### 2. `src/nextrec/cart.py`
- Import `Page` from `playwright.async_api`
- Convert `CartManager` methods to `async def`:
  - `_ensure_page()`, `add_to_cart()`, `_book_single()`, `_extract_csrf()`
- All `page.request.post()` → `await page.request.post()`
- All `page.goto()` → `await page.goto()`
- All `page.wait_for_selector()` → `await page.wait_for_selector()`
- CSRF token read: `element.get_attribute()` → `await element.get_attribute()`

#### 3. `src/nextrec/scrapers/perfectmind.py`
- Import `Page` from `playwright.async_api`
- Convert `PerfectMindScraper` methods to `async def`:
  - `_ensure_page()`, `search()`, `fetch_config()`, `fetch_slots()`
- All `page.goto()` → `await page.goto()`
- All `page.request.post()` → `await page.request.post()`
- `page.content()` → `await page.content()`
- All `page.wait_for_selector()` → `await page.wait_for_selector()`
- Element attribute reads: `await element.get_attribute()`

#### 4. `src/nextrec/auth.py`
- Import `Page` from `playwright.async_api`
- Convert `check_session()`, `capture_login_interactive()`, `auto_login()` to `async def`
- All `page.goto()` → `await page.goto()`
- All `page.wait_for_selector()` → `await page.wait_for_selector()`
- `page.locator().fill()` → `await page.locator().fill()`
- `page.locator().click()` → `await page.locator().click()`
- `page.keyboard.press()` → `await page.keyboard.press()`

#### 5. `src/nextrec/tui/app.py`
- Change `_run_search` from `@work(thread=True)` to `@work(thread=False)` (async coroutine)
- Change `_run_booking` from `@work(thread=True)` to `@work(thread=False)` (async coroutine)
- Remove `call_from_thread()` calls — everything runs on the main event loop
- Use `await session.start()` etc. instead of sync calls
- `checkout_session.stop()` is now `await checkout_session.stop()` — runs on main thread safely
- `_start_session()` becomes `async def`
- `_close_session()` becomes `async def`

#### 6. `src/nextrec/cli/main.py`
- CLI type commands use `asyncio.run()` to call async functions:
  ```python
  def book(...):
      asyncio.run(_async_book(...))
  ```
- Or convert Typer commands to async (Typer doesn't natively support async, but we can use `asyncio.run`)

#### 7. `src/nextrec/search.py`
- `search_multi()` calls the scraper — convert to `async def`

### TUI async flow (before vs after)

**Before (sync, threads):**
```
Textual event loop (main thread)
  ├── @work(thread=True) _run_search
  │   └── sync Playwright in thread → call_from_thread to update UI
  ├── @work(thread=True) _run_booking
  │   └── sync Playwright in thread → call_from_thread to update UI + push screen
  └── CheckoutScreen.done() → checkout_session.stop() → ERROR
```

**After (async, single loop):**
```
Textual event loop (main thread) — single loop for everything
  ├── @work(thread=False) _run_search
  │   └── async Playwright → direct UI updates
  ├── @work(thread=False) _run_booking
  │   └── async Playwright → direct UI updates + push screen
  └── CheckoutScreen.done() → await checkout_session.stop() → OK
```

## Testing approach

- All 129 existing tests exercise the model, auth, cart, browser_manager, search, scraper, and timeline functions
- Tests for `browser_manager.py` create mock Playwright objects — these will need updating to async mock patterns
- Tests for `cart.py` and `scrapers/perfectmind.py` similarly use mock Playwright objects
- Strategy: update existing tests to use `pytest.mark.asyncio` and `async/await` where they test async functions; keep sync tests unchanged where possible

Expected test delta: update ~30 existing tests (the ones that directly test async-converted functions).

## Documentation approach

No user-facing documentation changes needed. The CLI interface and TUI behavior remain identical.

Expected docs delta: none.

## Progress checklist

- [x] Phase 1: Convert `BrowserManager` + `BrowserSession` to async
- [x] Phase 2: Convert `PerfectMindScraper` to async
- [x] Phase 3: Convert `CartManager` to async
- [x] Phase 4: Convert `auth.py` to async
- [x] Phase 5: Convert `search.py` to async
- [x] Phase 6: Convert TUI `app.py` to async
- [x] Phase 7: Convert `cli/main.py` to use `asyncio.run()` for async calls
- [x] Phase 8 (browser + scraper tests): Update existing tests for async
- [x] Phase 8 (cart tests): Update CartManager tests for async
- [x] Phase 8 (auth tests): Update auth tests for async
- [x] Phase 8 (search tests): Update search tests for async
- [x] All tests pass
- [ ] Manual verification: single booking succeeds
- [ ] Manual verification: second consecutive booking succeeds
- [ ] Manual verification: multi-slot booking succeeds

## Phases

### Phase 1 — async BrowserManager + BrowserSession

Files: `src/nextrec/browser.py`

- Change import to `from playwright.async_api import ...`
- Convert all methods to `async def`
- Update internal calls to use `await`

### Phase 2 — async PerfectMindScraper

Files: `src/nextrec/scrapers/perfectmind.py`

- Import `Page` from `playwright.async_api`
- Convert all methods to `async def`
- Update all Playwright calls to use `await`

### Phase 3 — async CartManager

Files: `src/nextrec/cart.py`

- Import `Page` from `playwright.async_api`
- Convert all methods to `async def`
- Update all Playwright calls to use `await`

### Phase 4 — async auth

Files: `src/nextrec/auth.py`

- Import from `playwright.async_api`
- Convert functions to `async def`

### Phase 5 — async search

Files: `src/nextrec/search.py`

- `search_multi` becomes `async def`

### Phase 6 — async TUI

Files: `src/nextrec/tui/app.py`

- Change `@work(thread=True)` → `@work(thread=False)` on search and booking
- Remove `call_from_thread()` usages
- Add `await` to all async calls
- `_start_session()` and `_close_session()` become async
- `_show_checkout_screen` can remain sync (just pushes a screen)
- `CheckoutScreen.done()` → `await self._checkout_session.stop()` (already on main thread)

### Phase 7 — async CLI

Files: `src/nextrec/cli/main.py`

- Wrap async function calls in `asyncio.run()` within sync Typer command handlers

### Phase 8 — Update tests

Files: all test files under `tests/unit/nextrec/`

- Add `pytest.mark.asyncio` to test classes that test async functions
- Use `await` in test bodies
- Update mock patterns for async Playwright

## Execution order

Phases 1-5 convert the library layer (can be done independently). Phase 6 depends on 1-5. Phase 7 is independent. Phase 8 must be updated as each phase progresses.

Recommended order: 1 → 8 (browser tests) → 2 → 8 (scraper tests) → 3 → 8 (cart tests) → 4 → 8 (auth tests) → 5 → 8 (search tests) → 6 → 7 → final test run.

## Implementation notes

### 2026-07-19 - Phase 3 (CartManager async)
- Scope completed: Converted CartManager to async Playwright (playwright.async_api).
- Code touchpoints: `src/nextrec/cart.py` — `_ensure_page`, `_extract_csrf`, `_book_single`, `add_to_cart` all now async; removed sync `page` property.
- Tests: Updated all 10 cart tests to use `@pytest.mark.asyncio`, `AsyncMock`, and `await`.
- Follow-ups: None.

### 2026-07-19 - Phase 6 (TUI app.py async)
- Scope completed: Converted TUI app.py to async.
- Code touchpoints: `src/nextrec/tui/app.py` — `_start_session`, `_close_session` now async; `_run_search` and `_run_booking` changed from `@work(thread=True)` to `@work(thread=False)`; removed `call_from_thread()` and `threading.Event`; replaced with `asyncio.Event`; `CheckoutScreen.done()` uses `asyncio.ensure_future()` to stop session; all Playwright calls use `await`.
- Tests: No TUI tests existed; timeline pure function tests unchanged.
- Follow-ups: None.

### 2026-07-19 - Phase 7 (CLI main.py async)
- Scope completed: Converted CLI to use `asyncio.run()` for all async operations.
- Code touchpoints: `src/nextrec/cli/main.py` — `_run_auth_flow`, `_ensure_auth_session` now async; `book` command wraps in `asyncio.run()`; `auth` command wrapped; `debug-browse` wrapped; `tui` uses `asyncio.run()` for auth check (Textual runs its own loop).
- Tests: No CLI tests exist; unit tests unchanged.
- Follow-ups: None.

### 2026-07-19 - Phase 4 (auth.py async)
- Scope completed: Converted auth.py to async Playwright (playwright.async_api).
- Code touchpoints: `src/nextrec/auth.py` — all functions now async (`is_logged_in`, `_extract_csrf`, `_detect_captcha`, `try_auto_login`, `capture_login_interactive`, `ensure_logged_in`).
- Tests: Updated all 20 auth tests to use `@pytest.mark.asyncio`, `AsyncMock`, and `await`.
- Follow-ups: None.

### 2026-07-19 - Phase 5 (search.py async)
- Scope completed: Converted search.py (`search`, `search_multi`) to async.
- Code touchpoints: `src/nextrec/search.py` — both functions now `async def` and `await scraper.search()`.
- Tests: Updated all 3 search tests to async.
- Follow-ups: None.

## Risks and mitigations

- Risk: `pytest.mark.asyncio` requires `pytest-asyncio` installed. Mitigation: already listed as a dev dependency in the skill documentation; add if missing.
- Risk: `asyncio.run()` in CLI creates a new event loop each time. Mitigation: CLI commands are one-shot, so this is fine. The event loop is fully cleaned up after each command.
- Risk: Textual's `@work(thread=False)` runs the coroutine on the event loop — if the coroutine blocks (not awaits), the UI freezes. Mitigation: all async Playwright calls properly yield control via `await`, so the UI stays responsive. Cart operations (page navigation, API calls) will yield while waiting for network.
- Risk: `checkout_session.stop()` being async means we need to await it from the main thread, but `CheckoutScreen.done()` is a sync event handler. Mitigation: use `self.call_later()` or `self.set_timer()` to run the stop asynchronously, or use `asyncio.create_task()`.

## Acceptance criteria

1. `pytest -x` passes (all tests updated for async).
2. TUI: search completes and displays results.
3. TUI: single-slot booking opens checkout browser, Done closes it cleanly.
4. TUI: second consecutive booking succeeds without errors.
5. TUI: multi-slot booking processes all slots without errors.
6. CLI: `nextrec book`, `nextrec auth`, `nextrec debug-browse` still work (wrapped in `asyncio.run()`).
