from unittest.mock import Mock

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, Facility
from nextrec.search import search, search_multi


class TestSearch:
    def test_delegates_to_scraper(self, monkeypatch):
        mock_scraper = Mock()
        mock_scraper.search.return_value = [
            Facility(id="1", name="Field", location="Park", type="Field", capacity=10, availability=[])
        ]

        def fake_constructor(session):
            return mock_scraper

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", fake_constructor)

        session = BrowserSession()
        constraints = Constraint(keywords="soccer")
        result = search(session, constraints)

        assert len(result) == 1
        assert result[0].name == "Field"
        mock_scraper.search.assert_called_once_with(constraints)


class TestSearchMulti:
    def test_deduplicates_by_facility_id(self, monkeypatch):
        mock_scraper = Mock()
        results_a = [
            Facility(id="1", name="Field A", location="Park", type="Field", availability=[]),
            Facility(id="2", name="Field B", location="Park", type="Field", availability=[]),
        ]
        results_b = [
            Facility(id="1", name="Field A", location="Park", type="Field", availability=[]),
            Facility(id="3", name="Field C", location="Park", type="Field", availability=[]),
        ]
        mock_scraper.search.side_effect = [results_a, results_b]

        def fake_constructor(session):
            return mock_scraper

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", fake_constructor)

        session = BrowserSession()
        base = Constraint(start_date=None)
        result = search_multi(session, ["keyword1", "keyword2"], base)

        assert len(result) == 3  # 3 unique ids across both keyword queries
        assert {f.id for f in result} == {"1", "2", "3"}
        assert mock_scraper.search.call_count == 2

    def test_empty_keywords(self, monkeypatch):
        mock_scraper = Mock()
        mock_scraper.search.side_effect = [[], []]

        def fake_constructor(session):
            return mock_scraper

        monkeypatch.setattr("nextrec.search.PerfectMindScraper", fake_constructor)

        session = BrowserSession()
        result = search_multi(session, ["", ""], Constraint())
        assert result == []
