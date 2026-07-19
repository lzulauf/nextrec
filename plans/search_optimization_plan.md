# Search Optimization Plan

Status: Drafting

Goal
----
Reduce wall-clock time from "click Search" to "results shown" from ~10-15s to ~3-5s for typical workloads (2-3 keywords, 3-5 facilities).

Why this comes first
--------------------
Search latency is the primary UX pain point. Users wait 10-15 seconds before seeing any results. The fixes are low-risk (no behavior change, just eliminating redundant network calls) and deliver a ~2-3x speedup.

Scope
-----
- Merge `fetch_config` + `fetch_slots` into a single `fetch_config_and_slots` method that navigates the facility detail page once, extracts both config and CSRF token, and POSTs for availability all within one page context
- Share the facility list page CSRF token across all keyword searches (load once, reuse)
- Add in-memory facility config cache so repeated lookups for the same facility are instant
- Keep public API (`search_and_fetch`, `Constraint`, `SlotInfo`) unchanged

Out of scope
-----------
- Request-level caching with disk persistence
- Changing the Semaphore limits
- Pre-fetching or speculative fetching
- Changing the TUI or CLI user experience
- Network-level optimizations (HTTP/2, keep-alive tuning)

Technical Design Details
------------------------

### Current flow (per keyword)

```
for each keyword:
    page.goto(FACILITY_LIST_URL)          # ~1s  — page load + CSRF extract
    POST GetFacilities                    # ~200ms
    for each facility:
        page.goto(FACILITY_DETAIL_URL)    # ~1s  — config page
        extract config JSON               # ~50ms
        page.goto(FACILITY_DETAIL_URL)    # ~1s  — **DUPLICATE page load**
        extract CSRF token                # ~50ms
        POST FacilityAvailability         # ~200ms
```

**Per facility: ~2.3s (two page loads + two non-page ops)**
**Per keyword: ~1.2s + N * 2.3s serial within keyword**
**Overall: parallel across keywords, capped at 3 parallel CSRF loads + 4 parallel facility loads**

### Optimized flow

```
# One-time
page.goto(FACILITY_LIST_URL)             # ~1s  — load once, extract CSRF
CSRF = extract_csrf(page)

for each keyword (all in parallel, share CSRF):
    POST GetFacilities                   # ~200ms
    for each facility (all in parallel):
        if facility_id in config_cache:
            config = config_cache[fid]     # ~0s
        else:
            page.goto(FACILITY_DETAIL_URL)  # ~1s  — load once
            config = extract_config(page)   # ~50ms
            config_cache[fid] = config
            csrf_detail = extract_csrf(page)  # ~50ms
        POST FacilityAvailability         # ~200ms
```

**Per facility: ~1s (one page load, cached-on-revisit) + ~250ms ops**
**Total: ~1s (shared CSRF) + ~200ms (keyword POSTs) + max(4 facilities/parallel batch) * ~1.25s ≈ ~3s**

~3x speedup.

### Touchpoints

| File | Changes |
|------|---------|
| `src/nextrec/scrapers/perfectmind.py` | Add `fetch_config_and_slots(facility_id, ...)` method combining `fetch_config` + `fetch_slots`; add `_config_cache: dict[str, FacilityConfig]` to `PerfectMindScraper`; add `get_list_csrf()` method to load list page once and return token |
| `src/nextrec/search.py` | Update `pipeline_one()` to call `fetch_config_and_slots` instead of two separate calls; extract CSRF once before launching keyword pipelines |

### Method signatures

```python
class PerfectMindScraper:
    _config_cache: dict[str, FacilityConfig]  # per-instance, in-memory

    async def fetch_list_csrf(self) -> str:
        """Load facility list page once, return CSRF token. Cached per instance."""
        ...

    async def fetch_config_and_slots(
        self,
        facility_id: str,
        start_date: date,
        days_count: int,
        duration_minutes: int,
        end_date: Optional[date] = None,
        time_window_start: Optional[time] = None,
        time_window_end: Optional[time] = None,
    ) -> Tuple[FacilityConfig, List[TimeSlot]]:
        """Navigate facility page once, extract config + CSRF, POST availability.
        Uses config_cache for repeat lookups."""
        ...
```

### Error handling

- `fetch_config_and_slots` wraps the page navigation + config extraction + availability POST in one `try/except ScrapeError`
- If config is cached but the availability POST fails, raise `ScrapeError` as before
- Config cache entries are evicted on exception (stale cache protection)
- CSRF token reuse: if the list page CSRF expires mid-search, the POST will get a 400. We don't add retry logic — the existing error handling propagates it

## Testing Approach

### Test delta: updated tests

Scraper tests need updates:

| Test | Change |
|------|--------|
| `TestFetchConfig` + `TestFetchSlots` | Merge into `TestFetchConfigAndSlots` — verifies one page navigation, both config and slots returned |
| Config cache test (new) | Cached config returned without second navigation; cache evicted on error |
| CSRF sharing test (new) | `fetch_list_csrf` called once, reused across `search()` calls |
| `TestSearchAndFetch` in `test_search.py` | Updated mocks for new method name; verify CSRF shared across keywords |

