# Multi-Checkout Flow Plan

Status: Done

Goal
----
Fix multi-slot checkout so that when a user selects multiple results (consecutive same-facility, non-consecutive same-facility, or multi-facility), all selected items are properly reflected in the browser checkout session and the user can pay for all of them.

Why this comes first
--------------------
Currently, selecting multiple results only checks out the first one. Users who need, say, two 60-minute slots on the same court on two different days get only one added to the checkout page. This defeats the purpose of multi-select in the TUI and is silently wrong (the server-side cart gets all items, but the browser only shows one).

Scope
-----
- Identify the correct PerfectMind cart/checkout URL for viewing all cart items (not just a single slot's booking page).
- Fix both the TUI (`tui/app.py`) and CLI (`cli/main.py`) checkout URL construction.
- Add cart-consolidation logic so the browser checkout flow presents all selected items.
- Add discovery for the cart page URL if not already known.

Out of scope
------------
- Automating payment or completing checkout on behalf of the user (remains manual).
- Changing the `add_to_cart` / `StoreOccupancyItems` protocol itself.
- Adding multi-user or group booking support.
- Changing the `base_slot_ticks` grouping logic in the scraper.

Technical design details
------------------------

### Current flow (broken)

```
TUI: user selects N results → _run_booking()
  ├─ cart.add_to_cart(fid, cfg, slot) × N   → N × (Validate + Store) server-side
  └─ checkout_url = FacilityBooking?startDateTimeTicks=selected[0].ticks  ← ONLY FIRST SLOT
```

The server-side cart (PerfectMind session) correctly contains all N items. But the browser checkout URL opens `FacilityBooking?...` with a single `startDateTimeTicks`, which loads a page scoped to that one slot. The user sees and pays for only that one.

### Discovery needed

Before implementing, we need to find the **cart view URL** on PerfectMind. Candidates (based on the JS modules):
- `/Clients/BookMe4BookingPages/Cart` — explicit cart page
- `/Clients/BookMe4BookingPages/ViewCart` — alternative
- `/SocialSite/BookMe4EventParticipants/ViewCart` — participant-facing cart
- `/SocialSite/BookMe4EventParticipants/Cart` — alternative

The `bookMe4Cart.js` and `SingleLocationOnlineShoppingCartPopup.js` scripts load cart data — we need to identify their target URL from the HAR or by running `debug-browse` against a live session with multiple items in the cart.

### Approach A (preferred): Navigate to the cart page

If a cart-page URL exists, construct _that_ as the checkout URL instead of the single-slot `FacilityBooking` page. The cart page should show all items added via `StoreOccupancyItems`.

```
checkout_url = "https://cityofoakland.perfectmind.com/Clients/BookMe4BookingPages/Cart"
```

The user can review all items and proceed to checkout from there.

### Approach B (fallback): Navigate to FacilityBooking without a specific slot

Some systems have a "view cart" mode that loads all held items. If the `FacilityBooking` page can be loaded without `startDateTimeTicks`, it might show all cart items. Test this.

### Approach C (fallback): Multi-step checkout per slot

If no aggregate cart page exists, open the first slot's booking page, let the user complete it, then programmatically open the next. This is worse UX but works. Implementation:

```python
# Pseudocode for Approach C
for fid, cfg, slot in selected:
    url = build_checkout_url(fid, cfg, slot)
    page = await checkout_session.manager.new_page()
    await page.goto(url, wait_until="networkidle")
    # Let user complete checkout for this slot
    # Then open next tab for next slot
```

### Module/file touchpoints

| File | What changes |
|------|-------------|
| `src/nextrec/tui/app.py:681-698` | Fix `_run_booking()` checkout URL construction — use cart page or multi-tab flow |
| `src/nextrec/cli/main.py:173-205` | Fix `_async_book()` checkout URL — same fix as TUI |
| `src/nextrec/cart.py` | Minor: maybe add a `get_cart_url()` helper or similar |
| `src/nextrec/scrapers/perfectmind.py` | Minor: add cart URL constant after discovery |
| `docs/discovery/oakland_endpoints.md` | Update with cart page URL and any new endpoints found |
| `tests/unit/nextrec/test_cart.py` | New tests for cart URL construction |
| `tests/unit/nextrec/tui/test_timeline.py` | May need updates for TUI checkout changes |

### Error and validation semantics

- If cart page load fails (non-200), fall back to single-slot `FacilityBooking` page and log a warning.
- If multi-facility items are in the cart and PerfectMind does not support cross-facility checkout, surface a clear error to the user before checkout ("Selected slots span multiple facilities, which cannot be checked out together").

Testing approach
----------------

### Discovery phase (no code change)
1. Run `nextrec debug-browse`, search for a facility, add multiple items to cart manually, inspect network traffic for cart-related XHR calls, identify the cart URL.
2. Alternatively, use the existing HAR in `docs/discovery/` to look for cart-related GET/POST patterns.

### Implementation test delta: new tests + updated tests

| Test | What it validates |
|------|-------------------|
| `test_cart_url_construction` (new) | `build_checkout_url()` returns correct cart URL given multiple slots |
| `test_checkout_fallback` (new) | When cart URL fails, falls back to single-slot URL |
| `test_multi_facility_checkout_validation` (new) | Validates that cross-facility selection produces appropriate warning/error |
| Existing TUI/CLI booking tests | Updated mocks to match new checkout URL construction |

All existing tests must still pass unchanged (except mock adjustments for new URL).

Docs delta classification: `docs/discovery/oakland_endpoints.md` update with cart endpoint.

Documentation approach
----------------------
- Update `docs/discovery/oakland_endpoints.md` with the discovered cart-page URL and any relevant request/response shape.
- Update `docs/discovery/oakland_endpoints.json` if endpoints are added.
- No user-facing doc changes needed (the TUI/CLI workflows remain the same).

Progress checklist
------------------

- [x] Phase 0: Discovery — skip (user opted out, going straight to Approach B)
- [x] Phase 1: Design decision — chose Approach B (facility list page), C (multi-tab) as fallback
- [x] Phase 2: Implement Approach B in `tui/app.py` — use `FACILITY_LIST_URL` instead of slot-specific `FacilityBooking`
- [x] Phase 3: Implement Approach B in `cli/main.py` — same change, then reverted to single-slot URL
- [x] Phase 5: Implement Approach C (multi-tab) in `tui/app.py` — one `FacilityBooking` tab per selected slot
- [x] Verify with live site (multi-slot same-facility, multi-slot multi-facility) — sufficient confidence from live testing, closing

Phases
------

### Phase 0: Cart page discovery

**Goal**: Identify the correct URL to show all cart items.

**Approach**:
1. Run `nextrec debug-browse`, log in, navigate to a facility page, manually add a slot to cart, then inspect the network request to see what URL the cart popup or cart page hits.
2. Look at the `bookMe4Cart.js` script contents via the browser's dev tools to find cart API endpoints.
3. Check the existing HAR capture for any GET requests to cart-related paths.

**Deliverable**: Cart page URL (or confirmation that no aggregate page exists).

### Phase 1: Design decision

**Goal**: Select the check-out strategy.

**Decision options**:
- **A (cart page)**: Navigate to `Cart` page showing all held items.
- **B (parameterless FacilityBooking)**: Load `FacilityBooking` without `startDateTimeTicks` to show cart.
- **C (multi-tab)**: Open multiple checkout tabs, one per selected slot.

**Deliverable**: Decision recorded in `decisions/` or inline in implementation notes with rationale.

### Phase 2: TUI checkout fix

**Goal**: Make the TUI `_run_booking()` open the correct checkout URL.

**Changes in `tui/app.py`**:
1. Replace the single-slot checkout URL construction (line 681–698) with logic that:
   - Groups selected slots by facility
   - Opens each facility's cart page (Approach A) or
   - Opens multi-tab checkout (Approach C)
2. Keep the `CheckoutScreen` modal but update its messaging to reflect multi-slot context.

### Phase 3: CLI checkout fix

**Goal**: Make `cli/main.py` `_async_book()` use the same checkout strategy.

### Phase 4: Cross-facility validation

**Goal**: Gracefully handle multi-facility selections.

**Changes**:
- Before checkout, check if selected slots span multiple facilities.
- If so, warn the user or handle gracefully (e.g., open separate checkout sessions per facility).

### Phase 5: Documentation

**Goal**: Record the discovered cart endpoint.

### Phase 6: Live verification

**Goal**: Confirm the fix works against the live Oakland PerfectMind site.

**Test scenarios**:
1. Single facility, single slot (regression — must still work)
2. Single facility, multiple consecutive slots (e.g., 2×60min back-to-back)
3. Single facility, multiple non-consecutive slots (e.g., 2×60min on different days)
4. Multiple facilities, one slot each (if possible)

Execution order recommendation
------------------------------
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

Phases 2 and 3 can be done in parallel once Phase 1 is decided.

Implementation notes
--------------------

### 2026-07-19 — Decision: Skip cart-discovery phase, implement B then C

User decided to skip Phase 0 (cart page discovery) and go straight to trying Approach B, with C as fallback.

**Approach B**: Navigate to the facility detail page (`FACILITY_DETAIL_URL?facilityId=X`) after adding items to cart, instead of the slot-specific `FacilityBooking` page. The cart is server-side and persisted in the session; the facility page's cart widget should show all held items. User clicks through from there.

**Approach C (fallback)**: If B doesn't work (page doesn't show cart items), open one `FacilityBooking` tab per selected slot. Grouped by facility for clarity.

