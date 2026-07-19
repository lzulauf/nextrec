# Adjacent Slot Merge Decision

## Problem statement

When a user searches for 90-min slots and selects two adjacent results (e.g., 9:00-10:30 + 10:30-12:00), each opens its own checkout tab. The user must check out twice. Is it possible/practical to merge them into a single 180-min checkout?

## Why this matters now

The multi-checkout (Approach C) was just implemented. Before users test it, we should decide whether to also support automatic merging of adjacent selections so the multi-tab case is minimized.

## Goals and decision criteria

**Goals:**
- Reduce the number of checkout tabs the user must handle
- Only merge when PerfectMind supports the combined duration
- Don't break the existing single-slot/grouped-slot flow

**Decision criteria:**
- **Implementation effort** — how many files/modules change
- **Reliability** — can we correctly detect mergeable slots?
- **Maintainability** — does the merge logic add complexity?
- **Coverage** — does it handle edge cases (partial overlap, gaps, different facilities)?

## Constraints and assumptions

- `TimeSlot.base_slot_ticks` records the individual base-slots that make up a grouped result.
- `FacilityConfig.duration_prices` lists all supported durations.
- Adjacency means `slotB.ticks == slotA.ticks + slotA.duration_ticks`.
- The combined duration must have a matching `DurationPrice` (or be resolvable via `_resolve_duration`).
- The merge only applies within the same facility.
- The merge only applies to same-date slots.

## Options considered

### Option 1: Do nothing

Keep the current Approach C — one tab per selected result, regardless of adjacency.

**What this means**: If the user selects 2 adjacent 90-min results, they get 2 tabs.

**Criteria impact:**
- Implementation effort: None
- Reliability: N/A
- Maintainability: None
- Coverage: Full — works for all selection combinations

**Pros:**
- Zero implementation cost
- Works correctly in all cases
- User just closes tabs after each checkout

**Cons:**
- More tabs for adjacent selections
- User completes checkout N times instead of once

### Option 2: Merge adjacent selections before booking

Analyze the selected slots before calling `add_to_cart`. If two adjacent slots for the same facility have a combined duration that's in `duration_prices`, merge them into a single `TimeSlot` with extended `base_slot_ticks`.

**What this means**: A merge function runs between selection and booking:

```
Selected: [90-min@9:00, 90-min@10:30] → Merge → [180-min@9:00]
```

The merged slot has `duration_minutes=180`, `base_slot_ticks=[300, 330, 360, 390, 420, 450]`.

`add_to_cart` then calls `_book_single` 6 times with 30-min duration — same as it would for a native 180-min grouped slot.

The checkout URL uses the merged slot: `startDateTimeTicks=300&duration=180`.

```python
def merge_adjacent_slots(
    items: List[Tuple[str, FacilityConfig, TimeSlot]]
) -> List[Tuple[str, FacilityConfig, TimeSlot]]:
    """Merge adjacent slots for the same facility when the combined duration is supported."""
    by_facility = defaultdict(list)
    for fid, cfg, slot in items:
        by_facility[fid].append((cfg, slot))

    result = []
    for fid, entries in by_facility.items():
        cfg = entries[0][0]
        sorted_entries = sorted(entries, key=lambda x: x[2].ticks)
        available_minutes = {dp.minutes for dp in cfg.duration_prices}

        i = 0
        while i < len(sorted_entries):
            entry_cfg, current = sorted_entries[i]

            # Try to extend forward with adjacent entries
            merged_base_ticks = list(current.base_slot_ticks or [current.ticks])
            j = i + 1
            while j < len(sorted_entries):
                _, candidate = sorted_entries[j]
                expected_ticks = merged_base_ticks[-1] + (current.duration_ticks // len(merged_base_ticks))
                if candidate.ticks != expected_ticks:
                    break
                candidate_base = candidate.base_slot_ticks or [candidate.ticks]
                combined_minutes = (len(merged_base_ticks) + len(candidate_base)) * (current.duration_minutes // len([current.base_slot_ticks or [current.ticks]]))
                # Hmm this gets complex...

                # Simpler: compute combined duration
                base_minutes = current.duration_minutes // (len(current.base_slot_ticks) if current.base_slot_ticks else 1)
                total_base_slots = len(merged_base_ticks) + len(candidate_base)
                combined_minutes = total_base_slots * base_minutes

                if combined_minutes not in available_minutes:
                    break
                merged_base_ticks.extend(candidate_base)
                j += 1

            if j > i + 1:
                # Merge happened
                from datetime import timedelta
                from nextrec.scrapers.perfectmind import minutes_to_ticks, _DOTNET_EPOCH
                base_tick_dur = current.duration_ticks // len(current.base_slot_ticks)
                merged_dur_ticks = len(merged_base_ticks) * base_tick_dur
                merged_minutes = len(merged_base_ticks) * (current.duration_minutes // (len(current.base_slot_ticks) if current.base_slot_ticks else 1))
                end_dt = _DOTNET_EPOCH + timedelta(seconds=merged_dur_ticks / 10_000_000)
                merged = TimeSlot(
                    date=current.date,
                    start_time=current.start_time,
                    end_time=end_dt.time(),
                    ticks=current.ticks,
                    duration_minutes=merged_minutes,
                    duration_ticks=merged_dur_ticks,
                    is_disabled=False,
                    base_slot_ticks=merged_base_ticks,
                )
                result.append((fid, entry_cfg, merged))
                i = j
            else:
                result.append((fid, entry_cfg, current))
                i += 1

    return result
```

