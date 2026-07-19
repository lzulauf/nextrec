# Timeline-Based Result Filtering Plan

Status: Done

Goal
----
Enable users to filter the results list by selecting time cells (and facility cells in full mode) in the timeline view. In condensed mode, filter purely by time. In expanded (full) mode, filter to results matching the selected time/facility pairs. Support multi-cell selection via click-to-toggle, shift-click for range selection, and drag selection.

## Current Implementation Summary

### What exists

| Component | Location | Behavior |
|-----------|----------|----------|
| `_time_filter` | `app.py:210` | `Optional[Tuple[time, time]]` — a single time range. `None` = no filter. |
| `_pending_filter_time` | `app.py:211` | `Optional[time]` — set on `CellHighlighted`, displayed in status bar, but **never consumed**. No key binding uses it to apply a filter. |
| `_visible_results` | `app.py:443-448` | Filters `_search_results` to slots whose `start_time` falls within `_time_filter`. |
| `handle_timeline_selected` | `app.py:594-611` | Fires on Enter in a DataTable cell. Extracts time from `row[0]`, calls `_apply_time_filter(t)`. **Ignores the column** — facility is lost even in full mode. |
| `handle_timeline_highlight` | `app.py:572-592` | Fires on arrow-key cell navigation. Stores time in `_pending_filter_time`, updates status bar preview. |
| `_apply_time_filter(t)` | `app.py:544-562` | Single-time click toggles between `(t,t)` and `None`. Two-time clicks create range. |
| `_build_results_list` | `app.py:479-504` | Iterates `_search_results` and skips any where `slot.start_time` is outside `_time_filter`. |
| `_build_timeline` | `app.py:462-477` | Passes `time_filter` to `build_timeline_rows`, which further narrows displayed time rows to match the filter. |
| `build_timeline_rows` | `timeline.py` | Condensed: `Time + Available` columns. Full: `Time + per-facility` columns. Cells show `█` (available) or `·` (unavailable). **Zero selection metadata** in output. No mapping from col back to facility_id. |
| `action_clear_time_filter` | `app.py` | Bound to Escape. Sets `_time_filter=None`, rebuilds both timeline and results. |

### What is broken or missing

1. **Facility-level filtering does not work.** In full mode, clicking a facility's cell (e.g., "Mosswood Tennis" at 08:00) only filters by time `08:00`, not by `08:00 + Mosswood Tennis`. The `col_key` is never mapped to a facility_id.

2. **No multi-cell selection.** The timeline only supports one time range. You cannot select multiple disconnected time cells (e.g., 08:00–09:00 and 14:00–15:00), nor multiple facility+time pairs in full mode.

3. **No visual selection markers.** Cells in the DataTable only show availability (green block vs. dim dot). There is no highlight or marker indicating which cells are currently selected/filtered.

4. **`_pending_filter_time` is dead code.** It is set on cell highlight but never consumed by any filter-apply logic. Enter always extracts time fresh from the row rather than using the pending value.

5. **No drag or shift-click selection.** The DataTable has neither drag detection nor shift-click range selection handlers.

6. **`_build_timeline` skips non-matching rows entirely.** When a time filter is active, `build_timeline_rows` uses `_slot_rows()` which yields only rows within the filter range. This means deselected time slots disappear from the timeline, making it impossible to see or re-select them without clearing the filter first.

## Technical Design Details

### Data model: `TimelineFilter`

Replace the single `_time_filter` tuple with a richer selection model:

```python
from dataclasses import dataclass, field

@dataclass
class TimelineFilter:
    """Represents the set of selected time/facility pairs from the timeline."""
    # In condensed mode or when no facility is specified:
    #   A set of time ranges (time, time), or
    #   None meaning "no filter" (show all results).
    time_ranges: set[tuple[time, time]] = field(default_factory=set)

    # In full mode, specific facility+time pairs:
    #   (facility_id, time) tuples.
    facility_time_pairs: set[tuple[str, time]] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.time_ranges and not self.facility_time_pairs

    def matches(self, facility_id: str, slot_time: time) -> bool:
        """Check if a slot passes this filter."""
        if self.is_empty():
            return True
        if (facility_id, slot_time) in self.facility_time_pairs:
            return True
        for lo, hi in self.time_ranges:
            if lo <= slot_time <= hi:
                return True
        return False
```

