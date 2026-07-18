from unittest.mock import Mock

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, Facility
from nextrec.search import search


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
