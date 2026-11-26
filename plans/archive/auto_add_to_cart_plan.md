# Auto Add-to-Cart Plan

Status: Done

Goal
----
When the user selects several slots and presses Book, nextrec adds every slot to the PerfectMind cart on its own and opens **one** browser tab for checkout, instead of one `FacilityBooking` tab per slot that each need a manual "Add to Cart" click.

Why this comes first
--------------------
Multi-slot booking works today only through [Approach C of the multi-checkout plan](multi_checkout_flow_plan.md): N tabs, N manual clicks, then one checkout. With several slots that is slow and easy to get wrong while slots are only briefly held.

Prerequisite
------------
Phase 0 (capture the real "Add to Cart" request). Phases 2 and 3 cannot be finalised until the request and the post-add cart URL are known.

Scope
-----
- Capture and document the request sent by the "Add to Cart" button on `FacilityBooking`, and the cart/checkout URL it leads to.
- Perform "Add to Cart" automatically for each selected slot in the headless booking session.
- Open a single headed tab on the cart page after all adds.
- Fall back to today's per-slot tabs for any slot that could not be added automatically.
- Share the checkout flow between the TUI and the CLI `book` command.
- Check the `isOk` field of the `ValidateFacilityBooking` response (currently ignored).

Out of scope
------------
- Paying or completing checkout on the user's behalf.
- Removing stale cart items left from earlier sessions (we only warn).
- Parallel adds; adds run one slot at a time.

Technical design details
------------------------

### What we know (from `docs/discovery/facility_detail_capture.json`)

The facility landing page sends `ValidateFacilityBooking` (response `{"isOk": true}`) and `StoreOccupancyItems` **before** it navigates to `FacilityBooking`. So `CartManager.add_to_cart` today only places a **hold**; the cart item is created later by the "Add to Cart" button on `FacilityBooking`, whose request has never been captured.

```
landing page                     FacilityBooking page               cart
 Validate ─► StoreOccupancy ─►    GET FacilityBooking ─► [Add to Cart] ─► ??? (unknown URL)
 (CartManager does this today)    (tab per slot today)    (manual click today)
```

### What the capture showed (2026-11-26 live run)

There is no single "Add to Cart" button. After the hold, the site walks through three pages; each step is a normal form POST:

```
GET  /Clients/BookMe4EventParticipants/FacilityBooking?...   302 ─► /Clients/BookMe4EventParticipants?eventId=<eventId>&...
     page 1 "Participants": pick who the booking is for (the account holder, "You")
POST /Clients/BookMe4RegistrationForms/FillForms              302 ─► /Clients/BookMe4Extras/Extras
     fields: EventInfo.* (CalendarId, ProgramId, LocationId, FacilityId), ParticipantsFamily.EventId,
             ParticipantsFamily.FamilyMembers[0].MemberId / PriceTypeId / IsParticipating=true
     page 2 "Extras": pick the fee, e.g. "Hourly Rental: Resident" ($15) or "Hourly Rental: Non-Resident" ($18)
POST /Clients/BookMe4Cart/Cart?memberId=<memberId>&waitListMode=False   ─► cart page (this is the add)
     fields: EventId, ObjectId, CartItemMembers[0].MemberId, CartItemMembers[0].Price.Id,
             CartItemMembers[0].Price.ProratedAmount, ...
```

- The Extras page embeds JSON with every fee (`Prices[]`: `Id`, `PriceTypeId`, `Name`, `Amount`) and the member's `Residency` / `IsResident`, so the right fee can be chosen without guessing.
- The cart page `/Clients/BookMe4Cart/Cart?memberId=...` is where checkout continues, so it is the one tab to open.
- `numberOfNights` is sent as `1` by the site's own `ValidateFacilityBooking` call; nextrec sends `0`. Left as is because the current value works; revisit only if a hold fails.

### Fee selection (new requirement)

Default to the resident fee. Add a `pricing` setting (`resident` | `non-resident`, default `resident`) to the config file, a `--pricing` CLI option and a TUI toggle. The add step picks the fee whose name ends in `: Resident` / `: Non-Resident`. If no fee matches, or the account's `IsResident` disagrees with a resident choice, the slot falls back to a manual tab with a message rather than picking a price.

### Phase 0 tooling (used once, then removed)

- `nextrec.traffic_capture.TrafficRecorder`: attaches to a Playwright `BrowserContext`, records every PerfectMind non-static request across all tabs, in request order, with POST bodies, JSON responses, saved HTML documents, failures and main-frame navigations.
- `nextrec capture-cart`: opens a headed, logged-in browser on the facility list, records while the user books one slot up to "Add to Cart", then writes `captures/add_to_cart_capture.json` and `captures/pages/*.html` (git-ignored, contains personal data) and prints the ordered POSTs and navigations.
- `BrowserManager.context` property exposed the live context.
- After the capture answered the open questions, all three were removed before merge to keep the codebase small. They can be recovered from the project thread's history if another capture is needed.

