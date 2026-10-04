from datetime import date, time
from unittest.mock import AsyncMock, Mock

import pytest

from nextrec.models import Constraint, DurationPrice, FacilityConfig, TimeSlot
from nextrec.scrapers.perfectmind import (
    PerfectMindScraper,
    ScrapeError,
    datetime_to_ticks,
    minutes_to_ticks,
    ticks_to_minutes,
    ticks_to_time,
)


class TestExtractCsrf:
    def test_extracts_token(self):
        html = '<form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="csrf-token-123"/></form>'
        assert PerfectMindScraper._extract_csrf_from_html(html) == "csrf-token-123"

    def test_raises_when_not_found(self):
        with pytest.raises(ScrapeError, match="CSRF token not found"):
            PerfectMindScraper._extract_csrf_from_html("<html></html>")


class TestFormatDate:
    def test_formats_date_to_compact(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        assert scraper._format_date(date(2026, 7, 20)) == "20260720"

    def test_returns_none_for_none(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        assert scraper._format_date(None) is None


class TestBuildPayload:
    def test_empty_constraint_has_defaults(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        payload = scraper._build_payload(Constraint())
        assert payload["take"] == "10"
        assert payload["skip"] == "0"
        assert payload["page"] == "1"
        assert payload["pageSize"] == "10"
        assert payload["ShouldCheckAvailability"] == "true"
        assert "KeyWord" not in payload
        assert "StartDate" not in payload

    def test_includes_all_set_fields(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        c = Constraint(
            start_date=date(2026, 7, 20),
            end_date=date(2026, 7, 25),
            keywords="soccer",
            facility_types=["Field", "Court"],
            min_capacity=10,
            max_capacity=50,
            time_window_start=time(8, 0),
            time_window_end=time(18, 0),
        )
        payload = scraper._build_payload(c)
        assert payload["StartDate"] == "20260720"
        assert payload["EndDate"] == "20260726"
        assert payload["KeyWord"] == "soccer"
        assert payload["FacilityTypes"] == "Field,Court"
        assert payload["MinCapacity"] == "10"
        assert payload["MaxCapacity"] == "50"
        assert "TimeWindowStart" not in payload
        assert "TimeWindowEnd" not in payload


class TestParseFacilities:
    def test_parses_facilities_list(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        raw = {
            "facilities": [
                {
                    "ID": "101",
                    "Name": "Soccer Field A",
                    "LocationName": "North Park",
                    "FacilityType": "Field",
                }
            ],
            "total": 1,
        }
        facilities = scraper._parse_facilities(raw)
        assert len(facilities) == 1
        assert facilities[0].id == "101"
        assert facilities[0].name == "Soccer Field A"
        assert facilities[0].location == "North Park"

    def test_parses_legacy_data_items_format(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        raw = {
            "Data": {
                "Items": [
                    {
                        "Id": "101",
                        "Name": "Soccer Field A",
                        "Location": "North Park",
                        "FacilityType": "Field",
                        "Capacity": 22,
                    }
                ]
            }
        }
        facilities = scraper._parse_facilities(raw)
        assert len(facilities) == 1
        assert facilities[0].id == "101"
        assert facilities[0].name == "Soccer Field A"
        assert facilities[0].capacity == 22

    def test_parses_lowercase_keys(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        raw = {
            "facilities": [
                {
                    "id": "202",
                    "name": "Tennis Court 1",
                    "location": "Tennis Center",
                    "type": "Court",
                }
            ]
        }
        facilities = scraper._parse_facilities(raw)
        assert len(facilities) == 1
        assert facilities[0].id == "202"
        assert facilities[0].type == "Court"

    def test_handles_empty_response(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        assert scraper._parse_facilities({"facilities": []}) == []
        assert scraper._parse_facilities({"Data": {"Items": []}}) == []

    def test_skips_invalid_items(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        raw = {"facilities": [{"ID": "1", "Name": "Valid"}, None, "string"]}
        facilities = scraper._parse_facilities(raw)
        assert len(facilities) == 1

    def test_raises_on_unexpected_response_type(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="Unexpected response"):
            scraper._parse_facilities("not_a_dict")


class TestParseAvailability:
    def test_parses_availability_from_item(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        item = {
            "Availability": [
                {"Date": "2026-07-20", "StartTime": "09:00", "EndTime": "11:00", "ItemId": "slot-1"},
                {"Date": "2026-07-20", "StartTime": "14:00", "EndTime": "16:00"},
            ]
        }
        slots = scraper._parse_availability(item)
        assert len(slots) == 2
        assert slots[0].date == "2026-07-20"
        assert slots[0].item_id == "slot-1"
        assert slots[1].start_time == "14:00"
        assert slots[1].end_time == "16:00"

    def test_returns_empty_list_when_missing(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        assert scraper._parse_availability({}) == []
        assert scraper._parse_availability({"Availability": None}) == []


@pytest.mark.asyncio
class TestSearch:
    async def test_calls_get_facilities_with_csrf_and_headers(self):
        session, client = _common_mocks()
        client.get = AsyncMock(return_value=make_mock_response(text="""<html><body>
<form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="csrf-token"/></form>
</body></html>"""))
        client.post = AsyncMock(return_value=make_mock_response(json_data={"facilities": [], "total": 0}))
        scraper = PerfectMindScraper(session)
        result = await scraper.search(Constraint(keywords="soccer"))

        assert result == []
        client.post.assert_awaited_once()
        call_kwargs = client.post.call_args[1]
        assert call_kwargs["headers"]["x-requested-with"] == "XMLHttpRequest"
        assert call_kwargs["headers"]["origin"] == "https://cityofoakland.perfectmind.com"
        assert "csrf-token" in str(call_kwargs["data"])

    async def test_raises_on_http_error(self):
        session, client = _common_mocks()
        client.get = AsyncMock(return_value=make_mock_response(text="""<html><body>
<form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="csrf-token"/></form>
</body></html>"""))
        client.post = AsyncMock(return_value=make_mock_response(ok=False))
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="GetFacilities"):
            await scraper.search(Constraint())


class TestTicksConversions:
    def test_ticks_to_time(self):
        t = ticks_to_time(36000000000)
        assert t == time(1, 0)

    def test_ticks_to_time_midnight(self):
        t = ticks_to_time(0)
        assert t == time(0, 0)

    def test_ticks_to_minutes(self):
        assert ticks_to_minutes(36000000000) == 60
        assert ticks_to_minutes(18000000000) == 30
        assert ticks_to_minutes(0) == 0

    def test_minutes_to_ticks(self):
        assert minutes_to_ticks(60) == 36000000000
        assert minutes_to_ticks(30) == 18000000000
        assert minutes_to_ticks(0) == 0

    def test_datetime_to_ticks(self):
        from datetime import datetime
        dt = datetime(1, 1, 1, 1, 0, 0)
        assert datetime_to_ticks(dt) == minutes_to_ticks(60)

    def test_roundtrip(self):
        t = time(14, 30)
        ticks = 14 * 36000000000 + 30 * 600000000
        assert ticks_to_time(ticks) == t
        expected_minutes = 14 * 60 + 30
        assert ticks_to_minutes(ticks) == expected_minutes
        assert minutes_to_ticks(expected_minutes) == expected_minutes * 600_000_000


class TestParseSlotsResponse:
    def test_parses_slots(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        dp = DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0)
        config = FacilityConfig(
            facility_id="f1", calendar_id="c1", service_id="s1", program_id="s1",
            duration_prices=[dp],
        )
        raw = {
            "availabilities": [
                {
                    "Date": "/Date(1721358000000)/",
                    "BookingGroups": [
                        {
                            "Name": "Morning",
                            "Order": 0,
                            "AvailableSpots": [
                                {"Ticks": 324000000000, "IsDisabled": False, "Title": "Reserve"},
                                {"Ticks": 360000000000, "IsDisabled": True, "Title": "Unavailable"},
                            ],
                        }
                    ],
                }
            ]
        }
        slots = scraper._parse_slots_response(raw, config, 60)
        assert len(slots) == 2
        assert slots[0].duration_minutes == 60
        assert not slots[0].is_disabled
        assert slots[0].title == "Reserve"
        assert slots[1].is_disabled
        assert slots[1].title == "Unavailable"

    def test_empty_response(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        dp = DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0)
        config = FacilityConfig(
            facility_id="f1", calendar_id="c1", service_id="s1", program_id="s1",
            duration_prices=[dp],
        )
        assert scraper._parse_slots_response({"availabilities": []}, config, 60) == []
        assert scraper._parse_slots_response({}, config, 60) == []

    def test_handles_missing_fields(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        dp = DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0)
        config = FacilityConfig(
            facility_id="f1", calendar_id="c1", service_id="s1", program_id="s1",
            duration_prices=[dp],
        )
        raw = {
            "availabilities": [
                {
                    "Date": "/Date(1721358000000)/",
                    "BookingGroups": [
                        {"Name": "Morning", "Order": 0, "AvailableSpots": [{}]}
                    ],
                }
            ]
        }
        slots = scraper._parse_slots_response(raw, config, 60)
        assert len(slots) == 0

    def test_skips_invalid_entries(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        dp = DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0)
        config = FacilityConfig(
            facility_id="f1", calendar_id="c1", service_id="s1", program_id="s1",
            duration_prices=[dp],
        )
        raw = {
            "availabilities": [
                {"Date": "/Date(1721358000000)/", "BookingGroups": [{"AvailableSpots": [None, {"Ticks": "string", "IsDisabled": False}]}]}
            ]
        }
        slots = scraper._parse_slots_response(raw, config, 60)
        assert len(slots) == 0

    def test_raises_on_non_dict_slot_response(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="Unexpected slots response"):
            scraper._parse_slots_response("not_a_dict", Mock(), 60)

    def test_raises_on_non_list_availabilities(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="'availabilities' is not a list"):
            scraper._parse_slots_response({"availabilities": "bad"}, Mock(), 60)


class TestParseDateMicrosoft:
    def test_parses_valid_date(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        d = scraper._parse_date_microsoft("/Date(1721358000000)/")
        assert isinstance(d, date)

    def test_raises_on_invalid(self):
        session = Mock()
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="Cannot parse Microsoft date"):
            scraper._parse_date_microsoft("not-a-date")


class TestExtractServicesJson:
    def test_extracts_from_html(self):
        html = """
<html><body><script>
var viewModel = new MainViewModel({
    facilityId: 'abc',
    services: [{"ID": "svc-1", "Calendars": [{"Id": "cal-1"}], "Durations": [{"Duration": 60, "DurationIDs": ["dur-1", "dur-2"], "Prices": [{"Id": "dur-1", "Name": "Hourly Rental: Resident", "Amount": 10.0}, {"Id": "dur-2", "Name": "Hourly Rental: Non-Resident", "Amount": 12.0}]}]}]
});
</script></body></html>
"""
        services = PerfectMindScraper._extract_services_json(html)
        assert services is not None
        assert len(services) == 1
        assert services[0]["ID"] == "svc-1"

    def test_returns_none_when_not_found(self):
        assert PerfectMindScraper._extract_services_json("<html><body>no viewmodel here</body></html>") is None


from tests.conftest import make_mock_response


def _common_mocks(facility_html: str = ""):
    """Create common session/http mocks for fetch_config_and_slots tests."""
    session = Mock()
    mock_client = Mock()
    list_page_html = '<html><body><form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="list-csrf"/></form></body></html>'

    async def _get(url, **kw):
        if "Facility" in url and "List" not in url:
            return make_mock_response(text=facility_html or _SERVICES_HTML)
        return make_mock_response(text=list_page_html)

    mock_client.get = _get
    mock_client.post = AsyncMock()
    session.get_httpx_client = AsyncMock(return_value=mock_client)
    return session, mock_client


_SERVICES_HTML = """
<html><body><script>
new MainViewModel({
    facilityId: 'fac-1',
    services: [{"ID": "svc-1", "Calendars": [{"Id": "cal-1"}], "Durations": [{"Duration": 60, "DurationIDs": ["dur-1", "dur-2"], "Prices": [{"Id": "dur-1", "Name": "Hourly Rental: Resident", "Amount": 10.0}, {"Id": "dur-2", "Name": "Hourly Rental: Non-Resident", "Amount": 12.0}]}]}]
});
</script></body></html>
"""


@pytest.mark.asyncio
class TestFetchConfigAndSlots:
    async def test_returns_config_and_slots(self):
        session, client = _common_mocks(facility_html=_SERVICES_HTML)
        client.post = AsyncMock(return_value=make_mock_response(json_data={
            "availabilities": [
                {
                    "Date": "/Date(1721358000000)/",
                    "BookingGroups": [
                        {"Name": "Morning", "Order": 0,
                         "AvailableSpots": [{"Ticks": 324000000000, "IsDisabled": False, "Title": "Reserve"}]}
                    ],
                }
            ]
        }))
        scraper = PerfectMindScraper(session)
        config, slots = await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19), days_count=7, duration_minutes=60)
        assert config.facility_id == "fac-1"
        assert config.calendar_id == "cal-1"
        assert config.service_id == "svc-1"
        assert len(config.duration_prices) == 1
        assert config.duration_prices[0].minutes == 60
        assert config.duration_prices[0].resident_price == 10.0
        assert len(slots) == 1
        assert not slots[0].is_disabled

    async def test_raises_on_missing_services(self):
        session, client = _common_mocks(facility_html="<html><body>no data</body></html>")
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="Could not extract services config"):
            await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19))

    async def test_raises_on_missing_calendar(self):
        session, client = _common_mocks(facility_html="""
<html><body><script>
new MainViewModel({services: [{"ID": "svc-1", "Calendars": [], "Durations": []}]});
</script></body></html>
""")
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="missing Calendars"):
            await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19))

    async def test_raises_on_slot_http_error(self):
        session, client = _common_mocks(facility_html=_SERVICES_HTML)
        client.post = AsyncMock(return_value=make_mock_response(ok=False))
        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="FacilityAvailability"):
            await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19))

    async def test_config_cache_prevents_second_get(self):
        session, client = _common_mocks(facility_html=_SERVICES_HTML)
        client.post = AsyncMock(return_value=make_mock_response(json_data={"availabilities": []}))
        scraper = PerfectMindScraper(session)
        await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19))

        # Track get calls by wrapping
        get_call_count = 0
        orig_get = client.get
        async def counting_get(*a, **kw):
            nonlocal get_call_count
            get_call_count += 1
            return await orig_get(*a, **kw)
        client.get = counting_get

        config, slots = await scraper.fetch_config_and_slots("fac-1", date(2026, 7, 19))
        # Cache hit: should NOT fetch facility HTML again (no get calls)
        assert get_call_count == 0


