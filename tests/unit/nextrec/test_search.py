from datetime import date, time
from unittest.mock import AsyncMock, Mock

import pytest

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, DurationPrice, Facility, FacilityConfig, TimeSlot
from nextrec.search import search, search_and_fetch


def _mock_scraper(search_result, configs, slots, *, override_search=None):
    """Create a mock PerfectMindScraper for testing search_and_fetch."""
    m = Mock()
    m._list_csrf = "fake-csrf"
    m._config_cache = {}

    async def search_fn(constraint):
        return search_result

    async def fetch_config_and_slots_fn(fid, *a, **kw):
        cfg = configs.get(fid, FacilityConfig(
            facility_id=fid, calendar_id="cal-1", service_id="svc-1",
            program_id="svc-1",
            duration_prices=[DurationPrice(id="dur-1", minutes=60, resident_price=5.0, non_resident_price=6.0)],
        ))
        return cfg, slots

    m.search = AsyncMock(side_effect=override_search or search_fn)
    m.fetch_config_and_slots = AsyncMock(side_effect=fetch_config_and_slots_fn)
    m.fetch_list_csrf = AsyncMock(return_value="fake-csrf")
    return m


@pytest.mark.asyncio
class TestSearch:
    async def test_delegates_to_scraper(self, monkeypatch):
        mock_scraper = Mock()
        mock_scraper.search = AsyncMock(return_value=[
            Facility(id="1", name="Field", location="Park", type="Field", capacity=10, availability=[])
        ])

        def fake_constructor(session):
            return mock_scraper

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", fake_constructor)

        session = BrowserSession()
        constraints = Constraint(keywords="soccer")
        result = await search(session, constraints)

        assert len(result) == 1
        assert result[0].name == "Field"
        mock_scraper.search.assert_awaited_once_with(constraints)


@pytest.mark.asyncio
class TestSearchAndFetch:
    async def test_merges_results_across_keywords(self, monkeypatch, make_config, make_slot):
        config_a = make_config("fac-1")
        config_b = make_config("fac-2")
        config_c = make_config("fac-3")
        slot = make_slot(ticks=100)
        configs = {"fac-1": config_a, "fac-2": config_b, "fac-3": config_c}

        def mock_constructor(session, config_cache=None):
            async def search_fn(constraint):
                kw = constraint.keywords
                if kw == "kw1":
                    return [
                        Facility(id="fac-1", name="Alpha", location="", type="", availability=[]),
                        Facility(id="fac-2", name="Beta", location="", type="", availability=[]),
                    ]
                elif kw == "kw2":
                    return [
                        Facility(id="fac-2", name="Beta", location="", type="", availability=[]),
                        Facility(id="fac-3", name="Gamma", location="", type="", availability=[]),
                    ]
                return []

            return _mock_scraper(None, configs, [slot], override_search=search_fn)

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", mock_constructor)

        session = BrowserSession()
        base = Constraint(start_date=date(2026, 7, 20))
        names, results = await search_and_fetch(
            session, ["kw1", "kw2"], base, duration_minutes=60,
        )

        # 3 unique facilities
        assert names == {"fac-1": "Alpha", "fac-2": "Beta", "fac-3": "Gamma"}
        # Slots deduplicated by (fid, ticks)
        assert len(results) == 3

    async def test_handles_keyword_failure(self, monkeypatch, make_config, make_slot):
        config_a = make_config("fac-1")
        slot = make_slot()
        call_count = 0

        def mock_constructor(session, config_cache=None):
            nonlocal call_count

            async def search_fn(constraint):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Keyword search failed")
                return [Facility(id="fac-1", name="Alpha", location="", type="", availability=[])]

            return _mock_scraper(None, {"fac-1": config_a}, [slot], override_search=search_fn)

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", mock_constructor)

        session = BrowserSession()
        base = Constraint(start_date=date(2026, 7, 20))
        names, results = await search_and_fetch(
            session, ["failing", "good"], base, duration_minutes=60,
        )

        # Second keyword should still produce results
        assert names == {"fac-1": "Alpha"}
        assert len(results) == 1

    async def test_deduplicates_duplicate_slots(self, monkeypatch, make_config, make_slot):
        config_a = make_config("fac-1")
        slot = make_slot()

        def mock_constructor(session, config_cache=None):
            return _mock_scraper(
                [Facility(id="fac-1", name="Alpha", location="", type="", availability=[])],
                {"fac-1": config_a},
                [slot, slot],
            )

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", mock_constructor)

        session = BrowserSession()
        base = Constraint(start_date=date(2026, 7, 20))
        names, results = await search_and_fetch(
            session, ["kw"], base, duration_minutes=60,
        )

        # Same slot (same fid + ticks) should be deduplicated
        assert len(results) == 1