### Target flow (Phase 2, browser-driven add)

```
booking session (headless)                       checkout session (headed)
for slot in selected:                            
    CartManager.add_to_cart(...)   # hold        
    page = new_page(FacilityBooking url)         
    click "Add to Cart"; await add response      
    record SlotAddResult                         
save storage state ─────────────────────────────► open ONE tab: cart URL
                                                  + one FacilityBooking tab per failed slot
```

New module `src/nextrec/checkout.py`, used by `tui/app.py::_run_booking` and `cli/main.py::_async_book`:

```python
@dataclasses.dataclass(frozen=True)
class SlotAddResult:
    facility_id: str
    slot: TimeSlot
    added: bool
    booking_url: str          # FacilityBooking URL, used for the manual fallback tab
    message: str = ""

@dataclasses.dataclass(frozen=True)
class CartAddReport:
    results: List[SlotAddResult]
    cart_url: Optional[str]   # page the site lands on after a successful add
    holds_before: Optional[int]
    holds_after: Optional[int]

def build_booking_url(facility_id: str, config: FacilityConfig, slot: TimeSlot, attendees: int) -> str: ...

async def add_slots_to_cart(session: BrowserSession, selections, attendees: int,
                            add_timeout_ms: int = 15000) -> CartAddReport: ...

async def open_checkout(session: BrowserSession, report: CartAddReport) -> None: ...
```

Usage:

```python
report = await add_slots_to_cart(booking_session, selected, attendees=num_att)
await booking_session.manager.save_storage_state(checkout_state)
await open_checkout(checkout_session, report)   # 1 cart tab + fallback tabs
```

Per-slot add (pseudocode):

```python
await cart.add_to_cart(fid, cfg, slot)                 # raises CartError if isOk is false
page = await session.manager.new_page()
await page.goto(build_booking_url(...), wait_until="networkidle")   # lands on Participants
await select_account_holder(page)                      # tick "You" if not already ticked
await click_next_and_wait(page, "/BookMe4Extras/Extras")
fee = choose_fee(read_extras_json(page), pricing)      # None -> manual fallback
if fee is None:
    return SlotAddResult(..., added=False, message="no matching fee")
await select_fee(page, fee)
async with page.expect_response(lambda r: "/BookMe4Cart/Cart" in r.url, timeout=add_timeout_ms) as info:
    await click_add_to_cart(page)
ok = (await info.value).ok
cart_url = page.url if ok else None
await page.close()
```

Page selectors live in one module-level table so a site change is a one-line fix. Error semantics: `add_slots_to_cart` never raises for a single slot; each failure becomes `added=False` with a message. It raises only if the session itself is unusable (not logged in).

### Optional Phase 3 (direct HTTP add)

If the captured request is a plain form/JSON POST whose fields can be read from the `FacilityBooking` HTML, add `CartManager.add_booking_to_cart` that GETs the page, parses token and ids, and POSTs directly. Keep the browser click as fallback. Decide after Phase 0 with a decision doc in `decisions/`.

Testing approach
----------------
- Expected test delta: new tests and updated tests.
- Unit (Phase 0, removed with the tooling): `tests/unit/nextrec/test_traffic_capture.py` covered filtering, ordering, HTML saving, failure and body errors, navigations, multi-tab attach and JSON output.
- Unit (Phase 1–2): `tests/unit/nextrec/test_checkout.py` with fake Page/Locator objects: all slots added; button missing; button disabled; error or timeout on add response; mixed batch yields correct fallback list; `build_booking_url` matches today's URL. `test_cart.py`: `isOk: false` raises `CartError`.
- Manual live checks (stop before paying, empty the cart afterwards): 1 slot; 2 slots same facility; 2 facilities; merged adjacent slot; one forced failure (bad selector) falls back to a tab. In each, the cart shows exactly the selected slots and the hold count matches.
- Run: focused test files while iterating, then full `pytest`.

Documentation approach
----------------------
- Expected docs delta: both.
- README: describe the single-tab checkout and fallback in the booking section (Phase 2).
- `docs/discovery/oakland_endpoints.md` (local, untracked): correct `StoreOccupancyItems` from "Add to cart" to "hold", add FillForms, Extras and Cart (Phase 1).
- README: document the `pricing` setting (Phase 2).

