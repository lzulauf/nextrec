import logging
import re
import urllib.parse
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx2

from nextrec.browser import BrowserSession
from nextrec.models import (
    AvailabilitySlot,
    Constraint,
    DurationPrice,
    Facility,
    FacilityConfig,
    TimeSlot,
)

logger = logging.getLogger(__name__)

FACILITY_LIST_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
GET_FACILITIES_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/GetFacilities"
FACILITY_DETAIL_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/Facility"
FACILITY_AVAILABILITY_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4LandingPages/FacilityAvailability"

_DOTNET_EPOCH = datetime(1, 1, 1)

_COMMON_DURATIONS = {
    30: 18_000_000_000,       # 30 min in ticks
    60: 36_000_000_000,       # 60 min
    90: 54_000_000_000,       # 90 min
    120: 72_000_000_000,      # 120 min
    150: 90_000_000_000,      # 150 min
    180: 108_000_000_000,     # 180 min
}


def ticks_to_time(ticks: int) -> time:
    delta = timedelta(seconds=ticks / 10_000_000)
    return (_DOTNET_EPOCH + delta).time()


def ticks_to_minutes(ticks: int) -> int:
    return int(ticks / 10_000_000 / 60)


def minutes_to_ticks(minutes: int) -> int:
    return minutes * 600_000_000


def datetime_to_ticks(dt: datetime) -> int:
    delta = dt - _DOTNET_EPOCH
    return int(delta.total_seconds() * 10_000_000)


class ScrapeError(Exception):
    """Unexpected page structure or network failure during scraping."""


