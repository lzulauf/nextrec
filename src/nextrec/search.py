import asyncio
import logging
from datetime import date, time
from typing import Dict, List, Optional, Tuple

from nextrec.browser import BrowserSession
from nextrec.models import Constraint, FacilityConfig, TimeSlot
from nextrec.scrapers.perfectmind import PerfectMindScraper

logger = logging.getLogger(__name__)

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


async def search(session: BrowserSession, constraints: Constraint) -> List:
    scraper = PerfectMindScraper(session)
    return await scraper.search(constraints)


async def search_and_fetch(
    session: BrowserSession,
    keywords: List[str],
    base: Constraint,
    duration_minutes: int,
    days_count: int = 7,
    end_date: Optional[date] = None,
    time_window_start: Optional[time] = None,
    time_window_end: Optional[time] = None,
    max_concurrent_searches: int = 3,
    max_concurrent_fetches: int = 4,
) -> Tuple[Dict[str, str], List[SlotInfo]]:
    """Pipeline keyword searches and facility config/slot fetches.

    Each keyword runs its own pipeline: search → fetch config+slots for
    every facility returned.  Pipelines for different keywords run
    concurrently so facility work starts as soon as its keyword search
    finishes, without waiting for other keywords.

    Returns (facility_names, slot_info_list).
    """
    search_sem = asyncio.Semaphore(max_concurrent_searches)
    fetch_sem = asyncio.Semaphore(max_concurrent_fetches)

    async def pipeline_one(kw: str):
        async with search_sem:
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
            facilities = await scraper.search(c)

        async def fetch_facility(f):
            async with fetch_sem:
                scraper = PerfectMindScraper(session)
                config = await scraper.fetch_config(f.id)
                slots = await scraper.fetch_slots(
                    f.id,
                    base.start_date or date.today(),
                    config,
                    days_count=days_count,
                    duration_minutes=duration_minutes,
                    end_date=end_date,
                    time_window_start=time_window_start,
                    time_window_end=time_window_end,
                )
                return f.id, f.name, config, slots

        results = await asyncio.gather(
            *[fetch_facility(f) for f in facilities],
            return_exceptions=True,
        )

        kw_names = {}
        kw_results = []
        for r in results:
            if isinstance(r, Exception):
                continue
            fid, name, config, slots = r
            kw_names[fid] = name
            for s in slots:
                if not s.is_disabled:
                    kw_results.append((fid, config, s))
        return kw_names, kw_results

    task_results = await asyncio.gather(
        *[pipeline_one(kw) for kw in keywords],
        return_exceptions=True,
    )

    all_names = {}
    all_results = []
    seen_slots = set()

    for r in task_results:
        if isinstance(r, Exception):
            logger.warning("Keyword pipeline failed: %s", r)
            continue
        names, slots = r
        all_names.update(names)
        for slot_info in slots:
            fid, cfg, slot = slot_info
            key = f"{fid}_{slot.ticks}"
            if key not in seen_slots:
                seen_slots.add(key)
                all_results.append(slot_info)

    all_results.sort(key=lambda x: (x[2].date, x[2].start_time))
    return all_names, all_results