Run: `pytest tests/ -v`

## Documentation Approach

### Docs delta: none

Internal refactoring — the public API (`search_and_fetch`) is unchanged. No user-facing behavior changes.

## Progress Checklist

- [ ] Phase 1: Add `fetch_config_and_slots` to `PerfectMindScraper` — one navigation, config extraction, CSRF extraction, availability POST
- [ ] Phase 2: Add config cache to `PerfectMindScraper` — in-memory `_config_cache` dict
- [ ] Phase 3: Add `fetch_list_csrf` to `PerfectMindScraper` — load list page once, cache token
- [ ] Phase 4: Update `search_and_fetch` to use merged method + shared CSRF
- [ ] Phase 5: Update scraper tests for merged method and cache
- [ ] Phase 6: Full test suite passes; live smoke test verifies speed improvement

## Phases

### Phase 1: `fetch_config_and_slots`

**Files:** `src/nextrec/scrapers/perfectmind.py`

Implement a new method that combines the current `fetch_config` and `fetch_slots` into one page navigation:

```python
async def fetch_config_and_slots(self, facility_id, start_date, ...):
    url = f"{FACILITY_DETAIL_URL}?facilityId={facility_id}"
    page = await self._browser_session.manager.new_page()
    await page.goto(url, wait_until="networkidle")
    
    # Extract config (services JSON from page content)
    config = self._extract_services_config(page)
    
    # Extract CSRF from the same page
    csrf = await self._extract_csrf(page)
    
    # POST availability
    slots = await self._fetch_slots_inner(page, csrf, facility_id, config, start_date, ...)
    
    return config, slots
```

Keep the existing `fetch_config` and `fetch_slots` methods for now (deprecated, will be removed in cleanup phase).

### Phase 2: Config cache

**Files:** `src/nextrec/scrapers/perfectmind.py`

Add `_config_cache: dict[str, FacilityConfig]` to `PerfectMindScraper.__init__`.

In `fetch_config_and_slots`:
- Check cache before navigating
- On success, store in cache
- On `ScrapeError`, remove stale entry from cache

### Phase 3: Shared CSRF for list page

**Files:** `src/nextrec/scrapers/perfectmind.py`

Add `_list_csrf: Optional[str]` to `PerfectMindScraper`.

Add `fetch_list_csrf()` method: loads `FACILITY_LIST_URL` once, extracts CSRF token, stores it. Returns cached token on subsequent calls.

Update `search()` to use `fetch_list_csrf()` instead of internal page load. If `_list_csrf` is not set, call `fetch_list_csrf()` first.

### Phase 4: Update `search_and_fetch`

**Files:** `src/nextrec/search.py`

- Before launching keyword pipelines, call `scraper.fetch_list_csrf()` once to preload the shared CSRF token
- Replace `fetch_config(f.id)` + `fetch_slots(f.id, ...)` with `fetch_config_and_slots(f.id, ...)` in `fetch_facility`
- Remove per-keyword scraper creation within `fetch_facility` (scraper is shared per keyword)

### Phase 5: Update tests

**Files:** `tests/unit/nextrec/scrapers/test_perfectmind.py`, `tests/unit/nextrec/test_search.py`

- Merge `TestFetchConfig` and `TestFetchSlots` into `TestFetchConfigAndSlots`
- Add config cache test
- Add CSRF sharing test
- Update `TestSearchAndFetch` mocks

### Phase 6: Verification

- `pytest tests/ -v` — all tests pass
- Live smoke test: `nextrec tui -c pickleball.yml --start-date 7/25 --end-date 7/26 --duration 90`
- Verify wall-clock time from Enter to results is ~3-5s (down from ~10-15s)

## Execution Order Recommendation

Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

Phases 1-3 are the scraper refactors. Phase 4 wires them into the search pipeline. Phase 5 updates tests. Phase 6 verifies.

## Implementation Notes

- No implementation notes yet.

## Risks and Mitigations

- **Risk**: CSRF token expires between list-page load and keyword POSTs. **Mitigation**: CSRF tokens on PerfectMind are session-scoped (valid for the browser context), not request-scoped. If a 400 occurs, the existing error handling propagates it.
- **Risk**: Config cache holds stale data if facility config changes mid-session. **Mitigation**: Facility configs (service IDs, calendar IDs, prices) are stable — they don't change within a user session. If a ScrapeError occurs for a cached facility, the cache entry is evicted.
- **Risk**: Merged `fetch_config_and_slots` has a larger method surface area, making it harder to test. **Mitigation**: Keep helper methods (`_extract_services_config`, `_extract_csrf`, `_fetch_slots_inner`) as separate testable units.

## Acceptance Criteria

1. `fetch_config_and_slots(facility_id, ...)` navigates the facility page once and returns both config and slots
2. Config cache prevents repeat page loads for the same facility within a session
3. CSRF token from facility list page is loaded once and shared across all keyword searches
4. Live search time for 2 keywords producing 4 facilities is under 5 seconds (was ~10-15s)
5. All existing tests pass (or are updated)
6. No change to the public `search_and_fetch` API signature