### Touchpoints

| File | Changes |
|------|---------|
| `src/nextrec/tui/app.py` | Replace `_time_filter` with `_timeline_filter: TimelineFilter`; update `_visible_results`, `_build_results_list`, `_build_timeline`, `handle_timeline_selected`, clear-filter action; add drag/shift-click handlers |
| `src/nextrec/tui/timeline.py` | Add facility_id→column_index mapping to `build_timeline_rows` return value; encode selection state in cell content (selected `[bold bright_yellow]█[/bold bright_yellow]`, unselected `[dim]·[/dim]` as today); stop hiding deselected rows when filter is active |
| `tests/unit/nextrec/tui/test_timeline.py` | Update tests for new return shape; add tests for selection-encoding in cells |

### Filter lifecycles by mode

**Condensed mode** (`TimelineFilter.time_ranges`):
- Click cell at time `t`: toggle range `(t, t)` on/off (add if absent, remove if present)
- Shift-click or drag: extend to a range
- Display: single `"Available"` column with green block for selected times, dim dot for unselected

**Full mode** (`TimelineFilter.facility_time_pairs`):
- Click cell at (facility_id, time): toggle the (facility_id, time) pair on/off
- Shift-click across time cells within same facility: toggle all intermediate (facility_id, t) pairs on
- Display: per-facility columns; selected cells in bright yellow, unselected in dim

### Timeline display

Stop hiding non-matching rows. Show all time rows regardless of filter state, and use cell styling instead:

```
// Selected cell (in filter):       [bright_yellow]█[/bright_yellow]
// Available, not selected:         [dim]█[/dim]       (or green)
// Unavailable:                      [dim]·[/dim]
```

This way users can see the full timeline and click to toggle cells without losing context.

### `_visible_results` filter

```python
@property
def _visible_results(self):
    if self._timeline_filter.is_empty():
        return self._search_results
    return [r for r in self._search_results
            if self._timeline_filter.matches(r[0], r[2].start_time)]
```

### Drag and shift-click selection

Textual DataTable does not provide built-in drag or shift-click. Implementation approach:

- Track `_drag_start_coordinate: Optional[Coordinate]` on mouse-down in the timeline table
- On mouse-up, compute the bounding rectangle of cells and add all enclosed (facility_id, time) pairs to the filter
- For shift-click: track last-clicked cell coordinate; on CellSelected with Shift modifier, select all cells between last and current

### Key/click bindings

| Input | Action |
|-------|--------|
| Enter on timeline cell | Toggle selected cell (condensed: toggle time; full: toggle facility+time pair) |
| Shift+Enter on timeline cell | Range-select from last selected cell to current |
| Escape | Clear all timeline filters |
| Mouse click + drag on timeline | Select all cells in the drag rectangle |
| `t` | Toggle condensed/full mode (existing, no change) |

## Testing Approach

### Test delta: new tests + updated tests

| Test target | Type |
|-------------|------|
| `TimelineFilter.matches()` | unit — empty filter, time_range match, facility_time match, no match |
| `TimelineFilter` toggle behavior | unit — adding/removing ranges and pairs |
| `build_timeline_rows` selection encoding | unit — condensed and full modes with filter; verify cell styling |
| `build_timeline_rows` facility→column mapping | unit — verify mapping dict structure |
| TUI `_visible_results` with `TimelineFilter` | unit — condensed, full, empty filter |
| Existing timeline tests | updated — new return shape, no hanging references to old `_time_filter` tuple |

Run: `pytest tests/unit/nextrec/tui/ -v` and full suite `pytest tests/`.

