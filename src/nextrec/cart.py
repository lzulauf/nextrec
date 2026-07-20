import logging
import re
import urllib.parse
from typing import Optional, Set

import httpx2

from nextrec.browser import BrowserSession
from nextrec.models import BookingResult, FacilityConfig, TimeSlot

logger = logging.getLogger(__name__)

FACILITY_DETAIL_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/Facility"
VALIDATE_BOOKING_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/ValidateFacilityBooking"
STORE_OCCUPANCY_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/StoreOccupancyItems"


class CartError(Exception):
    pass


class CartManager:
    def __init__(self, session: BrowserSession):
        self._session = session
        self._http: Optional[httpx2.AsyncClient] = None
        self._booked_keys: Set[str] = set()

    async def _ensure_http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = await self._session.get_httpx_client()
        return self._http

    async def _fetch_csrf(self, facility_id: str, detail_url: str) -> str:
        http = await self._ensure_http()
        resp = await http.get(detail_url)
        resp.raise_for_status()
        m = re.search(r'name="__RequestVerificationToken".*?value="([^"]*)"', resp.text)
        if not m:
            raise CartError("CSRF token not found on facility detail page")
        return m.group(1)

    def _booking_key(self, facility_id: str, slot: TimeSlot) -> str:
        if slot.base_slot_ticks:
            return f"{facility_id}_{'_'.join(str(t) for t in slot.base_slot_ticks)}"
        return f"{facility_id}_{slot.ticks}"

    async def _book_single(
        self, http, facility_id, config, ticks, duration_ticks,
        number_of_nights, fee_type, csrf_token, detail_url,
        number_of_attendees=1,
    ) -> tuple:
        validate_payload = [
            ("facilityId", facility_id),
            ("widgetId", ""),
            ("calendarId", config.calendar_id),
            ("programId", config.service_id),
            ("timeTicks", str(ticks)),
            ("duration", str(duration_ticks)),
            ("numberOfAttendees", str(number_of_attendees)),
            ("numberOfNights", str(number_of_nights)),
            ("feeType", str(fee_type)),
            ("__RequestVerificationToken", csrf_token),
        ]
        for dp in config.duration_prices:
            validate_payload.append(("durationIds[]", dp.id))

        headers = {
            "x-requested-with": "XMLHttpRequest",
            "origin": "https://cityofoakland.perfectmind.com",
            "referer": detail_url,
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        logger.info("Validating booking for facility %s ticks %s", facility_id, ticks)
        try:
            validate_resp = await http.post(
                VALIDATE_BOOKING_URL,
                data=urllib.parse.urlencode(validate_payload, doseq=True),
                headers=headers,
            )
            validate_resp.raise_for_status()
        except httpx2.HTTPStatusError as e:
            raise CartError(f"ValidateFacilityBooking returned {e.response.status_code}") from e

        logger.info("Storing cart for facility %s ticks %s", facility_id, ticks)
        try:
            store_resp = await http.post(
                STORE_OCCUPANCY_URL,
                data=urllib.parse.urlencode([("__RequestVerificationToken", csrf_token)]),
                headers=headers,
            )
            store_resp.raise_for_status()
        except httpx2.HTTPStatusError as e:
            raise CartError(f"StoreOccupancyItems returned {e.response.status_code}") from e

        return validate_resp.status_code, store_resp.status_code

    async def add_to_cart(
        self,
        facility_id: str,
        config: FacilityConfig,
        slot: TimeSlot,
        number_of_nights: int = 0,
        fee_type: int = 0,
        number_of_attendees: int = 1,
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

        detail_url = f"{FACILITY_DETAIL_URL}?facilityId={facility_id}"
        http = await self._ensure_http()
        csrf_token = await self._fetch_csrf(facility_id, detail_url)

        results = []
        tick_values = slot.base_slot_ticks or [slot.ticks]
        base_duration_ticks = slot.duration_ticks // len(tick_values) if slot.base_slot_ticks else slot.duration_ticks

        for ticks in tick_values:
            v_status, s_status = await self._book_single(
                http, facility_id, config, ticks, base_duration_ticks,
                number_of_nights, fee_type, csrf_token, detail_url,
                number_of_attendees=number_of_attendees,
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
