# Plan: Parallelized Search Pipeline

## Status

Implementing

## Goal

Speed up searches by pipelining keyword searches and facility config/slot fetches. As soon as a keyword search returns, immediately start fetching its facilities' configs and slots — don't wait for other keyword searches to finish.

## Scope

- Replace the current two-phase sequential flow (all keyword searches → dedup → all facility fetches) with a per-keyword pipeline (search → process facilities → emit results)
- Fix the `_get_scraper` coroutine bug in `tui/app.py`
- Rate-limit concurrent browser operations with `asyncio.Semaphore`
- Remove hard dedup gate between keyword search and facility fetch — accept occasional duplicate work for overlapping keywords in exchange for lower latency
- Dedup results at the very end before display

## Out of Scope

- `asyncio.TaskGroup` (Python 3.11 has both; `gather` is simpler)
- Cross-session parallelism
- Parallelizing `CartManager.add_to_cart` or booking operations
- Changing `BrowserManager` or `BrowserSession` internals
- Replacing the `@work(exclusive=True)` guard in TUI

## Technical Design Details

### Current state (sequential two-phase)

```
keyword_1 search ──┐
keyword_2 search ──┤  wait for ALL ──► dedup ──► facility_1 fetch ──► facility_2 fetch ──► ...
keyword_3 search ──┘
```

### Target state (per-keyword pipeline)

```
keyword_1 search ──► facility fetches ──► results_1 ──┐
keyword_2 search ──► facility fetches ──► results_2 ──┤  merge ──► sort ──► display
keyword_3 search ──► facility fetches ──► results_3 ──┘
```

Each keyword's pipeline is independent. Facility fetches for keyword N start as soon as that keyword's search returns, without waiting for keywords N+1.

### Key insight

Keyword searches are fast (single POST). Facility config+slot fetches are slow (page navigation + POST). In the original plan, fast keyword searches all finish quickly, then ALL facility fetches wait until the last keyword completes. With pipelining, facility fetches for keyword 1 start while keyword 2 is still searching.

If keywords overlap (same facility returned by two keywords), that facility gets fetched twice. This is a minor cost — facilities are few (<20) and config/slot fetches are cheap — compared to the latency win of not waiting.

### New/changed APIs

**New function in `search.py`:**

```python
async def search_and_fetch(
    session: BrowserSession,
    keywords: List[str],
    base: Constraint,
    duration_minutes: int,
    days_count: int = 7,
    end_date: Optional[date] = None,
    time_window_start: Optional[time] = None,
    time_window_end: Optional[time] = None,
    max_concurrent_searches: int = 3,
    max_concurrent_fetches: int = 4,
) -> Tuple[Dict[str, str], List[SlotInfo]]:
    """Pipeline: search keywords → fetch config+slots per facility.
    
    Returns (facility_names, slot_info_list).
    Facility names is a dict of {facility_id: name}.
    Slot info is a list of (facility_id, FacilityConfig, TimeSlot) tuples.
    """
```

This replaces the call pattern:
```
facilities = search_multi(session, kw_list, constraint)
for f in facilities:
    fac_names[f.id] = f.name
    config = scraper.fetch_config(f.id)
    slots = scraper.fetch_slots(f.id, ...)
    ...
```

With a single call that does everything in parallel.

**`search_multi` can be removed** (or kept as a backwards-compat wrapper). All callers should use `search_and_fetch` instead.

### Pipeline internals

```python
async def search_and_fetch(session, keywords, base, ...):
    search_sem = asyncio.Semaphore(max_concurrent_searches)
    fetch_sem = asyncio.Semaphore(max_concurrent_fetches)

    async def pipeline_one(kw: str):
        # Phase 1: keyword search
        async with search_sem:
            c = Constraint(
                start_date=base.start_date,
                end_date=base.end_date,
                time_window_start=base.time_window_start,
                time_window_end=base.time_window_end,
                keywords=kw,
            )
            scraper = PerfectMindScraper(session)
            facilities = await scraper.search(c)

        # Phase 2: facility processing (parallel within this keyword)
        async def fetch_facility(f: Facility):
            async with fetch_sem:
                scraper = PerfectMindScraper(session)
                config = await scraper.fetch_config(f.id)
                slots = await scraper.fetch_slots(
                    f.id,
                    base.start_date or date.today(),
                    config,
                    days_count=days_count,
                    duration_minutes=duration_minutes,
                    end_date=end_date,
                    time_window_start=time_window_start,
                    time_window_end=time_window_end,
                )
                return (f.id, f.name, config, slots)

        results = await asyncio.gather(
            *[fetch_facility(f) for f in facilities],
            return_exceptions=True,
        )

        kw_results = []
        kw_names = {}
        for r in results:
            if isinstance(r, Exception):
                continue
            fid, name, config, slots = r
            kw_names[fid] = name
            for s in slots:
                if not s.is_disabled:
                    kw_results.append((fid, config, s))
        return kw_names, kw_results

    # Fire off all keyword pipelines
    task_results = await asyncio.gather(
        *[pipeline_one(kw) for kw in keywords],
        return_exceptions=True,
    )

    # Merge results
    all_names: Dict[str, str] = {}
    all_results: List[SlotInfo] = []
    seen_slots: Set[str] = set()

    for r in task_results:
        if isinstance(r, Exception):
            continue
        names, slots = r
        all_names.update(names)
        for slot_info in slots:
            fid, cfg, slot = slot_info
            # Dedup by facility_id + slot ticks
            key = f"{fid}_{slot.ticks}"
            if key not in seen_slots:
                seen_slots.add(key)
                all_results.append(slot_info)

    all_results.sort(key=lambda x: (x[2].date, x[2].start_time))
    return all_names, all_results
```

