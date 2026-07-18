import logging
from datetime import date, time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from nextrec.browser import BrowserSession
from nextrec.models import AvailabilitySlot, Constraint, Facility

logger = logging.getLogger(__name__)

FACILITY_LIST_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
GET_FACILITIES_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/GetFacilities"
CSRF_SELECTOR = '#AjaxAntiForgeryForm input[name="__RequestVerificationToken"]'


class ScrapeError(Exception):
    """Unexpected page structure or network failure during scraping."""


class PerfectMindScraper:
    def __init__(self, session: BrowserSession):
        self._session = session
        self._page: Optional[Page] = None

    def _ensure_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            self._page = self._session.manager.new_page()
        return self._page

    def _extract_csrf(self, page: Page) -> str:
        try:
            element = page.wait_for_selector(CSRF_SELECTOR, state="attached", timeout=10000)
            if element is None:
                raise ScrapeError("CSRF token element not found on page")
            token = element.get_attribute("value")
            if not token:
                raise ScrapeError("CSRF token attribute was empty")
            return token
        except ScrapeError:
            raise
        except Exception as exc:
            raise ScrapeError(f"Failed to extract CSRF token: {exc}") from exc

    @staticmethod
    def _format_date(d: Optional[date]) -> Optional[str]:
        if d is None:
            return None
        return d.strftime("%Y%m%d")

    def _build_payload(self, constraints: Constraint) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "take": "10",
            "skip": "0",
            "page": "1",
            "pageSize": "10",
            "ShouldCheckAvailability": "true",
        }
        if constraints.keywords:
            payload["KeyWord"] = constraints.keywords
        start = self._format_date(constraints.start_date)
        if start:
            payload["StartDate"] = start
        end = self._format_date(constraints.end_date)
        if end:
            payload["EndDate"] = end
        if constraints.facility_types:
            payload["FacilityTypes"] = ",".join(constraints.facility_types)
        if constraints.min_capacity is not None:
            payload["MinCapacity"] = str(constraints.min_capacity)
        if constraints.max_capacity is not None:
            payload["MaxCapacity"] = str(constraints.max_capacity)
        if constraints.time_window_start:
            payload["TimeWindowStart"] = constraints.time_window_start.strftime("%H:%M")
        if constraints.time_window_end:
            payload["TimeWindowEnd"] = constraints.time_window_end.strftime("%H:%M")
        return payload

    def _parse_facilities(self, raw: Any) -> List[Facility]:
        if not isinstance(raw, dict):
            raise ScrapeError(f"Unexpected response type: {type(raw).__name__}")
        items = raw.get("facilities") or raw.get("Data") or raw.get("data") or raw
        if isinstance(items, dict):
            items = items.get("Items") or items.get("items") or []
        if not isinstance(items, list):
            raise ScrapeError(f"Cannot locate facility list in response: {type(items).__name__}")

        facilities: List[Facility] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            facility = Facility(
                id=str(item.get("ID", item.get("Id", item.get("id", "")))),
                name=str(item.get("Name", item.get("name", ""))),
                location=str(item.get("LocationName", item.get("Location", item.get("location", "")))),
                type=str(item.get("FacilityType", item.get("type", ""))),
                availability=self._parse_availability(item),
            )
            facilities.append(facility)
        return facilities

    def _parse_availability(self, item: dict) -> List[AvailabilitySlot]:
        raw_slots = item.get("Availability", item.get("availability", []))
        if isinstance(raw_slots, (int, bool)):
            return []
        if not isinstance(raw_slots, list):
            return []
        slots: List[AvailabilitySlot] = []
        for slot in raw_slots:
            if not isinstance(slot, dict):
                continue
            slots.append(
                AvailabilitySlot(
                    date=str(slot.get("Date", slot.get("date", ""))),
                    start_time=str(slot.get("StartTime", slot.get("start_time", ""))),
                    end_time=str(slot.get("EndTime", slot.get("end_time", ""))),
                    book_button_selector=slot.get("BookButtonSelector"),
                    item_id=str(slot.get("ItemId", slot.get("item_id", ""))),
                )
            )
        return slots

    def search(self, constraints: Constraint) -> List[Facility]:
        page = self._ensure_page()
        logger.info("Loading facility list page to obtain CSRF token")
        page.goto(FACILITY_LIST_URL, wait_until="networkidle")

        csrf_token = self._extract_csrf(page)
        payload = self._build_payload(constraints)
        payload["__RequestVerificationToken"] = csrf_token
        logger.info("Searching facilities with constraints: %s", payload)

        response = page.request.post(
            GET_FACILITIES_URL,
            form=payload,
            headers={
                "x-requested-with": "XMLHttpRequest",
                "origin": "https://cityofoakland.perfectmind.com",
                "referer": FACILITY_LIST_URL,
            },
        )
        if not response.ok:
            raise ScrapeError(f"GetFacilities returned {response.status}: {response.status_text}")

        raw = response.json()
        logger.debug("Response top-level keys: %s", list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict):
                    logger.debug("  %s keys: %s", k, list(v.keys()))
                elif isinstance(v, list) and v:
                    logger.debug("  %s is a list of length %d", k, len(v))
        facilities = self._parse_facilities(raw)
        logger.info("Found %d facilities", len(facilities))
        return facilities