class PerfectMindScraper:
    def __init__(self, session: BrowserSession, config_cache: Optional[Dict[str, FacilityConfig]] = None):
        self._session = session
        self._http: Optional[httpx2.AsyncClient] = None
        self._config_cache: Dict[str, FacilityConfig] = config_cache if config_cache is not None else {}
        self._list_csrf: Optional[str] = None

    async def _ensure_http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = await self._session.get_httpx_client()
        return self._http

    async def _fetch_html(self, url: str) -> str:
        http = await self._ensure_http()
        try:
            resp = await http.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx2.HTTPStatusError as e:
            raise ScrapeError(f"HTTP {e.response.status_code} fetching {url}") from e

    @staticmethod
    def _extract_csrf_from_html(html: str) -> str:
        m = re.search(r'name="__RequestVerificationToken".*?value="([^"]*)"', html)
        if m:
            return m.group(1)
        raise ScrapeError("CSRF token not found in HTML")

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
        if constraints.end_date:
            payload["EndDate"] = self._format_date(constraints.end_date + timedelta(days=1))
        if constraints.facility_types:
            payload["FacilityTypes"] = ",".join(constraints.facility_types)
        if constraints.min_capacity is not None:
            payload["MinCapacity"] = str(constraints.min_capacity)
        if constraints.max_capacity is not None:
            payload["MaxCapacity"] = str(constraints.max_capacity)
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
            raw_cap = item.get("Capacity", item.get("capacity"))
            cap: Optional[int] = None
            if raw_cap is not None:
                try:
                    cap = int(raw_cap)
                except (ValueError, TypeError):
                    pass
            facility = Facility(
                id=str(item.get("ID", item.get("Id", item.get("id", "")))),
                name=str(item.get("Name", item.get("name", ""))),
                location=str(item.get("LocationName", item.get("Location", item.get("location", "")))),
                type=str(item.get("FacilityType", item.get("type", ""))),
                availability=self._parse_availability(item),
                capacity=cap,
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

    @staticmethod
    def _extract_services_json(html: str) -> Optional[list]:
        idx = html.find("new MainViewModel({")
        if idx < 0:
            return None
        svc_idx = html.find("services: [", idx)
        if svc_idx < 0:
            return None
        start = svc_idx + len("services: ")
        depth = 0
        in_string = False
        escape = False
        i = start
        while i < len(html):
            c = html[i]
            if escape:
                escape = False
            elif c == "\\" and in_string:
                escape = True
            elif c == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
            i += 1
        raw_json = html[start:i]
        try:
            import json as _json
            return _json.loads(raw_json)
        except Exception:
            return None

    @staticmethod
    def _parse_date_microsoft(ms_date_str: str) -> date:
        m = re.match(r"/Date\((\d+)\)/", ms_date_str)
        if not m:
            raise ScrapeError(f"Cannot parse Microsoft date: {ms_date_str!r}")
        ms = int(m.group(1))
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()

    def _parse_slots_response(self, raw: Any, config: FacilityConfig, duration_minutes: int) -> List[TimeSlot]:
        if not isinstance(raw, dict):
            raise ScrapeError(f"Unexpected slots response type: {type(raw).__name__}")

        availabilities = raw.get("availabilities") or []
        if not isinstance(availabilities, list):
            raise ScrapeError(f"'availabilities' is not a list: {type(availabilities).__name__}")

        duration_ticks = minutes_to_ticks(duration_minutes)
        slots: List[TimeSlot] = []

        for entry in availabilities:
            if not isinstance(entry, dict):
                continue
            raw_date = entry.get("Date", "")
            try:
                slot_date = self._parse_date_microsoft(raw_date)
            except ScrapeError:
                logger.warning("Skipping entry with unparseable date: %s", raw_date)
                continue

            booking_groups = entry.get("BookingGroups") or []
            for group in booking_groups:
                if not isinstance(group, dict):
                    continue
                spots = group.get("AvailableSpots") or []
                for spot in spots:
                    if not isinstance(spot, dict):
                        continue
                    ticks = spot.get("Ticks")
                    if not isinstance(ticks, int):
                        continue
                    is_disabled = bool(spot.get("IsDisabled", False))
                    title = str(spot.get("Title", "Reserve"))

                    start_dt = _DOTNET_EPOCH + timedelta(seconds=ticks / 10_000_000)
                    start_t = start_dt.time()
                    end_dt = start_dt + timedelta(seconds=duration_ticks / 10_000_000)
                    end_t = end_dt.time()

                    slots.append(
                        TimeSlot(
                            date=slot_date,
                            start_time=start_t,
                            end_time=end_t,
                            ticks=ticks,
                            duration_minutes=duration_minutes,
                            duration_ticks=duration_ticks,
                            is_disabled=is_disabled,
                            title=title,
                        )
                    )

        return slots

    @staticmethod
    def _resolve_duration(duration_prices: List[DurationPrice], requested_minutes: int) -> int:
        available = sorted({dp.minutes for dp in duration_prices})
        if requested_minutes in available:
            return requested_minutes
        for base in reversed(available):
            if requested_minutes % base == 0:
                return base
        return available[0] if available else requested_minutes

    @staticmethod
    def _group_slots(slots: List[TimeSlot], base_minutes: int, target_minutes: int) -> List[TimeSlot]:
        if base_minutes >= target_minutes:
            return slots
        step = base_minutes * 600_000_000
        group_count = target_minutes // base_minutes
        grouped = []
        sorted_slots = sorted(slots, key=lambda s: s.ticks)
        i = 0
        while i <= len(sorted_slots) - group_count:
            group = sorted_slots[i:i + group_count]
            is_consecutive = all(
                group[j + 1].ticks - group[j].ticks == step
                for j in range(group_count - 1)
            )
            if is_consecutive:
                first = group[0]
                start_dt = _DOTNET_EPOCH + timedelta(seconds=first.ticks / 10_000_000)
                end_dt = start_dt + timedelta(seconds=minutes_to_ticks(target_minutes) / 10_000_000)
                grouped.append(TimeSlot(
                    date=first.date,
                    start_time=start_dt.time(),
                    end_time=end_dt.time(),
                    ticks=first.ticks,
                    duration_minutes=target_minutes,
                    duration_ticks=minutes_to_ticks(target_minutes),
                    is_disabled=any(s.is_disabled for s in group),
                    title=first.title,
                    base_slot_ticks=[s.ticks for s in group],
                ))
                i += 1
            else:
                i += 1
        return grouped

    async def fetch_list_csrf(self) -> str:
        if self._list_csrf:
            return self._list_csrf
        logger.info("Loading facility list page to obtain CSRF token")
        html = await self._fetch_html(FACILITY_LIST_URL)
        csrf = self._extract_csrf_from_html(html)
        self._list_csrf = csrf
        return csrf

    async def fetch_config_and_slots(
        self,
        facility_id: str,
        target_date: date,
        days_count: int = 7,
        duration_minutes: int = 60,
        end_date: Optional[date] = None,
        time_window_start: Optional[time] = None,
        time_window_end: Optional[time] = None,
    ) -> tuple[FacilityConfig, List[TimeSlot]]:
        if facility_id in self._config_cache:
            config = self._config_cache[facility_id]
            logger.info("Using cached config for facility %s", facility_id)
        else:
            url = f"{FACILITY_DETAIL_URL}?facilityId={facility_id}"
            logger.info("Fetching facility config from %s", url)
            html = await self._fetch_html(url)

            services = self._extract_services_json(html)
            if not services or not isinstance(services, list) or len(services) == 0:
                raise ScrapeError(
                    f"Could not extract services config from facility detail page for {facility_id}."
                )

            svc = services[0]
            service_id = svc.get("ID") or svc.get("Id")
            if not service_id:
                raise ScrapeError(f"Facility config missing service ID for {facility_id}")

            calendars = svc.get("Calendars") or []
            if not calendars:
                raise ScrapeError(f"Facility config missing Calendars for {facility_id}")
            calendar_id = calendars[0].get("Id") if isinstance(calendars[0], dict) else None
            if not calendar_id:
                raise ScrapeError(f"Facility config missing calendarId for {facility_id}")

            durations: List[DurationPrice] = []
            for d in svc.get("Durations") or []:
                if not isinstance(d, dict):
                    continue
                dur_minutes = int(d.get("Duration") or d.get("duration") or 60)
                duration_ids = d.get("DurationIDs") or d.get("durationIDs") or []
                prices = d.get("Prices") or []
                resident_price = 0.0
                non_resident_price = 0.0
                for p in prices:
                    if not isinstance(p, dict):
                        continue
                    pname = (p.get("Name") or "").lower()
                    amount = float(p.get("Amount", 0))
                    if "non-resident" in pname or "nonresident" in pname:
                        non_resident_price = amount
                    elif "resident" in pname:
                        resident_price = amount
                dur_id = duration_ids[0] if duration_ids else ""
                durations.append(DurationPrice(
                    id=dur_id, minutes=dur_minutes,
                    resident_price=resident_price, non_resident_price=non_resident_price,
                ))

            config = FacilityConfig(
                facility_id=facility_id, calendar_id=calendar_id,
                service_id=service_id, program_id=service_id,
                duration_prices=durations,
            )
            self._config_cache[facility_id] = config

        # Now fetch slots via httpx2
        if end_date and end_date >= target_date:
            api_end = end_date + timedelta(days=1)
            days_count = (api_end - target_date).days

        base_minutes = self._resolve_duration(config.duration_prices, duration_minutes)
        logger.info(
            "Fetching slots for facility %s %s to %s, %d days, %d min (base=%d)",
            facility_id, target_date,
            end_date or target_date, days_count, duration_minutes, base_minutes,
        )

        csrf_token = await self.fetch_list_csrf()
        date_iso = target_date.strftime("%Y-%m-%dT00:00:00.000Z")
        base_ids = [dp.id for dp in config.duration_prices if dp.minutes == base_minutes]
        api_ids = base_ids or [dp.id for dp in config.duration_prices]

        form_data: List[tuple] = [
            ("facilityId", facility_id),
            ("date", date_iso),
            ("daysCount", str(days_count)),
            ("duration", str(base_minutes)),
            ("serviceId", config.service_id),
            ("__RequestVerificationToken", csrf_token),
        ]
        for did in api_ids:
            form_data.append(("durationIds[]", did))

        try:
            http = await self._ensure_http()
            response = await http.post(
                FACILITY_AVAILABILITY_URL,
                data=urllib.parse.urlencode(form_data, doseq=True),
                headers={
                    "x-requested-with": "XMLHttpRequest",
                    "origin": "https://cityofoakland.perfectmind.com",
                    "referer": f"{FACILITY_DETAIL_URL}?facilityId={facility_id}",
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            response.raise_for_status()
            raw = response.json()
        except httpx2.HTTPStatusError as e:
            self._config_cache.pop(facility_id, None)
            raise ScrapeError(f"FacilityAvailability returned {e.response.status_code}") from e
        slots = self._parse_slots_response(raw, config, base_minutes)
        slots = self._group_slots(slots, base_minutes, duration_minutes)
        if end_date:
            slots = [s for s in slots if target_date <= s.date <= end_date]
        if time_window_start and time_window_end:
            if time_window_start < time_window_end:
                slots = [s for s in slots if s.start_time >= time_window_start and s.end_time <= time_window_end]
            else:
                logger.warning(
                    "Time window end %s < start %s — overnight filter not yet supported, skipping",
                    time_window_end, time_window_start,
                )
        elif time_window_start:
            slots = [s for s in slots if s.start_time >= time_window_start]
        elif time_window_end:
            slots = [s for s in slots if s.end_time <= time_window_end]
        return config, slots

    async def search(self, constraints: Constraint) -> List[Facility]:
        csrf_token = await self.fetch_list_csrf()
        payload = self._build_payload(constraints)
        payload["__RequestVerificationToken"] = csrf_token
        logger.info("Searching facilities with constraints: %s", payload)

        http = await self._ensure_http()
        try:
            response = await http.post(
                GET_FACILITIES_URL,
                data=urllib.parse.urlencode(payload, doseq=True),
                headers={
                    "x-requested-with": "XMLHttpRequest",
                    "origin": "https://cityofoakland.perfectmind.com",
                    "referer": FACILITY_LIST_URL,
                    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
            response.raise_for_status()
            raw = response.json()
        except httpx2.HTTPStatusError as e:
            raise ScrapeError(f"GetFacilities returned {e.response.status_code}") from e
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
