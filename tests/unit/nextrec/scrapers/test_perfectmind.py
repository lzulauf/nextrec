from datetime import date, time
from unittest.mock import Mock, PropertyMock

import pytest

from nextrec.models import Constraint
from nextrec.scrapers.perfectmind import PerfectMindScraper, ScrapeError


class TestExtractCsrf:
    def test_extracts_token(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        element = Mock()
        element.get_attribute.return_value = "csrf-token-123"
        page.wait_for_selector.return_value = element

        scraper = PerfectMindScraper(session)
        scraper._page = page
        token = scraper._extract_csrf(page)

        assert token == "csrf-token-123"
        page.wait_for_selector.assert_called_once()

    def test_raises_when_element_missing(self):
        session = Mock()
        page = Mock()
        page.wait_for_selector.return_value = None

        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="CSRF token element not found"):
            scraper._extract_csrf(page)

    def test_raises_when_token_empty(self):
        session = Mock()
        page = Mock()
        element = Mock()
        element.get_attribute.return_value = ""
        page.wait_for_selector.return_value = element

        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="CSRF token attribute was empty"):
            scraper._extract_csrf(page)

    def test_raises_on_timeout(self):
        session = Mock()
        page = Mock()
        page.wait_for_selector.side_effect = Exception("timeout")

        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="Failed to extract CSRF token"):
            scraper._extract_csrf(page)


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
        assert payload["EndDate"] == "20260725"
        assert payload["KeyWord"] == "soccer"
        assert payload["FacilityTypes"] == "Field,Court"
        assert payload["MinCapacity"] == "10"
        assert payload["MaxCapacity"] == "50"
        assert payload["TimeWindowStart"] == "08:00"
        assert payload["TimeWindowEnd"] == "18:00"


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


class TestSearch:
    def test_calls_get_facilities_with_csrf_and_headers(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        csrf_element = Mock()
        csrf_element.get_attribute.return_value = "csrf-token"
        page.wait_for_selector.return_value = csrf_element
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"facilities": [], "total": 0}
        page.request.post.return_value = mock_response
        session.manager.new_page.return_value = page

        scraper = PerfectMindScraper(session)
        result = scraper.search(Constraint(keywords="soccer"))

        assert result == []
        page.request.post.assert_called_once()
        call_kwargs = page.request.post.call_args[1]
        assert call_kwargs["headers"]["x-requested-with"] == "XMLHttpRequest"
        assert call_kwargs["headers"]["origin"] == "https://cityofoakland.perfectmind.com"
        assert "csrf-token" in str(call_kwargs["form"]["__RequestVerificationToken"])

    def test_raises_on_http_error(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        csrf_element = Mock()
        csrf_element.get_attribute.return_value = "csrf-token"
        page.wait_for_selector.return_value = csrf_element
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status = 500
        mock_response.status_text = "Internal Server Error"
        page.request.post.return_value = mock_response
        session.manager.new_page.return_value = page

        scraper = PerfectMindScraper(session)
        with pytest.raises(ScrapeError, match="GetFacilities returned 500"):
            scraper.search(Constraint())
