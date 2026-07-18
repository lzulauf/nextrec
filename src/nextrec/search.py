from typing import List

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, Facility
from nextrec.scrapers.perfectmind import PerfectMindScraper


def search(session: BrowserSession, constraints: Constraint) -> List[Facility]:
    scraper = PerfectMindScraper(session)
    return scraper.search(constraints)