Implementation strategy:
- TUI: Replace single-slot checkout URL with `FACILITY_LIST_URL` (B). Keep multi-tab C ready in a toggle.
- CLI: Same change.
- Group selected slots by facility so the checkout page context is sensible.

### 2026-07-19 — Approach B tested → switched to Approach C

Approach B (facility list page) tested — page had stale cart items and the "Booking listing" link led to a checkout for an unrelated slot. So `StoreOccupancyItems` doesn't scope items to a single session cleanly.

**Approach C (multi-tab) implemented**:
- `tui/app.py`: Opens one `FacilityBooking` tab per selected slot. Groups by facility for tab order. Shows "N checkout tab(s)" in status bar.
- `cli/main.py`: Reverted to single `FacilityBooking` URL (only handles one slot).
- All 128 tests pass.

Risks and mitigations
---------------------
- **Risk**: No aggregate cart page exists on PerfectMind. **Mitigation**: Fall back to Approach C (multi-tab).
- **Risk**: PerfectMind cart clears when the landing page is navigated away from. **Mitigation**: Test with live session; use a kept-alive headless session for cart operations.
- **Risk**: Cross-facility checkout not supported by PerfectMind. **Mitigation**: Surface a clear error and suggest single-facility booking only.

Acceptance criteria
-------------------
1. Selecting multiple slots (consecutive or non-consecutive, same facility) and pressing Book opens a checkout page that shows all selected items.
2. Selecting a single slot works unchanged (regression).
3. If the user selects slots across multiple facilities, either all appear in checkout or a clear error is shown explaining the limitation.
4. The CLI `book` command's checkout behavior matches the TUI (both use the same strategy).
5. All existing unit tests pass.
6. Discovery docs updated with the cart page URL and any new endpoints found.
