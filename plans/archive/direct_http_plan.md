# Direct HTTP Plan

Status: Done

Goal
----
Replace Playwright `page.goto()` and `page.request.post()` with `httpx` for facility config extraction and data POSTs, reducing each page-load from ~2s to ~300-500ms. Keep Playwright only for login/auth and the final checkout browser.

Why this comes first
--------------------
Page loads are the dominant cost (~8s of 10.4s). Each `page.goto(url, wait_until="networkidle")` waits for all CSS/JS/images to load before returning — but we only need the raw HTML to parse the services JSON and CSRF token. httpx GET returns just the HTML in ~300-500ms.

Scope
-----
- Add `httpx` as a dependency
- Add cookie extraction from Playwright context → `httpx.Client`
- Replace `page.goto()` with `httpx.get()` for:
  - Facility detail page (config extraction)
  - Facility list page (CSRF token extraction)
- Replace `page.request.post()` with `httpx.post()` for:
  - `GetFacilities` (keyword search)
  - `FacilityAvailability` (slot fetch)
- Keep `page.goto()` ONLY for:
  - Login/interactive session capture
  - Checkout browser launch
- Keep `PerfectMindScraper` method signatures unchanged

Out of scope
------------
- Replacing the Playwright-based `BrowserSession` entirely
- Adding request retries or circuit breakers
- Persistent cookie storage outside Playwright

Technical Design Details
------------------------

### New dependency

Add `httpx>=0.27` to `pyproject.toml`.

### Cookie extraction

`BrowserSession` already has a `manager` with a Playwright `context`. Add a method to extract cookies and create an httpx client:

```python
# in browser.py
async def get_httpx_client(self) -> httpx.AsyncClient:
    cookies = await self.manager._context.cookies()
    jar = {}
    for c in cookies:
        jar[c["name"]] = c["value"]
    return httpx.AsyncClient(cookies=jar)
```

### New `HttpScraper` in `perfectmind.py`

A new class that mirrors `PerfectMindScraper`'s data methods but uses httpx instead of Playwright:

```python
class HttpScraper:
    def __init__(self, client: httpx.AsyncClient, config_cache: dict[str, FacilityConfig], list_csrf: Optional[str] = None):
        self._client = client
        self._config_cache = config_cache
        self._list_csrf = list_csrf
```

Methods:
- `fetch_html(url)` → GET and return text
- `_extract_csrf_from_html(html)` → parse CSRF from HTML
- `_extract_services_json_from_html(html)` → same as current static method but takes string
- `fetch_list_csrf()` → GET list page, parse CSRF, cache
- `search(constraint)` → POST GetFacilities with form data, parse facilities
- `fetch_config_and_slots(...)` → GET detail page, parse config + CSRF, POST availability

### Method details

```python
async def fetch_config_and_slots(self, facility_id, target_date, ...):
    if facility_id in self._config_cache:
        config = self._config_cache[facility_id]
    else:
        url = f"{FACILITY_DETAIL_URL}?facilityId={facility_id}"
        html = await self.fetch_html(url)
        config = self._parse_config_from_html(html, facility_id)
        self._config_cache[facility_id] = config

    base_minutes = self._resolve_duration(config.duration_prices, duration_minutes)
    csrf = await self.fetch_list_csrf()

    form = {
        "facilityId": facility_id,
        "date": date_iso,
        "daysCount": str(days_count),
        "duration": str(base_minutes),
        "serviceId": config.service_id,
        "__RequestVerificationToken": csrf,
        "durationIds[]": api_ids,
    }
    resp = await self._client.post(FACILITY_AVAILABILITY_URL, data=form, headers={...})
    resp.raise_for_status()
    raw = resp.json()
    slots = self._parse_slots_response(raw, config, base_minutes)
    ...
    return config, slots
```

### Integration with `search_and_fetch`

`search_and_fetch` creates an `HttpScraper` instead of `PerfectMindScraper`:

```python
client = await session.get_httpx_client()
scraper = HttpScraper(client, shared_config_cache)
await scraper.fetch_list_csrf()
```

But the TUI and CLI still use `PerfectMindScraper` for the single-keyword path (via `search.py`). I should either:
1. Make `search.py`'s `search()` and `search_and_fetch()` both use `HttpScraper`
2. Or have `PerfectMindScraper` delegate to `HttpScraper`

Option 1 is cleaner.

### Touchpoints

| File | Changes |
|------|---------|
| `pyproject.toml` | Add `httpx>=0.27` |
| `src/nextrec/browser.py` | Add `get_httpx_client()` method |
| `src/nextrec/scrapers/perfectmind.py` | Add `HttpScraper` class; keep `PerfectMindScraper` for login/checkout |
| `src/nextrec/search.py` | Use `HttpScraper` instead of `PerfectMindScraper` in `search_and_fetch` |
| `tests/` | Update mocks for `HttpScraper`; httpx responses instead of page mocks |

