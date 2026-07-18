#!/usr/bin/env python3
"""Headed browser inspection for PerfectMind facility detail / slot discovery.

Usage:
    python scripts/capnt_inspect.py
    python scripts/capnt_inspect.py --out captured.json
    python scripts/capnt_inspect.py --storage-state docs/discovery/storage_state.json
"""

import argparse
import json
import logging
import sys
from collections import Counter

from nextrec.browser import BrowserSession, find_system_chrome
from nextrec.scrapers.perfectmind import FACILITY_LIST_URL


def main():
    parser = argparse.ArgumentParser(description="Inspect PerfectMind facility detail page traffic")
    parser.add_argument("--out", default="captured_traffic.json", help="Output JSON file path")
    parser.add_argument("--storage-state", default=None, help="Path to saved Playwright storage state")
    parser.add_argument("--chrome-path", default=None, help="Explicit path to Chrome executable")
    parser.add_argument("--url", default=FACILITY_LIST_URL, help="Starting URL")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    chrome_path = args.chrome_path or find_system_chrome()
    if not chrome_path:
        print("ERROR: Chrome executable not found. Provide --chrome-path or install Chrome.")
        sys.exit(1)

    session = BrowserSession(chrome_path=chrome_path, headless=False)
    session.start()
    if args.storage_state:
        session.manager.load_storage_state(args.storage_state)

    page = session.manager.new_page()

    all_requests: list[dict] = []
    request_bodies: dict[str, str] = {}

    def on_request(req):
        entry = {
            "type": "request",
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type,
        }
        all_requests.append(entry)
        if req.method == "POST":
            try:
                body = req.post_data
                if body:
                    request_bodies[req.url] = body
            except Exception:
                pass

    def on_response(resp):
        url = resp.url
        rt = resp.request.resource_type
        if rt not in ("xhr", "fetch", "document") or resp.status == 304:
            return
        body = None
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                body = resp.json()
            elif "html" in ct or "text" in ct:
                body_text = resp.body()
                body = f"<{rt} ({len(body_text)} bytes)>"
        except Exception:
            pass
        all_requests.append({
            "type": "response",
            "url": url,
            "status": resp.status,
            "body": body,
            "content_type": resp.headers.get("content-type", ""),
        })

    page.on("request", on_request)
    page.on("response", on_response)

    page.goto(args.url, wait_until="networkidle")

    print("=" * 60)
    print("Headed browser opened at the facility list page.")
    print("What to do:")
    print("  1. Search for facilities (try 'pb', 'pickleball', 'tennis')")
    print("  2. Click a facility card to view its detail page")
    print("  3. Look for time slot loading / 'Add to Cart' on detail page")
    print("  4. Close the browser window when done")
    print("=" * 60)
    print(f"Results will be saved to: {args.out}")

    page.wait_for_event("close", timeout=0)

    # Detach handlers
    page.on("request", None)
    page.on("response", None)

    # Build summary
    api_calls = [e for e in all_requests
                 if e.get("resource_type") in ("xhr", "fetch")
                 or e.get("content_type", "").startswith("application/json")]

    url_counter = Counter()
    for e in all_requests:
        url_counter[e["url"].split("?")[0].split("#")[0]] += 1

    json_responses = [e for e in all_requests if e["type"] == "response" and e["body"] is not None and isinstance(e["body"], dict)]

    summary_lines = []
    summary_lines.append(f"Total events: {len(all_requests)}")
    summary_lines.append(f"XHR/API calls: {len(api_calls)}")
    summary_lines.append("")
    summary_lines.append("Endpoints hit:")
    summary_lines.append("")
    seen = set()
    for url, count in url_counter.most_common():
        if url not in seen:
            seen.add(url)
            domain_path = url.split("://", 1)[-1] if "://" in url else url
            summary_lines.append(f"  [{count}x] {domain_path}")
    summary_lines.append("")

    if json_responses:
        summary_lines.append("JSON API response shapes:")
        summary_lines.append("")
        for e in json_responses:
            summary_lines.append(f"--- {e['status']} {e['url']} ---")
            body = e["body"]
            top_keys = list(body.keys())
            summary_lines.append(f"  Keys: {top_keys}")
            for k in top_keys[:10]:
                v = body[k]
                if isinstance(v, list):
                    summary_lines.append(f"    {k}: list[{len(v)}]")
                    if v and isinstance(v[0], dict):
                        summary_lines.append(f"      item keys: {list(v[0].keys())}")
                elif isinstance(v, dict):
                    summary_lines.append(f"    {k}: dict keys={list(v.keys())}")
                else:
                    summary_lines.append(f"    {k}: {v!r}")
            summary_lines.append("")

    output = {
        "summary": "\n".join(summary_lines),
        "all_requests_count": len(all_requests),
        "api_calls_count": len(api_calls),
        "endpoints": list(seen),
        "endpoint_counts": dict(url_counter.most_common()),
        "request_bodies": request_bodies,
        "json_responses": [
            {"url": e["url"], "status": e["status"], "body": e["body"]}
            for e in json_responses
        ],
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2, default=str)

    page.close()
    session.stop()

    print("\n" + summary_lines[-1])
    print("=" * 60)
    print(summary_lines[2])
    print(f"Full results saved to: {args.out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
