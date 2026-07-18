from typing import List

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, Facility
from nextrec.scrapers.perfectmind import PerfectMindScraper


def search(session: BrowserSession, constraints: Constraint) -> List[Facility]:
    scraper = PerfectMindScraper(session)
    return scraper.search(constraints)


def search_multi(session: BrowserSession, keywords: List[str], base: Constraint) -> List[Facility]:
    seen: set[str] = set()
    results: List[Facility] = []

    for kw in keywords:
        c = Constraint(
            start_date=base.start_date,
            end_date=base.end_date,
            time_window_start=base.time_window_start,
            time_window_end=base.time_window_end,
            keywords=kw,
            facility_types=base.facility_types,
            min_capacity=base.min_capacity,
            max_capacity=base.max_capacity,
        )
        scraper = PerfectMindScraper(session)
        facilities = scraper.search(c)
        for f in facilities:
            if f.id not in seen:
                seen.add(f.id)
                results.append(f)

    return results
