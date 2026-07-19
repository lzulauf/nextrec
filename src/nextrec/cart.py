import logging
import urllib.parse
from typing import Optional, Set

from playwright.sync_api import Page

from nextrec.browser import BrowserSession
from nextrec.models import BookingResult, FacilityConfig, TimeSlot

logger = logging.getLogger(__name__)

FACILITY_DETAIL_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/Facility"
VALIDATE_BOOKING_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/ValidateFacilityBooking"
STORE_OCCUPANCY_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/StoreOccupancyItems"
CSRF_SELECTOR = '#AjaxAntiForgeryForm input[name="__RequestVerificationToken"]'


class CartError(Exception):
    pass


class CartManager:
    def __init__(self, session: BrowserSession):
        self._session = session
        self._page: Optional[Page] = None
        self._booked_keys: Set[str] = set()

    def _ensure_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            self._page = self._session.manager.new_page()
        return self._page

    @property
    def page(self) -> Page:
        return self._ensure_page()

    def _extract_csrf(self, page: Page) -> str:
        from playwright.sync_api import TimeoutError as PwTimeout
        try:
            element = page.wait_for_selector(CSRF_SELECTOR, state="attached", timeout=10000)
            if element is None:
                raise CartError("CSRF token element not found on page")
            token = element.get_attribute("value")
            if not token:
                raise CartError("CSRF token attribute was empty")
            return token
        except PwTimeout as exc:
            raise CartError(f"Timed out waiting for CSRF token: {exc}") from exc

    def _booking_key(self, facility_id: str, slot: TimeSlot) -> str:
        if slot.base_slot_ticks:
            return f"{facility_id}_{'_'.join(str(t) for t in slot.base_slot_ticks)}"
        return f"{facility_id}_{slot.ticks}"

    def _book_single(
        self, page, facility_id, config, ticks, duration_ticks,
        number_of_nights, fee_type, csrf_token, detail_url,
    ) -> tuple:
        validate_payload = [
            ("facilityId", facility_id),
            ("widgetId", ""),
            ("calendarId", config.calendar_id),
            ("programId", config.service_id),
            ("timeTicks", str(ticks)),
            ("duration", str(duration_ticks)),
            ("numberOfNights", str(number_of_nights)),
            ("feeType", str(fee_type)),
            ("__RequestVerificationToken", csrf_token),
        ]
        for dp in config.duration_prices:
            validate_payload.append(("durationIds[]", dp.id))

        logger.info("Validating booking for facility %s ticks %s", facility_id, ticks)
        validate_resp = page.request.post(
            VALIDATE_BOOKING_URL,
            data=urllib.parse.urlencode(validate_payload, doseq=True),
            headers={
                "x-requested-with": "XMLHttpRequest",
                "origin": "https://cityofoakland.perfectmind.com",
                "referer": detail_url,
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        if not validate_resp.ok:
            raise CartError(f"ValidateFacilityBooking returned {validate_resp.status}: {validate_resp.status_text}")

        logger.info("Storing cart for facility %s ticks %s", facility_id, ticks)
        store_resp = page.request.post(
            STORE_OCCUPANCY_URL,
            data=urllib.parse.urlencode([("__RequestVerificationToken", csrf_token)]),
            headers={
                "x-requested-with": "XMLHttpRequest",
                "origin": "https://cityofoakland.perfectmind.com",
                "referer": detail_url,
                "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        if not store_resp.ok:
            raise CartError(f"StoreOccupancyItems returned {store_resp.status}: {store_resp.status_text}")

        return validate_resp.status, store_resp.status

    def add_to_cart(
        self,
        facility_id: str,
        config: FacilityConfig,
        slot: TimeSlot,
        number_of_nights: int = 0,
        fee_type: int = 0,
    ) -> BookingResult:
        key = self._booking_key(facility_id, slot)
        if key in self._booked_keys:
            logger.info("Already booked slot %s for facility %s, skipping", slot.ticks, facility_id)
            return BookingResult(
                success=True,
                facility_id=facility_id,
                slot_date=slot.date,
                slot_start=slot.start_time,
                message="Already added to cart in this session",
            )

        page = self._ensure_page()
        detail_url = f"{FACILITY_DETAIL_URL}?facilityId={facility_id}"
        logger.info("Navigating to facility detail page: %s", detail_url)
        page.goto(detail_url, wait_until="networkidle")
        csrf_token = self._extract_csrf(page)

        results = []
        tick_values = slot.base_slot_ticks or [slot.ticks]
        base_duration_ticks = slot.duration_ticks // len(tick_values) if slot.base_slot_ticks else slot.duration_ticks

        for ticks in tick_values:
            v_status, s_status = self._book_single(
                page, facility_id, config, ticks, base_duration_ticks,
                number_of_nights, fee_type, csrf_token, detail_url,
            )
            results.append((ticks, v_status, s_status))

        self._booked_keys.add(key)

        parts = "; ".join(f"slot{t}=validate={v},store={s}" for t, (_, v, s) in enumerate(results))
        return BookingResult(
            success=True,
            facility_id=facility_id,
            slot_date=slot.date,
            slot_start=slot.start_time,
            message=f"Added {len(results)} slot(s) to cart ({parts})",
        )