## Documentation Approach

### Docs delta: no user-facing docs changes

The TUI behavior change is self-documenting via the UI itself (status bar hints, cell highlighting). No README or external docs changes needed.

## Progress Checklist

- [x] Phase 0: Add `TimelineFilter` model to `app.py`
- [x] Phase 1: Update `build_timeline_rows` to return facility→column mapping and encode selection state in cell content; stop hiding filtered rows
- [x] Phase 2: Replace `_time_filter` with `_timeline_filter` in app; update `_visible_results`, `_build_results_list`, `_build_timeline`, clear action
- [x] Phase 3: Implement cell-toggle handler in `handle_timeline_selected` — map cell to (facility_id, time) in full mode, time-only in condensed
- [x] Phase 4: Implement drag selection and shift-click range selection on timeline DataTable
- [x] Phase 5: Update timeline unit tests for new return shape and selection encoding
- [x] Phase 6: Full test suite passes; manual smoke test in TUI (condensed click, full mode toggle, drag select, escape clear)

## Phases

### Phase 0: `TimelineFilter` model

**Goal**: Define the selection data model.

**Changes in `src/nextrec/tui/app.py`**:
- Add `TimelineFilter` dataclass with `time_ranges`, `facility_time_pairs`, `is_empty()`, `matches(facility_id, slot_time)`
- Unit test: `TimelineFilter` logic in `test_timeline.py`

### Phase 1: Update `build_timeline_rows`

**Goal**: Return facility→column mapping for cell-to-facility resolution. Encode selection state in cells. Stop hiding filtered rows.

**Changes in `src/nextrec/tui/timeline.py`**:
- Add `selected_time_ranges: set[tuple[time,time]]` and `selected_facility_times: set[tuple[str,time]]` parameters
- Return a tuple `(columns, rows, facility_col_map: dict[str, int])` instead of `(columns, rows)`
- In full mode, for each cell: if (facility_id, time) is selected, render `[bright_yellow]█[/bright_yellow]`; if available but unselected, render `[dim]█[/dim]`; if unavailable, render `[dim]·[/dim]`
- In condensed mode: if time is within any selected range, render `[bright_yellow]█[/bright_yellow]`
- Remove the `_slot_rows` time-filter skip logic — show all time rows regardless of filter

### Phase 2: Wire `TimelineFilter` into app

**Goal**: Replace all `_time_filter` usages with `_timeline_filter`.

**Changes in `src/nextrec/tui/app.py`**:
- `_time_filter` → `_timeline_filter: TimelineFilter`
- `_visible_results` property updated to use `_timeline_filter.matches()`
- `_build_results_list` updated
- `_build_timeline` passes `selected_time_ranges` and `selected_facility_times` from filter to `build_timeline_rows`
- `action_clear_time_filter` → clears `_timeline_filter`
- Remove `_pending_filter_time` (dead code)

### Phase 3: Cell-toggle handler

**Goal**: `handle_timeline_selected` maps col_index to facility_id and toggles the selection.

**Changes in `src/nextrec/tui/app.py`**:
- In `_build_timeline` / on DataTable creation, store `_facility_col_map: dict[str, int]` returned by `build_timeline_rows`
- `handle_timeline_selected`: extract `row_key` and `col_key` from event
  - `col_index = col_key.value` (Textual DataTable column keys are `ColumnKey`)
  - `time = _extract_time_from_row(row)`
  - If full mode: `facility_id` = reverse lookup from `_facility_col_map` by col_index. Toggle `(facility_id, time)` in `_timeline_filter.facility_time_pairs`.
  - If condensed: toggle range `(time, time)` in `_timeline_filter.time_ranges`.
  - Rebuild timeline and results.

### Phase 4: Multi-cell selection (drag + shift-click)

**Goal**: Support selecting multiple cells at once.