Progress checklist
------------------
- [x] Phase 0a: Capture tooling (`TrafficRecorder`, `capture-cart`) built and used (removed before merge)
- [x] Phase 0b: Live capture run done and Add to Cart request + cart URL documented
- [x] Phase 1: `checkout.py` extracted with `build_booking_url`; `isOk` checked; TUI and CLI use it with no behavior change
- [x] Phase 2: Browser-driven add with single cart tab and per-slot fallback
- [ ] Phase 3 (optional): Direct HTTP add behind the browser fallback (deferred; not needed now that the browser flow works)
- [ ] Manual live check matrix passed (2 slots at 2 facilities: passed 2026-11-26)

Phases
------
0. **Discovery.** Tooling (this PR), then the user runs `nextrec capture-cart` once and books one slot up to Add to Cart. Update `oakland_endpoints.md` with the request, success signal, cart URL and any required form fields. PR boundary: tooling PR; docs PR after the run.
1. **Refactor.** Move URL building and checkout opening into `src/nextrec/checkout.py`; check `isOk` in `cart.py`. No user-visible change. PR boundary.
2. **Auto add.** Implement `add_slots_to_cart` / `open_checkout`; TUI status reads "4/5 added to cart, 1 needs a manual click"; CLI `book` uses the same path. PR boundary.
3. **Direct HTTP (optional).** Only if Phase 0 shows a simple request. Decision doc first. PR boundary.

Execution order recommendation
------------------------------
0 → 1 → 2, then decide on 3. Phase 1 can start before Phase 0b finishes.

Implementation notes
--------------------
- 2026-11-26: Completed and archived. Phase 3 is deferred. Not yet live-tested: a single slot, a merged back-to-back slot, and a forced fallback.
- 2026-11-26: First live run: every hold came back `isOk=false` and fell back to tabs. nextrec's `ValidateFacilityBooking` sent `numberOfNights=0` and `numberOfAttendees`, while the site sends `numberOfNights=1` and no attendees. Now matches the site, and `isOk=false` only warns, since the old flow ignored it. Second live run: 2/2 slots at two facilities added, one cart tab opened, and checkout continued from it. That settles both open questions (the cart URL works with GET in the headed session, and a second facility booking is allowed in the same cart).
- 2026-11-26: Phases 1 and 2 landed in one PR at the user's request. `src/nextrec/checkout.py` holds each slot, then drives Participants → Extras → Cart per slot in the headless session, choosing the fee with `choose_fee` and the `pricing` setting (`resident` default; CLI `--pricing`, config `pricing`, TUI Fee button). `open_checkout` opens the cart URL plus one booking tab per failed slot. Site dialogs are dismissed and their text becomes the failure reason. `CartManager` checks `isOk` (later changed to warn, see above). Verified with unit tests and a headless Chromium run against mock pages using the real selectors. Not yet verified live: whether the post-add cart URL renders when opened with GET in the headed session, and whether the site blocks a second facility booking in the same cart (`cartHasFacilityBooking()` on the Extras page; its source wasn't captured).
- 2026-11-26: Phase 0b. Live capture done (one slot, resident fee). Flow is Participants → FillForms → Extras → POST Cart; see "What the capture showed". Fee choice added as a requirement. The capture's `StoreOccupancyItems` response body could not be read because the page navigated away first; harmless.
- 2026-11-26: Phase 0a. Added `TrafficRecorder` and `capture-cart` (removed again before merge). Smoke-tested the recorder against a real headless Chromium context (POST body, JSON response, HTML save, second tab). Existing `debug-browse` reads async response bodies without awaiting them and blocks the event loop on `input()`, so it cannot capture bodies; left unchanged, `capture-cart` replaces it for this purpose. Pre-existing failure: `TestFindSystemChrome::test_uses_known_windows_location` fails on Linux.

Risks and mitigations
---------------------
- **Partial adds:** each slot reports separately; failed slots open as manual tabs, so the worst case equals today's flow.
- **Site markup changes:** selector and success rule are single constants; on any miss or timeout we fall back to a tab and log the page URL.
- **Extra input on some facilities** (attendee picker, waivers, questions): detect a disabled or missing button and fall back instead of guessing.
- **Stale or duplicate cart items:** compare `GetActiveHoldsCount` before and after; warn when the delta differs from the number of added slots.
- **Hold expiry:** adds run immediately after holds; checkout opens right after.
- **Cart not carried to the headed session:** verified in the live checks; if cookies alone don't carry it, run adds in the headed context with tabs closed after each add.

Acceptance criteria
-------------------
1. Selecting N slots and pressing Book opens exactly one tab showing all N in the cart when every add succeeds.
2. A slot that cannot be added opens its own `FacilityBooking` tab and is named in the status line.
3. A single-slot booking still works (regression).
4. CLI `book` and TUI share the same checkout code.
5. Focused tests and the full suite pass (aside from the known Windows-path test on Linux).
6. `oakland_endpoints.md` and README describe the new flow and endpoints.