### Caller changes

**TUI `_run_search`** replaces the entire search+fetch block with:

```python
# Before:
facilities = await search_multi(session, kw_list, constraint) if kw_list else await scraper.search(constraint)
results, fac_names = [], {}
for f in facilities:
    ...
    
# After:
if kw_list:
    fac_names, results = await search_and_fetch(
        session, kw_list, constraint, duration_min,
        end_date=constraint.end_date,
        time_window_start=constraint.time_window_start,
        time_window_end=constraint.time_window_end,
    )
else:
    # Single keyword-less search — use scraper directly
    facilities = await scraper.search(constraint)
    ...existing sequential loop...
```

The single-keyword (no keyword list) case stays sequential — there's nothing to pipeline with.

**CLI `_async_book`** same change.

### `_get_scraper` fix

```python
# Bug: passes coroutine instead of BrowserSession
# self._scraper = PerfectMindScraper(self._start_session())

# Fix: await first, then pass the session
await self._start_session()
self._scraper = PerfectMindScraper(self._session)
```

### Error handling

- Failed keyword search: logs warning, other keywords continue
- Failed facility fetch: that facility is skipped, other facilities continue
- Semaphore ensures we don't flood the browser

### Semaphore values

| Semaphore | Limit | Rationale |
|-----------|-------|-----------|
| `search_sem` | 3 | Keyword searches are lightweight POSTs |
| `fetch_sem` | 4 | Facility fetches do page navigation; 4 concurrent pages is comfortable |

## Testing Approach

- Core logic isn't changing — `PerfectMindScraper.search`, `fetch_config`, `fetch_slots` are tested separately
- `search_multi` either removed or kept as thin wrapper; existing `TestSearchMulti` tests can be updated to test `search_and_fetch` instead, adjusting mock expectations for parallel execution
- TUI and CLI tests: verify the new call path (integration-level mocking)

**Test delta**: updated tests for `search_multi` → `search_and_fetch` rename and parallel mock expectations.

## Documentation Approach

**Docs delta**: none — no public API changes.

## Progress Checklist

- [x] Phase 0: Fix `_get_scraper` coroutine bug (already fixed)
- [x] Phase 1: Create `search_and_fetch` pipeline function in `search.py`
- [x] Phase 2: Update TUI `_run_search` to use `search_and_fetch`
- [x] Phase 3: Update CLI `_async_book` to use `search_and_fetch`
- [x] Phase 4: Update tests
- [x] Full test suite passes (129 tests)

## Phases

### Phase 0: Fix `_get_scraper` bug

**File**: `src/nextrec/tui/app.py`

The `_get_scraper` method passes `self._start_session()` (a coroutine) instead of the resulting `BrowserSession`. Fix by ensuring the session is started first.

### Phase 1: Create `search_and_fetch`

**File**: `src/nextrec/search.py`

New function implementing the pipeline. The existing `search` and `search_multi` functions can remain as internal helpers or be removed.

### Phase 2: TUI update

**File**: `src/nextrec/tui/app.py`

Replace the search-then-fetch loop in `_run_search` with a call to `search_and_fetch`.

### Phase 3: CLI update

**File**: `src/nextrec/cli/main.py`

Same replacement in `_async_book`.

### Phase 4: Tests

**File**: `tests/unit/nextrec/test_search.py`

Update mock assertions for parallel execution paths.

## Execution Order

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4

## Implementation Notes

### 2026-07-19 — Implemented

Changes made:
- `src/nextrec/search.py`: Replaced `search_multi` with `search_and_fetch` pipeline. Each keyword runs its own pipeline (search → fetch config+slots), and keyword pipelines run concurrently via `asyncio.gather`. Uses `asyncio.Semaphore(3)` for keyword searches and `Semaphore(4)` for facility fetches. Results are deduplicated by `(facility_id, slot.ticks)` and sorted.
- `src/nextrec/tui/app.py`: Updated `_run_search` to use `search_and_fetch` for multi-keyword searches. Single-keyword path remains sequential. Removed `search_multi` import.
- `src/nextrec/cli/main.py`: Updated `_async_book` to use `search_and_fetch` for multi-keyword searches. Single-keyword path remains sequential (with per-facility progress printing). Removed `search_multi` import.
- `tests/unit/nextrec/test_search.py`: Replaced `TestSearchMulti` with `TestSearchAndFetch` — tests for cross-keyword merging, keyword failure tolerance, and slot deduplication.
- All 129 tests pass.

## Acceptance Criteria

1. Multi-keyword search: each keyword's facility fetches start before all keywords finish searching
2. Single-keyword search: produces identical results to current behavior
3. Facility-level failures don't abort other facilities or keywords
4. Full test suite passes
5. No new `asyncio` warnings from unawaited coroutines