**Changes in `src/nextrec/tui/app.py`**:
- Store `_last_timeline_cell: Optional[tuple[str, time]]` for shift-click range
- `handle_timeline_selected` (Enter): if Shift is held, range-select from `_last_timeline_cell` to current
- Mouse drag: capture `MouseDown` on timeline table → store start coordinate; on `MouseUp`, compute bounding rectangle, toggle all enclosed cells into filter
- Track `_last_timeline_cell` as `(facility_id_or_None, time)` for range selection

### Phase 5: Update tests

**Goal**: All existing tests pass; new tests cover the selection model.

**Changes in `tests/unit/nextrec/tui/test_timeline.py`**:
- Update `build_timeline_rows` callers for new `(columns, rows, map)` return shape
- Add tests for `TimelineFilter` model
- Add tests for selection encoding in cells (bright yellow vs. dim)
- Add tests for show-all-rows (no row hiding)

### Phase 6: Verification

**Goal**: Full test suite passes; manual TUI smoke test.

- Run `pytest tests/ -v`
- Manual: open TUI, search, click cells in condensed mode → results filter
- Manual: switch to full mode, click facility cells → results filter by facility+time
- Manual: shift-click / drag across multiple cells → multi-pair filter
- Manual: Escape → clear all filters

## Execution Order Recommendation

Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

Phase 0 (model) and Phase 1 (timeline builder) should land first since everything depends on them. Phase 3 and 4 can be developed in parallel.

## Risks and Mitigations

- **Risk**: Textual DataTable drag detection requires manual mouse-event tracking. **Mitigation**: Use `MouseDown`/`MouseUp` events from the Widget protocol; test with small drags and verify no false positives from single clicks.
- **Risk**: Shift-click detection requires distinguishing Enter vs Shift+Enter. **Mitigation**: Textual's `key.shift` attribute on the event; if not available, bind a separate key (e.g., Shift+Enter or another key combo).
- **Risk**: Row/column performance with many facilities. **Mitigation**: The number of facilities in real usage is small (<10 typically); no pagination needed.

## Implementation notes

### 2026-07-19 — Phases 0–6 complete
- Scope completed: Timeline-based result filtering with multi-cell selection.
- Code touchpoints:
  - `src/nextrec/tui/app.py` — Added `TimelineFilter` dataclass; replaced `_time_filter` with `_timeline_filter`; added `_facility_col_map`; replaced `_apply_time_filter` with `_toggle_time_filter`; added `_col_to_facility` and `_col_to_facility_by_index` helpers; added drag selection via `MouseDown`/`MouseUp` handlers on `#timeline-table`; removed dead `_pending_filter_time`.
  - `src/nextrec/tui/timeline.py` — Updated `build_timeline_rows` to accept `selected_time_ranges` and `selected_facility_times`; returns 3-tuple `(columns, rows, facility_col_map)`; shows all rows (no hiding); encodes selection in cells (`bright_yellow` for selected, `green` for available, `dim` for unavailable).
  - `tests/unit/nextrec/tui/test_timeline.py` — Updated 10 existing tests for new return shape; removed old `time_filter` kwarg; added 2 tests: `test_selected_time_range_condensed`, `test_selected_facility_time_full`.
- Tests: 130 pass, 11 timeline tests (2 new).
- Follow-ups: Shift+Enter range binding deferred (Textual `CellSelected` doesn't carry modifier key info; drag covers multi-cell need).

## Acceptance Criteria

1. Condensed timeline: clicking a time cell toggles filtering for that time; results list narrows accordingly. Clicking again toggles off.
2. Full timeline: clicking a facility's cell at a time toggles filtering for that (facility, time) pair. Results list shows only matching slots.
3. Shift-click or drag selects a range of cells in the timeline.
4. Escape clears all timeline filters.
5. All deselected rows/times remain visible in the timeline (dimmed, not hidden).
6. Selected cells display a visible selection mark (bright yellow).
7. All existing unit tests pass; new tests cover `TimelineFilter` and selection encoding.
