# Plan: Test Fixture Refactor

## Status

Drafting

## Goal

Eliminate boilerplate in async tests by extracting reusable pytest fixtures, reducing ~346 duplicated lines across 7 test files. Remove the cognitive overhead of repeated mock setup so tests focus on behavior, not wiring.

## Methodology

Coverage analysis identified every repeated mock-setup pattern. Each pattern gets a fixture or factory function at the appropriate scope level — module-level helpers for model builders, `conftest.py` fixtures for mock objects.

## Scope

- Add fixtures to `tests/conftest.py` (session-scope shared mocks) and `tests/unit/nextrec/conftest.py` (domain-specific mocks)
- Convert existing tests to use fixtures where the fixture handles the standard setup
- Keep tests that need unusual mock behavior (side effects, exceptions) free to override specific attrs after getting the fixture
- Only patterns with 3+ occurrences are targeted

## Out of Scope

- Changing test logic or assertion behavior
- Adding new test coverage (separate plan: `coverage_gap_plan.md`)
- `test_models.py` — already clean, no boilerplate
- `test_timeline.py` — already uses module-level constants, minimal boilerplate
- `test_search.py` — small file, its mock pattern (`monkeypatch` a constructor) is already concise
- Refactoring the source code itself (only test infrastructure changes)

## Boilerplate Inventory

### Top offenders (lines × occurrences = wasted lines)

| Pattern | Tests affected | Lines each | Occurrences | Wasted lines |
|---------|---------------|-----------|-------------|
| `session = Mock()` | auth, cart, perfectmind | 1 | 47 | 47 |
| `page = Mock()` | auth, cart, perfectmind, browser | 1 | 44 | 44 |
| `page.goto = AsyncMock()` | auth, cart, perfectmind | 1 | 26 | 26 |
| `session.manager = Mock()` | auth, cart, perfectmind | 1 | 19 | 19 |
| `element.get_attribute = AsyncMock(...)` | auth, cart, perfectmind | 1 | 19 | 19 |
| `session.manager.new_page = AsyncMock(...)` | auth, cart, perfectmind | 1 | 18 | 18 |
| `page.wait_for_selector = AsyncMock(...)` | auth, cart, perfectmind | 1 | 15 | 15 |
| Page timeout block | cart | 2 | 6 | 12 |
| `page.request.post = AsyncMock(...)` | cart, perfectmind | 1 | 10 | 10 |
| `page.is_closed = Mock(return_value=False)` | perfectmind | 1 | 7 | 7 |
| Login form locator block (~20 lines) | auth | 20 | 3 | 60 |
| `DurationPrice(...)` + `FacilityConfig(...)` creation | perfectmind, cart, timeline | 4 | 9 | 36 |
| `@pytest.mark.asyncio` (class-level) | all async files | 1 | 24 | 24 |

## Technical Design Details

### Fixture catalog

**`tests/conftest.py`** (extend existing file):

```python
@pytest.fixture
def mock_session():
    """A BrowserSession-like Mock with a pre-wired manager."""
    session = Mock()
    session.manager = Mock()
    session.manager.new_page = AsyncMock()
    session.manager.save_storage_state = AsyncMock()
    session.manager.load_storage_state = AsyncMock()
    session.manager.fetch_json = AsyncMock()
    session.start = AsyncMock()
    session.stop = AsyncMock()
    return session


@pytest.fixture
def mock_page():
    """A Page-like Mock with common async methods pre-wired as AsyncMock."""
    page = Mock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.is_closed = Mock(return_value=False)
    page.set_default_navigation_timeout = Mock()
    page.set_default_timeout = Mock()
    page.keyboard.press = AsyncMock()
    page.request.post = AsyncMock()
    page.on = Mock()
    page.content = AsyncMock(return_value="<html></html>")
    page.url = "about:blank"
    page.locator = Mock(return_value=Mock(count=Mock(return_value=0)))
    page.wait_for_selector = AsyncMock(return_value=None)
    return page


@pytest.fixture
def mock_csrf_element():
    """An element whose get_attribute returns a valid CSRF token."""
    el = Mock()
    el.get_attribute = AsyncMock(return_value="faketoken123")
    return el


@pytest.fixture
def mock_response():
    """A response-like Mock with ok=True and a json method."""
    resp = Mock()
    resp.ok = True
    resp.status = 200
    resp.status_text = "OK"
    resp.json = AsyncMock(return_value={})
    resp.headers = {}
    return resp


@pytest.fixture
def mock_login_page(mock_page, mock_csrf_element):
    """A mock Page pre-wired with a login form (username, password, no submit button).

    This covers the ~20-line locator closure pattern repeated across auth tests.
    Tests can override specific locator selections by patching mock_page.locator
    after receiving this fixture.
    """
    def _locator(selector):
        if "UserName" in selector or "Email" in selector or "email" in selector:
            el = Mock()
            el.count = Mock(return_value=1)
            el.fill = AsyncMock()
            return type("_", (), {"first": el})()
        if "Password" in selector or "password" in selector:
            el = Mock()
            el.count = Mock(return_value=1)
            el.fill = AsyncMock()
            return type("_", (), {"first": el})()
        if "submit" in selector or "Sign In" in selector or "Log In" in selector:
            el = Mock()
            el.count = Mock(return_value=0)
            return type("_", (), {"first": el})()
        if "__RequestVerificationToken" in selector:
            return type("_", (), {"first": mock_csrf_element})()
        return Mock()

    mock_page.locator = _locator
    return mock_page
```