**Criteria impact:**
- Implementation effort: Medium — ~50 lines of merge logic + tests
- Reliability: Medium — edge cases with non-uniform `base_slot_ticks`
- Maintainability: Medium — merge logic is self-contained but has edge cases
- Coverage: Limited — only works if combined duration is in `duration_prices`

**Pros:**
- Fewer checkout tabs (better UX for adjacent selections)
- Reuses existing `add_to_cart` and `_book_single` — no cart API changes
- Merged result is indistinguishable from a native longer slot

**Cons:**
- Only works when the combined duration is in `duration_prices`
- Edge cases: what if 3 adjacent 90-min slots exist? 270 min might not be in `duration_prices`, so we'd merge 2 and leave 1
- What about overlapping base_slot_ticks? (a 90-min group starting at 9:00 and one starting at 9:30 overlap — they share the 9:30 tick)
- Adds complexity to the booking pipeline
- The `_booking_key` dedup logic could break if a previously-booked merged key conflicts

### Option 3: Merge at the scraper level (wider grouping)

Instead of merging user-selected results after the fact, modify `_group_slots` to also produce larger groupings (e.g., 180-min) so they appear as single selectable results. The user would pick the 180-min result directly instead of two 90-min results.

**What this means**: `_group_slots` creates slots for ALL supported duration multiples:
- If `duration_prices` has 30, 60, 90, 180 and user requests 90 min
- Produce 90-min and 180-min slots
- User sees and selects the 180-min slot directly

**Criteria impact:**
- Implementation effort: Medium-High — affects scraper, search results, timeline display
- Reliability: High — works within existing grouping logic
- Maintainability: Medium — changes propagate to display

**Pros:**
- Cleanest user experience — pick the exact duration you want
- Works inside existing grouping framework
- No post-hoc merge logic needed

**Cons:**
- More results cluttering the timeline/results list
- User might not know to look for the longer duration
- Would need to update TUI display to show variable-duration results
- User might prefer two 90-min bookings (separate purposes) over one 180-min

## Tradeoff analysis

| Criterion | Option 1 (Do nothing) | Option 2 (Merge after selection) | Option 3 (Wider grouping) |
|-----------|----------------------|----------------------------------|---------------------------|
| Implementation effort | **None** | Medium | Medium-High |
| Reliability | **High** | Medium | High |
| Maintainability | **High** | Medium | Medium |
| Edge case coverage | **All** | Limited | Limited |

## Recommendation

**Option 1 (Do nothing) for now.** Let the user test the current Approach C (multi-tab) in practice. Reasons:

1. It's not clear that merging is a common need — users may rarely select adjacent results.
2. The merge logic has edge cases (overlapping base_slot_ticks from sliding-window grouping, combined duration not in `duration_prices`, mixed facilities) that need careful handling.
3. If multi-tab checkout works well in practice, the merge provides marginal UX improvement at non-trivial complexity cost.
4. The merge can be added later as a follow-up if users request it.

If users consistently request it, **Option 2** is the better implementation path — it sits cleanly between selection and booking without affecting search/scraper logic.

## Confidence and risks

Confidence: High that "do nothing" is correct for now. The multi-tab flow works correctly; merging is a polish optimization, not a correctness fix.

Risk: If users frequently book adjacent multi-hour blocks, the extra tabs will be annoying. Acceptable risk — easy to add later.

## Follow-up actions

1. Ship current Approach C (multi-tab) as-is.
2. Gather user feedback on whether adjacent-slot merging would be valuable.
3. If needed, implement Option 2 as a follow-up.
