"""Add selected slots to the PerfectMind cart and open a single checkout tab.

After a slot is held (``CartManager.add_to_cart``), the site needs three more
pages before the slot is in the cart:

1. Participants (``/Clients/BookMe4EventParticipants``): choose who the
   booking is for, then "Next" (POST ``FillForms``).
2. Extras (``/Clients/BookMe4Extras/Extras``): choose the fee (resident or
   non-resident), then "Next" / "Add to Cart".
3. POST ``/Clients/BookMe4Cart/Cart?memberId=...`` adds the item and shows the
   cart, which is where checkout continues.

``add_slots_to_cart`` drives those pages in a headless browser, one slot at a
time. Any slot it cannot add is reported so ``open_checkout`` can open that
slot's booking page as its own tab, the same way the old flow did.
"""

import dataclasses
import enum
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from nextrec.browser import BrowserSession
from nextrec.cart import CartError, CartManager
from nextrec.models import FacilityConfig, TimeSlot

logger = logging.getLogger(__name__)

SITE_URL = "https://cityofoakland.perfectmind.com"
FACILITY_DETAIL_URL = f"{SITE_URL}/Clients/BookMe4LandingPages/Facility"
FACILITY_BOOKING_URL = f"{SITE_URL}/SocialSite/BookMe4EventParticipants/FacilityBooking"

# Page markers and selectors, from the 2026-11-26 capture. Keep site details here.
PARTICIPANTS_PATH = "/BookMe4EventParticipants"
EXTRAS_PATH = "/BookMe4Extras/Extras"
CART_PATH = "/BookMe4Cart/Cart"
SIGN_IN_PATH = "MemberSignIn"
SELF_PARTICIPANT_CHECKBOX = "#ParticipantsFamily_FamilyMembers_0__IsParticipating"
PARTICIPANTS_NEXT = 'a.bm-button[title="Next"]'
FEE_LABELS = ".bm-extras-prices label[for]"
FEE_NAME = ".fee-name-item"
EXTRAS_ADD_TO_CART = "#btnNext"

DEFAULT_ADD_TIMEOUT_MS = 20_000


class Pricing(str, enum.Enum):
    """Which fee to choose on the Extras page."""

    RESIDENT = "resident"
    NON_RESIDENT = "non-resident"

    @property
    def label(self) -> str:
        return "Resident" if self is Pricing.RESIDENT else "Non-Resident"


def parse_pricing(value: Optional[str]) -> Pricing:
    """Return the Pricing for a config or CLI value, defaulting to resident.

    Raises:
        ValueError: If the value is not "resident" or "non-resident".
    """
    if value is None or str(value).strip() == "":
        return Pricing.RESIDENT
    normalized = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in ("nonresident", "non-resident"):
        return Pricing.NON_RESIDENT
    if normalized == "resident":
        return Pricing.RESIDENT
    raise ValueError(f"pricing must be 'resident' or 'non-resident', got {value!r}")


class NotLoggedInError(CartError):
    """The site redirected to sign-in, so no slot can be added."""


@dataclasses.dataclass(frozen=True)
class SlotAddResult:
    facility_id: str
    slot: TimeSlot
    added: bool
    booking_url: str
    message: str = ""


@dataclasses.dataclass(frozen=True)
class CartAddReport:
    results: Tuple[SlotAddResult, ...]
    cart_url: Optional[str]

    @property
    def added(self) -> Tuple[SlotAddResult, ...]:
        return tuple(r for r in self.results if r.added)

    @property
    def failed(self) -> Tuple[SlotAddResult, ...]:
        return tuple(r for r in self.results if not r.added)


def build_booking_url(facility_id: str, config: FacilityConfig, slot: TimeSlot, attendees: int) -> str:
    """Return the site's FacilityBooking URL for one slot."""
    dur_id = next(
        (dp.id for dp in config.duration_prices if dp.minutes == slot.duration_minutes),
        config.duration_prices[0].id if config.duration_prices else "",
    )
    back_url = urllib.parse.quote(f"{FACILITY_DETAIL_URL}?facilityId={facility_id}", safe="")
    return (
        f"{FACILITY_BOOKING_URL}?facilityId={facility_id}"
        f"&calendarId={config.calendar_id}"
        f"&serviceId={config.service_id}"
        f"&duration={slot.duration_minutes}"
        f"&durationId={dur_id}"
        f"&startDateTimeTicks={slot.ticks}"
        f"&numberOfAttendees={attendees}"
        f"&numberOfNights=0"
        f"&feeType=0"
        f"&landingPageBackUrl={back_url}"
    )


def choose_fee(fee_names: Sequence[str], pricing: Pricing) -> Optional[int]:
    """Return the index of the single fee matching ``pricing``, or None.

    Fee names look like "Hourly Rental: Resident" or "Hourly Rental: Non-Resident".
    None means zero or several fees match, so a person should choose.
    """
    matches = []
    for i, name in enumerate(fee_names):
        lowered = name.lower().replace("‑", "-")
        is_non_resident = "non-resident" in lowered or "nonresident" in lowered or "non resident" in lowered
        is_resident = "resident" in lowered and not is_non_resident
        if (pricing is Pricing.NON_RESIDENT and is_non_resident) or (pricing is Pricing.RESIDENT and is_resident):
            matches.append(i)
    return matches[0] if len(matches) == 1 else None


def summarize(report: CartAddReport) -> str:
    """Return a one-line status for the TUI and CLI."""
    total = len(report.results)
    text = f"Added {len(report.added)}/{total} to cart"
    if report.failed:
        reasons = "; ".join(r.message for r in report.failed[:2])
        text += f"; {len(report.failed)} need a manual click ({reasons})"
    return text


