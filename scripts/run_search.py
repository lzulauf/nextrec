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

    all_requests: list[dict] = []
    request_bodies: dict[str, str] = {}

    def on_request(req):
        all_requests.append({
            "type": "request",
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type,
        })
        if req.method == "POST":
            try:
                body = req.post_data
                if body:
                    request_bodies[req.url] = body
            except Exception:
                pass

    def on_response(resp):
        url = resp.url
        if resp.request.resource_type in ("xhr", "fetch", "document") and resp.status != 304:
            body = None
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    body = resp.json()
                elif "html" in ct and "facilityId" in url:
                    body = f"<HTML ({len(resp.body())} bytes)>"
            except Exception:
                pass
            all_requests.append({
                "type": "response",
                "url": url,
                "status": resp.status,
                "body": body,
                "content_type": resp.headers.get("content-type", ""),
            })

    print("=" * 60)
    print("Headed browser is open. You can now:")
    print("  1. Search for facilities (try 'pb', 'pickleball', 'tennis')")
    print("  2. Click on a facility card to view its detail page")
    print("  3. Interact with the detail page to see slot loading")
    print("Press Enter here when done to analyze the captured traffic.")
    print("=" * 60)

    page.on("request", on_request)
    page.on("response", on_response)

    input()

    from collections import Counter

    # Summarize all unique endpoints discovered
    xhr_entries = [e for e in all_requests if e.get("resource_type") in ("xhr", "fetch") or e.get("content_type", "").startswith("application/json")]

    print(f"\n=== Network Capture Summary ===")
    print(f"Total events captured: {len(all_requests)}")
    print(f"XHR/API calls: {len(xhr_entries)}")

    url_counter = Counter()
    for e in all_requests:
        url_counter[e["url"].split("?")[0].split("#")[0]] += 1

    print(f"\nUnique endpoints hit:\n")
    seen = set()
    for url, count in url_counter.most_common():
        if url not in seen:
            seen.add(url)
            domain_path = url.split("://", 1)[-1] if "://" in url else url
            print(f"  [{count}x] {domain_path}")

    # Show any response bodies for key endpoints
    json_responses = [e for e in all_requests if e["type"] == "response" and e["body"] is not None]
    if json_responses:
        print(f"\n=== Response details for API calls ===\n")
        for e in json_responses:
            print(f"--- {e['status']} {e['url']} ---")
            body = e["body"]
            if isinstance(body, dict):
                top_keys = list(body.keys())
                print(f"  Top-level keys: {top_keys}")
                for k in top_keys:
                    v = body[k]
                    if isinstance(v, list):
                        print(f"    {k}: list[{len(v)}]")
                        if v and isinstance(v[0], dict):
                            print(f"      item keys: {list(v[0].keys())}")
                    elif isinstance(v, dict):
                        print(f"    {k}: dict keys={list(v.keys())}")
                    else:
                        print(f"    {k}: {v!r}")
            elif isinstance(body, list):
                print(f"  List[{len(body)}]")
                if body and isinstance(body[0], dict):
                    print(f"  Item keys: {list(body[0].keys())}")
            else:
                print(f"  {body}")
            print()

    # Show request bodies for POST endpoints
    post_requests = [e for e in all_requests if e["type"] == "request" and e["method"] == "POST" and e["url"] in request_bodies]
    if post_requests:
        print(f"\n=== POST body details ===\n")
        sent_urls = set()
        for e in post_requests:
            url = e["url"]
            if url in sent_urls:
                continue
            sent_urls.add(url)
            body = request_bodies[url]
            print(f"--- POST {url} ---")
            params = body.split("&")
            for p in params:
                print(f"  {p}")
            print()

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