**`tests/unit/nextrec/conftest.py`** (NEW — domain-specific fixtures):

```python
import pytest
from unittest.mock import AsyncMock, Mock

from nextrec.models import DurationPrice, FacilityConfig, TimeSlot


@pytest.fixture
def mock_config_factory():
    """Factory for FacilityConfig objects with sensible defaults."""
    def _make(
        facility_id="fac-1",
        calendar_id="cal-1",
        service_id="svc-1",
        program_id="svc-1",
        duration_prices=None,
    ):
        if duration_prices is None:
            duration_prices = [
                DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0),
            ]
        return FacilityConfig(
            facility_id=facility_id,
            calendar_id=calendar_id,
            service_id=service_id,
            program_id=program_id,
            duration_prices=duration_prices,
        )
    return _make


@pytest.fixture
def mock_slot_factory():
    """Factory for TimeSlot objects with sensible defaults."""
    def _make(
        date="2026-07-20",
        start_time="09:00",
        end_time="10:00",
        duration_minutes=60,
        ticks=638000000000000000,
        is_disabled=False,
        base_slot_ticks=None,
    ):
        from datetime import date, time
        return TimeSlot(
            date=date.fromisoformat(date) if isinstance(date, str) else date,
            start_time=time.fromisoformat(start_time) if isinstance(start_time, str) else start_time,
            end_time=time.fromisoformat(end_time) if isinstance(end_time, str) else end_time,
            duration_minutes=duration_minutes,
            ticks=ticks,
            is_disabled=is_disabled,
            base_slot_ticks=base_slot_ticks,
        )
    return _make


@pytest.fixture
def fake_perfectmind_scraper(mock_page):
    """A PerfectMindScraper with all methods mocked, using mock_page.

    Returns the scraper instance. Tests access the page via scraper._page.
    """
    from nextrec.scrapers.perfectmind import PerfectMindScraper
    scraper = Mock(spec=PerfectMindScraper)
    scraper.search = AsyncMock(return_value=[])
    scraper.fetch_config = AsyncMock()
    scraper.fetch_slots = AsyncMock(return_value=[])
    scraper._session = Mock()
    scraper._page = mock_page
    scraper._ensure_page = AsyncMock(return_value=mock_page)
    return scraper
```

### Consolidation of `fake_playwright`

Extend `tests/conftest.py` to use the new fixtures internally:

```python
@pytest.fixture
def fake_playwright(monkeypatch, mock_page):
    """Provide a fake Playwright factory with a mock page.

    Returns a dict with playwright, browser, context, page keys.
    Tests can override page behavior via the returned page.
    """
    mock_pw = Mock()
    mock_pw.start = AsyncMock(return_value=mock_pw)
    mock_browser = Mock()
    mock_context = Mock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()
    mock_context.storage_state = AsyncMock()
    mock_context.request.fetch = AsyncMock()
    mock_context.set_default_timeout = Mock()

    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_pw.stop = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    monkeypatch.setattr("nextrec.browser.async_playwright", lambda: mock_pw)

    return {"playwright": mock_pw, "browser": mock_browser, "context": mock_context, "page": mock_page}
```

### Test example: before and after

**Before** (from `test_auth.py`, ~25 lines):
```python
async def test_something(self):
    session = Mock()
    session.manager = Mock()
    page = Mock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.is_closed = Mock(return_value=False)
    page.set_default_navigation_timeout = Mock()
    page.set_default_timeout = Mock()
    session.manager.new_page = AsyncMock(return_value=page)
    csrf_element = Mock()
    csrf_element.get_attribute = AsyncMock(return_value="csrf-token")
    page.wait_for_selector = AsyncMock(return_value=csrf_element)
    # ... actual test logic (5-10 lines)
```

