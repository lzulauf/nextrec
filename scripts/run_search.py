#!/usr/bin/env python3
"""Test the PerfectMind search/scraper against the live Oakland site.

Usage:
  python scripts/run_search.py --keywords soccer --headed
  python scripts/run_search.py --storage-state docs/discovery/storage_state.json
  python scripts/run_search.py --inspect --storage-state session_state.json
"""

import argparse
import json
import logging
import sys
from datetime import date, time

from nextrec.browser import BrowserSession, find_system_chrome
from nextrec.models import Constraint
from nextrec.scrapers.perfectmind import (
    FACILITY_LIST_URL,
    GET_FACILITIES_URL,
    PerfectMindScraper,
    ScrapeError,
)


def parse_date(s: str) -> date:
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError(f"Expected YYYY-MM-DD, got {s!r}")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def parse_time(s: str) -> time:
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {s!r}")
    return time(int(parts[0]), int(parts[1]))


def do_inspect(session: BrowserSession) -> None:
    page = session.manager.new_page()

    page.goto(FACILITY_LIST_URL, wait_until="networkidle")

    entries = []

    def on_request(req):
        entries.append({"type": "request", "url": req.url, "method": req.method})

    def on_response(resp):
        if "GetFacilities" in resp.url:
            try:
                body = resp.json()
                entries.append({"type": "response", "url": resp.url, "status": resp.status, "body": body})
            except Exception:
                entries.append({"type": "response", "url": resp.url, "status": resp.status, "body": None})

    print("=" * 60)
    print("Headed browser is open on the facility list page.")
    print("Use the search UI to perform your search manually.")
    print("After searching, press Enter here to show captured results.")
    print("=" * 60)

    page.on("request", on_request)
    page.on("response", on_response)

    input()
    page.on("request", None)
    page.on("response", None)

    if entries:
        print(f"\nCaptured {len(entries)} events after initial load:\n")
        for e in entries:
            if e["type"] == "request":
                print(f"  REQ {e['method']} {e['url']}")
            else:
                status = e["status"]
                url = e["url"]
                body = e["body"]
                if body is not None:
                    total = body.get("total", "?")
                    n_facilities = len(body.get("facilities") or [])
                    print(f"  RESP {status} {url}  total={total} facilities={n_facilities}")
                else:
                    print(f"  RESP {status} {url} (no JSON)")

        get_fac = [e for e in entries if e["type"] == "request" and "GetFacilities" in e["url"]]
        if get_fac:
            print(f"\nGetFacilities requests found: {len(get_fac)}")
            for e in get_fac:
                print(f"  {e['method']} {e['url']}")
            print("\nThe search may be sending keyword via a different mechanism.")
        else:
            print("\nNo GetFacilities requests during user interaction.")
            print("The search is likely filtering results client-side in JavaScript.")
            if entries:
                print("\nAll captured events listed above — check what endpoints were called.")
    else:
        print("\nNo requests or responses were captured after initial load.")

    page.close()


def main():
    parser = argparse.ArgumentParser(description="Test PerfectMind facility search")
    parser.add_argument("--keywords", default=None, help="Search keywords (e.g. soccer, tennis)")
    parser.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--time-window-start", default=None, help="Start time (HH:MM)")
    parser.add_argument("--time-window-end", default=None, help="End time (HH:MM)")
    parser.add_argument("--min-capacity", type=int, default=None, help="Minimum capacity")
    parser.add_argument("--max-capacity", type=int, default=None, help="Maximum capacity")
    parser.add_argument("--storage-state", default=None, help="Path to saved Playwright storage state JSON")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    parser.add_argument("--chrome-path", default=None, help="Explicit path to Chrome executable")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--inspect", action="store_true", help="Open browser for manual search and capture the request/response")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging including network requests")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    chrome_path = args.chrome_path or find_system_chrome()
    if not chrome_path:
        print("ERROR: Chrome executable not found. Provide --chrome-path or install Chrome.")
        sys.exit(1)

    session = BrowserSession(chrome_path=chrome_path, headless=not args.headed)
    session.start()
    if args.storage_state:
        session.manager.load_storage_state(args.storage_state)

    if args.inspect:
        do_inspect(session)
        session.stop()
        return

    constraints = Constraint(
        keywords=args.keywords,
        start_date=parse_date(args.start_date) if args.start_date else None,
        end_date=parse_date(args.end_date) if args.end_date else None,
        time_window_start=parse_time(args.time_window_start) if args.time_window_start else None,
        time_window_end=parse_time(args.time_window_end) if args.time_window_end else None,
        min_capacity=args.min_capacity,
        max_capacity=args.max_capacity,
    )

    print(f"Constraints: {constraints}")
    print(f"Browser: {'headed' if args.headed else 'headless'}")
    if args.storage_state:
        print(f"Storage state: {args.storage_state}")
    print()

    scraper = PerfectMindScraper(session)
    try:
        facilities = scraper.search(constraints)
    except ScrapeError as e:
        print(f"ERROR: {e}")
        session.stop()
        sys.exit(1)

    session.stop()

    if args.json:
        data = [
            {
                "id": f.id,
                "name": f.name,
                "location": f.location,
                "type": f.type,
                "capacity": f.capacity,
                "availability": [
                    {"date": s.date, "start_time": s.start_time, "end_time": s.end_time}
                    for s in f.availability
                ],
            }
            for f in facilities
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Found {len(facilities)} facilities:\n")
        for f in facilities:
            avail = ", ".join(f"{s.date} {s.start_time}-{s.end_time}" for s in f.availability[:3])
            more = f"... +{len(f.availability) - 3} more" if len(f.availability) > 3 else ""
            cap = f" — capacity {f.capacity}" if f.capacity is not None else ""
            print(f"  {f.id}: {f.name} ({f.type}) @ {f.location}{cap}")
            if avail:
                print(f"       Slots: {avail}{more}")
            print()


if __name__ == "__main__":
    main()