class TestResolveDuration:
    def test_exact_match(self):
        dps = [DurationPrice(id="a", minutes=30, resident_price=0, non_resident_price=0)]
        assert PerfectMindScraper._resolve_duration(dps, 30) == 30

    def test_divisible_match(self):
        dps = [DurationPrice(id="a", minutes=30, resident_price=0, non_resident_price=0)]
        assert PerfectMindScraper._resolve_duration(dps, 60) == 30

    def test_largest_divisible(self):
        dps = [
            DurationPrice(id="a", minutes=30, resident_price=0, non_resident_price=0),
            DurationPrice(id="b", minutes=15, resident_price=0, non_resident_price=0),
        ]
        assert PerfectMindScraper._resolve_duration(dps, 60) == 30

    def test_no_match_uses_smallest(self):
        dps = [DurationPrice(id="a", minutes=30, resident_price=0, non_resident_price=0)]
        assert PerfectMindScraper._resolve_duration(dps, 45) == 30

    def test_empty_falls_back_to_requested(self):
        assert PerfectMindScraper._resolve_duration([], 60) == 60


class TestGroupSlots:
    def _slot(self, ticks: int, disabled: bool = False) -> TimeSlot:
        return TimeSlot(
            date=date(2026, 7, 20),
            start_time=time(11, 0),
            end_time=time(11, 30),
            ticks=ticks,
            duration_minutes=30,
            duration_ticks=18_000_000_000,
            is_disabled=disabled,
        )

    def test_groups_consecutive_30min_into_60min(self):
        base = 18_000_000_000
        slots = [self._slot(i * base) for i in range(4)]
        grouped = PerfectMindScraper._group_slots(slots, 30, 60)
        assert len(grouped) == 3
        assert grouped[0].duration_minutes == 60
        assert grouped[0].base_slot_ticks == [0, base]
        assert grouped[1].base_slot_ticks == [base, 2 * base]
        assert grouped[2].base_slot_ticks == [2 * base, 3 * base]

    def test_skips_non_consecutive_slots(self):
        slots = [self._slot(0), self._slot(50_000_000_000)]
        grouped = PerfectMindScraper._group_slots(slots, 30, 60)
        assert len(grouped) == 0

    def test_no_grouping_when_base_equals_target(self):
        slots = [self._slot(0)]
        grouped = PerfectMindScraper._group_slots(slots, 60, 60)
        assert len(grouped) == 1
        assert grouped[0].base_slot_ticks is None

    def test_marks_group_disabled_if_any_base_disabled(self):
        base = 18_000_000_000
        slots = [self._slot(0), self._slot(base, disabled=True)]
        grouped = PerfectMindScraper._group_slots(slots, 30, 60)
        assert len(grouped) == 1
        assert grouped[0].is_disabled