**After** (~10 lines):
```python
async def test_something(self, mock_session, mock_page, mock_csrf_element):
    mock_session.manager.new_page = AsyncMock(return_value=mock_page)
    mock_page.wait_for_selector = AsyncMock(return_value=mock_csrf_element)
    # ... actual test logic (5-10 lines)
```

### What each test file gains

| File | Lines before | Fixtures to use | Lines after (est.) | Savings |
|------|-------------|-----------------|-------------------|---------|
| `test_perfectmind.py` | 610 | `mock_session`, `mock_page`, `mock_csrf_element`, `mock_response`, `mock_config_factory`, `mock_slot_factory` | ~500 | ~110 |
| `test_auth.py` | 423 | `mock_session`, `mock_page`, `mock_csrf_element`, `mock_login_page` | ~340 | ~83 |
| `test_cart.py` | 245 | `mock_session`, `mock_page`, `mock_csrf_element`, `mock_response`, `mock_config_factory`, `mock_slot_factory` | ~190 | ~55 |
| `test_browser_manager.py` | 258 | Updated `fake_playwright` (now includes page) | ~250 | ~8 |
| `test_timeline.py` | 105 | `mock_config_factory`, `mock_slot_factory` | ~90 | ~15 |

## Testing Approach

- Existing tests must continue passing identically — no behavioral changes
- Run full suite after each file conversion: `pytest tests/ -v --tb=short -W error::RuntimeWarning`
- Since fixtures are pytest infrastructure, they're tested implicitly by the tests that use them

**Test delta**: no new tests. Existing tests are rewritten to use fixtures.

## Documentation Approach

**Docs delta**: none. Test infrastructure only.

## Progress Checklist

- [ ] Phase 1: Add shared fixtures to `tests/conftest.py` (mock_session, mock_page, mock_csrf_element, mock_response, mock_login_page, extend fake_playwright)
- [ ] Phase 2: Domain fixtures in `tests/unit/nextrec/conftest.py` (mock_config_factory, mock_slot_factory, fake_perfectmind_scraper)
- [ ] Phase 3: Convert `test_perfectmind.py` to use fixtures
- [ ] Phase 4: Convert `test_auth.py` to use fixtures
- [ ] Phase 5: Convert `test_cart.py` to use fixtures
- [ ] Phase 6: Convert `test_browser_manager.py` to use updated `fake_playwright`
- [ ] Phase 7: Convert `test_timeline.py` to use factory fixtures
- [ ] Phase 8: Full suite passes; verify savings (~300 lines removed)

## Phases

### Phase 1: Shared fixtures

**File**: `tests/conftest.py`

- Add `mock_session`, `mock_page`, `mock_csrf_element`, `mock_response`, `mock_login_page` fixtures
- Extend `fake_playwright` to include `page` in return dict, using `mock_page` internally
- Remove unused `_async_mock()` helper

### Phase 2: Domain fixtures

**File**: `tests/unit/nextrec/conftest.py` (NEW)

- `mock_config_factory` — factory function for `FacilityConfig` with sensible defaults and parameter overrides
- `mock_slot_factory` — factory function for `TimeSlot` with sensible defaults and parameter overrides
- `fake_perfectmind_scraper` — a full mock scraper with pre-wired `search`, `fetch_config`, `fetch_slots`

### Phase 3–7: Convert each test file

Convert one file per phase. Strategy per file:

1. Add fixture parameters where the test varies mock behavior
2. Remove `session = Mock(); session.manager = Mock(); page = Mock(); page.goto = AsyncMock()` from each test
3. Replace with fixture references in test signatures
4. Where a test needs unusual mock behavior (e.g., `goto.side_effect = TimeoutError`), override after receiving the fixture

### Phase 8: Verify

- Run full suite: `pytest tests/ -v --tb=short -W error::RuntimeWarning`
- Count lines removed vs. added (target: ~300 lines net reduction)
- Ensure no behavioral changes

## Execution Order

Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8

Phases 3–7 can be done in any order within the phase, but starting with `test_perfectmind.py` (largest savings) is recommended.

## Implementation Notes

- No implementation notes yet.

## Acceptance Criteria

1. All existing tests pass identically (zero behavioral changes)
2. ~300 lines of boilerplate removed across 5 test files
3. No new boilerplate introduced by fixture definitions (fixtures are concise and reusable)
4. Any test can override fixture defaults using simple attribute assignment after fixture injection
5. `fake_playwright` still returns a dict (backward-compatible, but now includes `"page"` key)
6. Zero warnings from RuntimeWarning or DeprecationWarning