class _SlotAddFailed(Exception):
    pass


async def _add_one_via_page(page, booking_url: str, pricing: Pricing, timeout_ms: int) -> str:
    """Drive the Participants and Extras pages for one slot.

    Returns:
        The cart page URL after the add.

    Raises:
        NotLoggedInError: If the site asks for sign-in.
        _SlotAddFailed: If this slot needs a person (with the reason).
    """
    dialogs: List[str] = []

    async def _on_dialog(dialog):
        dialogs.append(dialog.message)
        await dialog.dismiss()

    page.on("dialog", _on_dialog)

    await page.goto(booking_url, wait_until="load")
    if SIGN_IN_PATH in page.url:
        raise NotLoggedInError("PerfectMind session expired; sign in again")
    if PARTICIPANTS_PATH not in page.url:
        raise _SlotAddFailed(f"unexpected page {page.url.split('?', 1)[0]}")

    participant = page.locator(SELF_PARTICIPANT_CHECKBOX)
    if await participant.count() == 0:
        raise _SlotAddFailed("no participant to choose")
    if not await participant.is_checked():
        await participant.check(force=True)
    await page.locator(PARTICIPANTS_NEXT).click()
    await page.wait_for_url(f"**{EXTRAS_PATH}**", timeout=timeout_ms)

    add_button = page.locator(EXTRAS_ADD_TO_CART)
    await add_button.wait_for(state="visible", timeout=timeout_ms)
    fees = await page.eval_on_selector_all(
        FEE_LABELS,
        f"els => els.map(e => ({{id: e.htmlFor, name: ((e.querySelector('{FEE_NAME}') || e).textContent || '').trim()}}))",
    )
    index = choose_fee([f["name"] for f in fees], pricing)
    if index is None:
        names = ", ".join(f["name"] for f in fees) or "none"
        raise _SlotAddFailed(f"no single {pricing.label} fee (fees: {names})")
    fee_id = fees[index]["id"]
    await page.locator(f'label[for="{fee_id}"]').click()
    if not await page.locator(f'[id="{fee_id}"]').is_checked():
        raise _SlotAddFailed(f"could not select {fees[index]['name']}")

    try:
        async with page.expect_response(
            lambda r: CART_PATH in r.url and r.request.method == "POST", timeout=timeout_ms,
        ) as response_info:
            await add_button.click()
        response = await response_info.value
    except Exception as e:
        detail = f"site said: {dialogs[-1]}" if dialogs else f"no cart response ({type(e).__name__})"
        raise _SlotAddFailed(detail) from e
    if not response.ok:
        raise _SlotAddFailed(f"cart returned HTTP {response.status}")
    await page.wait_for_load_state("load")
    return page.url


async def add_slots_to_cart(
    session: BrowserSession,
    selections: Iterable[Tuple[str, FacilityConfig, TimeSlot]],
    attendees: int,
    pricing: Pricing = Pricing.RESIDENT,
    timeout_ms: int = DEFAULT_ADD_TIMEOUT_MS,
) -> CartAddReport:
    """Hold each slot and add it to the cart, one slot at a time.

    A slot that cannot be added is reported with ``added=False``; it never
    stops the others.

    Raises:
        NotLoggedInError: If the site asks for sign-in.
    """
    cart = CartManager(session)
    results: List[SlotAddResult] = []
    cart_url: Optional[str] = None

    for facility_id, config, slot in selections:
        booking_url = build_booking_url(facility_id, config, slot, attendees)
        try:
            await cart.add_to_cart(facility_id, config, slot, number_of_attendees=attendees)
        except Exception as e:  # CartError, or HTTP errors fetching the CSRF token
            results.append(SlotAddResult(facility_id, slot, False, booking_url, f"hold failed: {e}"))
            continue

        page = await session.manager.new_page()
        try:
            cart_url = await _add_one_via_page(page, booking_url, pricing, timeout_ms)
            results.append(SlotAddResult(facility_id, slot, True, booking_url, "added"))
        except NotLoggedInError:
            raise
        except _SlotAddFailed as e:
            logger.warning("Slot %s %s at %s needs a manual add: %s", slot.date, slot.start_time, facility_id, e)
            results.append(SlotAddResult(facility_id, slot, False, booking_url, str(e)))
        except Exception as e:
            logger.exception("Automatic add failed for %s", booking_url)
            results.append(SlotAddResult(facility_id, slot, False, booking_url, f"{type(e).__name__}: {e}"))
        finally:
            try:
                await page.close()
            except Exception:
                pass

    return CartAddReport(results=tuple(results), cart_url=cart_url)


async def open_checkout(session: BrowserSession, report: CartAddReport) -> int:
    """Open the cart tab (if anything was added) plus one tab per failed slot.

    Returns:
        The number of tabs opened.
    """
    urls = []
    if report.cart_url:
        urls.append(report.cart_url)
    urls.extend(r.booking_url for r in report.failed)
    for url in urls:
        page = await session.manager.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # the tab is open either way; the person can reload it
            logger.warning("Checkout tab did not finish loading %s: %s", url, e)
    return len(urls)


def write_report_log(report: CartAddReport, path: Path) -> None:
    """Append one line per slot result to ``path`` for troubleshooting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    lines = [f"{stamp} {summarize(report)}; cart_url={report.cart_url}"]
    for r in report.results:
        state = "added" if r.added else "MANUAL"
        lines.append(f"{stamp}   {state} {r.slot.date} {r.slot.start_time} facility={r.facility_id}: {r.message}")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