### Error handling

- httpx raises `httpx.HTTPStatusError` for non-2xx → wrap in `ScrapeError`
- Connection errors → wrap in `ScrapeError`
- JSON parse errors → wrap in `ScrapeError`

Testing Approach
----------------

### Test delta: updated tests

| Test | Change |
|------|--------|
| `TestFetchConfigAndSlots` | Rewrite to use `httpx` mock responses instead of Playwright page mocks |
| `TestSearchAndFetch` | Mock `session.get_httpx_client()` and use `httpx` response mocks |
| Existing scraper unit tests | Remove `_common_mocks` with Playwright mocks; replace with `resp.text` / `resp.json` mocks |

### Mocking httpx

```python
mock_resp = Mock()
mock_resp.text = "<html>...</html>"
mock_resp.json = lambda: {"availabilities": [...]}
mock_resp.raise_for_status = lambda: None
```

Documentation Approach
----------------------

### Docs delta: none

Internal architecture change, no user-facing behavior changes.

Progress Checklist
------------------

- [ ] Phase 1: Add `httpx` dependency and `get_httpx_client()` to `BrowserSession`
- [ ] Phase 2: Add `HttpScraper` class with `fetch_html`, `fetch_list_csrf`, `search`, `fetch_config_and_slots`
- [ ] Phase 3: Update `search_and_fetch` to use `HttpScraper`
- [ ] Phase 4: Update tests for httpx-based mocking
- [ ] Phase 5: Full test suite + live timing verification

## Phases

### Phase 1: httpx dependency + cookie client

**Files:** `pyproject.toml`, `src/nextrec/browser.py`

- Add `httpx>=0.27` to dependencies
- Add `get_httpx_client()` to `BrowserSession` that extracts cookies from the Playwright context and returns an `httpx.AsyncClient`

### Phase 2: `HttpScraper` class

**Files:** `src/nextrec/scrapers/perfectmind.py`

- New `HttpScraper` class with same config cache + list CSRF pattern
- Methods: `fetch_html`, `fetch_list_csrf`, `search`, `fetch_config_and_slots`
- Parsing methods reuse existing static helpers (`_parse_date_microsoft`, `_parse_slots_response`, `_resolve_duration`, `_group_slots`, `_parse_facilities`)
- New HTML parsing: `_extract_csrf_from_html(text)` (regex-based), `_extract_services_json_from_html(text)` (same character-scanning logic as current)

### Phase 3: Wire into search pipeline

**Files:** `src/nextrec/search.py`

- `search_and_fetch` creates an httpx client via `session.get_httpx_client()`
- Creates an `HttpScraper` instead of `PerfectMindScraper`
- Preloads CSRF via `HttpScraper.fetch_list_csrf()`
- Passes the same http client and config cache to all keyword sub-scrapers

### Phase 4: Update tests

**Files:** `tests/unit/nextrec/scrapers/test_perfectmind.py`, `tests/unit/nextrec/test_search.py`

- Replace Playwright page mocks with httpx response mocks
- Test `HttpScraper` with fake HTML responses

### Phase 5: Verification

- `pytest tests/ -v` — all tests pass
- Live: `nextrec tui -c pickleball.yml --start-date 7/25 --end-date 7/26 --duration 90`
- Target: under 4s (down from ~10.4s)

## Execution Order

Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

## Implementation Notes

- No implementation notes yet.

## Risks and Mitigations

- **Risk**: The server might require specific headers or cookies that httpx doesn't send. **Mitigation**: Copy `user-agent`, `origin`, and `referer` headers from the current Playwright requests.
- **Risk**: Server CSRF tokens might be tied to specific page loads (now we load pages via GET instead of Playwright navigation). **Mitigation**: Already proven to work — the list-page CSRF works for availability POSTs.
- **Risk**: The services JSON extraction from HTML via character scanning (`_extract_services_json`) might work differently with httpx HTML (different encoding, whitespace, etc.). **Mitigation**: Same static HTML is returned; httpx just delivers it faster.
- **Risk**: Login session cookies might expire or not transfer properly to httpx. **Mitigation**: Cookies are extracted from the Playwright context immediately after login; if they expire, the user would re-authenticate (same as now).

## Acceptance Criteria

1. `httpx.get()` replaces `page.goto()` for config extraction and CSRF parsing
2. All searches and slot fetches succeed against the live site
3. Search wall-clock time for 2 keywords / 4 facilities drops from ~10.4s to under 4s
4. All existing unit tests pass
5. No change to the TUI or CLI user experience
