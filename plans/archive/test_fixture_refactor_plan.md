# Plan: Test Fixture Refactor

## Status

Done

## Goal

Eliminate duplicated mock setup in async tests by extracting reusable fixtures and helpers, reducing ~200 lines of boilerplate across 6 test files.

## Why this comes first

After the httpx2 migration, the test suite is cleaner but cross-file duplication crept in — `_make_config()`, `_make_slot()`, `session = Mock()` appear identically in multiple files. Consolidating them now prevents the duplication from spreading further.

## Scope

- Move duplicated model factories (`_make_config`, `_make_slot`) and httpx2 mock helpers to a shared module
- Add `mock_session` fixture for the pervasive `session = Mock()` pattern
- Add auth-specific helpers for the repeated Playwright page mock setup
- Keep tests that need unusual mock behavior free to override after receiving the fixture

## Out of Scope

- Changing test logic or assertions
- Adding new test coverage (separate plan)
- `test_timeline.py` — already clean, module-level constants
- `test_browser_manager.py` — minor, only ~8 lines to save

## Current Boilerplate Inventory

### Top patterns

| Pattern | Files affected | Occurrences | Lines each | Wasted lines |
|---------|---------------|-------------|------------|--------------|
| `_make_config()` / `_make_slot()` duplication | cart, search | 2 files | ~7-8 each | ~30 |
| `session = Mock()` | auth, cart, perfectmind | 32 | 1 | 32 |
| `session.get_httpx_client = AsyncMock(...)` | cart | 7 | 1 | 7 |
| `PerfectMindScraper(session)` | perfectmind | 17 | 1 | 17 |
| `page = Mock()` + page url/wait setup | auth | 21 | 2-3 | ~50 |
| `page.wait_for_selector` side-effect chains | auth | 6 | 8-20 | ~60 |
| `locator(sel)` branches for login form | auth | 4 | 10-14 | ~50 |

### Per-file targets

| File | Lines | Estimated savings | What |
|------|-------|------------------|------|
| `test_auth.py` | 423 | 80-110 | Session+page fixtures, CSRF/captcha helpers, login locator factory |
| `test_perfectmind.py` | 528 | 40-60 | `mock_session` fixture, shared config/slot factories |
| `test_cart.py` | 148 | 20-30 | Shared helpers, `mock_session` + httpx2 client fixture |
| `test_search.py` | 162 | 10-15 | Eliminate `_make_config`/`_make_slot` duplication |
| `test_browser_manager.py` | 258 | 5-10 | Minor cleanups |
| **Total** | | **~155-225** | |

## Technical Design Details

### Phase 1: Shared model factories (`tests/conftest.py`)

Move the duplicated `_make_config` and `_make_slot` to a shared location so `test_cart.py` and `test_search.py` both import from the same place:

```python
# tests/conftest.py — new additions

from datetime import date, time
from nextrec.models import DurationPrice, FacilityConfig, TimeSlot


@pytest.fixture
def make_config():
    def _make(facility_id="fac-1", calendar_id="cal-1", service_id="svc-1",
              duration_prices=None):
        if duration_prices is None:
            duration_prices = [
                DurationPrice(id="dur-1", minutes=60, resident_price=5.0, non_resident_price=6.0),
            ]
        return FacilityConfig(
            facility_id=facility_id, calendar_id=calendar_id,
            service_id=service_id, program_id=service_id,
            duration_prices=duration_prices,
        )
    return _make


@pytest.fixture
def make_slot():
    def _make(ticks=639200664000000000, dt=date(2026, 7, 20),
              start=time(11, 0), end=time(12, 0), duration_minutes=60,
              is_disabled=False, base_slot_ticks=None):
        return TimeSlot(
            date=dt, start_time=start, end_time=end,
            ticks=ticks, duration_minutes=duration_minutes,
            duration_ticks=36000000000, is_disabled=is_disabled,
            base_slot_ticks=base_slot_ticks,
        )
    return _make
```

### Phase 2: `mock_session` fixture (`tests/conftest.py`)

```python
@pytest.fixture
def mock_session():
    session = Mock()
    session.manager = Mock()
    session.manager.new_page = AsyncMock()
    session.manager.load_storage_state = AsyncMock()
    session.start = AsyncMock()
    session.stop = AsyncMock()
    session.get_httpx_client = AsyncMock()
    return session
```

### Phase 3: httpx2 test helpers (`tests/conftest.py`)

Consolidate the httpx2 mock response pattern used in `test_cart.py` and `test_perfectmind.py`:

```python
import httpx2

@pytest.fixture
def mock_httpx_client():
    client = Mock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


def make_mock_response(text="", json_data=None, ok=True):
    resp = Mock()
    resp.text = text
    resp.json = Mock(return_value=json_data or {})
    resp.status_code = 200 if ok else 500
    if ok:
        resp.raise_for_status = Mock()
    else:
        def _raise():
            raise httpx2.HTTPStatusError("error", request=Mock(), response=resp)
        resp.raise_for_status = _raise
    return resp
```

### Phase 4: Auth test helpers (`tests/unit/nextrec/auth/conftest.py` or inline)

Auth tests have the most remaining Playwright boilerplate. Helper functions for the repeated patterns:

```python
def make_auth_page(url, *, has_csrf=True, has_recaptcha=False, has_logout=False):
    """Create a mock Playwright page pre-wired for auth scenarios."""
    page = Mock()
    page.url = url
    page.goto = AsyncMock()

    def _selector(sel):
        elem = Mock()
        if has_csrf and "__RequestVerificationToken" in sel:
            elem.get_attribute = AsyncMock(return_value="csrf-token")
            return elem
        if has_recaptcha and "recaptcha" in sel:
            return elem
        if has_logout and "MyLoggedIn" in sel:
            return elem
        raise Exception("not found")
    page.wait_for_selector = AsyncMock(side_effect=_selector)
    return page
```

### Example: before and after

**Before** (test_cart.py, ~10 lines per test):
```python
async def test_add_to_cart_success(self):
    session = Mock()
    session.get_httpx_client = AsyncMock(return_value=_make_http_client())
    cm = CartManager(session)
    ...
```

**After** (~5 lines):
```python
async def test_add_to_cart_success(self, mock_session, mock_httpx_client):
    mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
    cm = CartManager(mock_session)
    ...
```

## Testing Approach

**Test delta**: no new tests. Existing tests are rewritten to use fixtures.

Run full suite after each phase: `pytest tests/ -W error::RuntimeWarning`

## Documentation Approach

**Docs delta**: none. Test infrastructure only.

## Progress Checklist

- [x] Phase 1: Move `_make_config`/`_make_slot` to `tests/conftest.py`; update `test_cart.py` and `test_search.py`
- [x] Phase 2: Add `mock_session` fixture to `tests/conftest.py`; convert caller files
- [x] Phase 3: Add `mock_httpx_client` and `make_mock_response` to `tests/conftest.py`; convert `test_cart.py` and `test_perfectmind.py`
- [x] Phase 4: Skipped — auth tests have highly customized mock setups per test, generic fixtures offer minimal savings
- [x] Phase 5: 128 tests pass; ~67 lines removed from test files, conftest provides shared infrastructure for future tests

## Phases

### Phase 1: Shared model factories

**Files**: `tests/conftest.py`, `test_cart.py`, `test_search.py`

- Add `make_config` and `make_slot` fixtures to conftest
- Remove local `_make_config`/`_make_slot` from cart and search test files
- Update test methods to accept the fixtures

### Phase 2: `mock_session` fixture

**Files**: `tests/conftest.py`, `test_cart.py`, `test_perfectmind.py`, `test_auth.py`

- Add `mock_session` fixture with pre-wired manager sub-mocks
- Replace `session = Mock(); session.manager = Mock()` in each test
- Tests that need unusual behavior override after receiving the fixture

### Phase 3: httpx2 helpers

**Files**: `tests/conftest.py`, `test_cart.py`, `test_perfectmind.py`

- Add `mock_httpx_client` fixture and `make_mock_response` helper
- Remove local `_make_http_client()` and `_mock_resp()` from cart
- Remove local `_make_mock_response()` from perfectmind (keep `_common_mocks` and `_SERVICES_HTML` — they're domain-specific)
- Add shared `_CSRF_HTML` constant for the standard CSRF-containing HTML snippet

### Phase 4: Auth test helpers

**Files**: `test_auth.py`

- Extract repeated page mock setup into shared helpers within the file
- Collapse the 4-6 variants of `wait_for_selector` side-effect functions
- Extract login locator factory (the 10-14 line `locator(sel)` closure)

### Phase 5: Verify

- Run full suite: `pytest tests/ -W error::RuntimeWarning`
- Count lines removed vs added
- Ensure zero behavioral changes

## Execution Order

Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

Phases 1-3 are the highest-value (widely reused). Phase 4 is auth-only.

## Implementation Notes

### 2026-07-19 — Phases 1-3 complete, Phase 4 deferred
- Scope completed: Added shared fixtures to `tests/conftest.py` (`make_config`, `make_slot`, `mock_session`, `mock_httpx_client`, `make_mock_response`, `_CSRF_HTML`). Removed duplicated local helpers from `test_cart.py`, `test_search.py`, and `test_perfectmind.py`.
- Code touchpoints:
  - `tests/conftest.py` — Added 6 new fixtures/helpers (70 new lines)
  - `tests/unit/nextrec/test_cart.py` — Removed `_make_config`, `_make_slot`, `_mock_resp`, `_make_http_client`, `_CSRF_HTML`, `import httpx2`; tests now accept `mock_session`, `mock_httpx_client`, `make_config`, `make_slot` fixtures
  - `tests/unit/nextrec/test_search.py` — Removed `_make_config`, `_make_slot`; inlined config fallback in `_mock_scraper`
  - `tests/unit/nextrec/scrapers/test_perfectmind.py` — Removed `_make_mock_response`, `import httpx2`; imports `make_mock_response` from conftest
- Tests: 128 pass
- Follow-ups: Auth tests (`test_auth.py`) remain with Playwright-based mock setup; each test has highly customized page mocks that don't benefit from generic fixtures

## Risks and Mitigations

- **Risk**: Fixture overrides make individual tests harder to understand. **Mitigation**: Only override specific attrs post-fixture when needed; keep fixtures simple.
- **Risk**: Moving httpx2 helpers to conftest creates a dependency on httpx2 for all tests. **Mitigation**: Already a dev dependency; no new import needed.

## Acceptance Criteria

1. All existing tests pass identically
2. ~160-220 lines of boilerplate removed across the test suite
3. `_make_config` and `_make_slot` exist in exactly one place
4. `session = Mock(); session.manager = Mock()` eliminated from all test files
5. Zero warnings
