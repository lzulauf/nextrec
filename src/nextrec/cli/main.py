import asyncio
import json
import logging
import tempfile
import urllib.parse
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import typer
from dateutil import parser as dateparser

from nextrec.auth import capture_login_interactive
from nextrec.browser import BrowserSession, SessionState, find_system_chrome
from nextrec.cart import CartError, CartManager
from nextrec.cli.config_loader import load_config, merge_configs
from nextrec.models import Constraint
from nextrec.scrapers.perfectmind import (
    FACILITY_DETAIL_URL,
    FACILITY_LIST_URL,
    PerfectMindScraper,
    ScrapeError,
)
from nextrec.search import search_and_fetch

app = typer.Typer(
    name="nextrec",
    help="Locate and book facility reservations on PerfectMind-based municipal sites.",
    no_args_is_help=True,
)


def _parse_date(s: str) -> date:
    return dateparser.parse(s, default=datetime.today()).date()


def _parse_time(s: str) -> time:
    parts = s.split(":")
    if len(parts) != 2:
        raise typer.BadParameter(f"Expected HH:MM, got {s!r}")
    return time(int(parts[0]), int(parts[1]))


def _resolve_chrome(chrome_path: Optional[Path]) -> str:
    exe = str(chrome_path) if chrome_path else find_system_chrome()
    if not exe:
        typer.echo("ERROR: Chrome executable not found. Provide --chrome-path or install Chrome.", err=True)
        raise typer.Exit(1)
    return exe


async def _run_auth_flow(chrome_exe: str, auth_path: str) -> None:
    typer.echo("Opening browser for login...")
    auth_session = BrowserSession(chrome_path=chrome_exe, headless=False)
    await auth_session.start()
    try:
        await capture_login_interactive(auth_session, auth_path)
    finally:
        await auth_session.stop()


async def _ensure_auth_session(chrome_exe: str, storage_state: Optional[Path]) -> str:
    auth_path = str(storage_state) if storage_state else "session_state.json"
    auth_file = Path(auth_path)

    if not auth_file.exists():
        await _run_auth_flow(chrome_exe, auth_path)
        return auth_path

    check_session = BrowserSession(chrome_path=chrome_exe, headless=True)
    await check_session.start()
    try:
        await check_session.manager.load_storage_state(auth_path)
        page = await check_session.manager.new_page()
        await page.goto(FACILITY_LIST_URL, wait_until="networkidle")
        resp = await page.request.get(
            "https://cityofoakland.perfectmind.com/MyInfo/ObjectHolds/GetActiveHoldsCount",
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return auth_path
    except Exception:
        pass
    finally:
        await check_session.stop()

    await _run_auth_flow(chrome_exe, auth_path)
    return auth_path


async def _async_book(
    constraint: Constraint,
    duration_min: int,
    days_count: int,
    num_attendees: int,
    kw_list: list[str],
    chrome_exe: str,
    auth_path: str,
    headed: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    facilities = []
    slots_by_facility = {}
    session = BrowserSession(chrome_path=chrome_exe, headless=not headed)
    await session.start()
    await session.manager.load_storage_state(auth_path)

    typer.echo(f"Constraints: {constraint}")
    typer.echo(f"Browser: {'headed' if headed else 'headless'}")
    typer.echo(f"Auth state: {auth_path}")
    typer.echo()

    book_target = None
    slots_by_facility = {}

    try:
        if kw_list:
            typer.echo("Searching and fetching facility info...")
            fac_names, slot_results = await search_and_fetch(
                session, kw_list, constraint, duration_min,
                days_count=days_count,
                end_date=constraint.end_date,
                time_window_start=constraint.time_window_start,
                time_window_end=constraint.time_window_end,
            )
            from collections import defaultdict
            by_facility = defaultdict(list)
            for fid, cfg, slot in slot_results:
                by_facility[fid].append((cfg, slot))

            for fid, items in by_facility.items():
                first_cfg = items[0][0]
                available = [s for _, s in items]
                slots_by_facility[fid] = [
                    {"date": str(s.date), "start_time": str(s.start_time), "end_time": str(s.end_time)}
                    for s in available
                ]
                name = fac_names.get(fid, fid[:8])
                typer.echo(f"\n  {name} ({fid}):")
                typer.echo(f"    Config: calendar={first_cfg.calendar_id}, service={first_cfg.service_id}")
                if first_cfg.duration_prices:
                    prices = ", ".join(
                        f"{dp.minutes}min=${dp.resident_price:.0f}(R)/${dp.non_resident_price:.0f}(NR)"
                        for dp in first_cfg.duration_prices
                    )
                    typer.echo(f"    Pricing: {prices}")
                if available:
                    typer.echo(f"    Available slots ({len(available)}):")
                    for s in available[:10]:
                        typer.echo(f"      {s.date} {s.start_time}-{s.end_time}")
                    if len(available) > 10:
                        typer.echo(f"      ... and {len(available) - 10} more")
                    if book_target is None:
                        book_target = (fid, first_cfg, available[0])
                else:
                    typer.echo(f"    No available slots")
        else:
            scraper = PerfectMindScraper(session)
            facilities = await scraper.search(constraint)
            typer.echo("Fetching facility configs and time slots...")
            for f in facilities:
                try:
                    slot_date = constraint.start_date or date.today()
                    config_obj, slots = await scraper.fetch_config_and_slots(
                        f.id, slot_date,
                        days_count=days_count,
                        duration_minutes=duration_min,
                        end_date=constraint.end_date,
                        time_window_start=constraint.time_window_start,
                        time_window_end=constraint.time_window_end,
                    )
                except ScrapeError as e:
                    typer.echo(f"  [SKIP] {f.name}: {e}")
                    continue

                available = [s for s in slots if not s.is_disabled]
                slots_by_facility[f.id] = [
                    {"date": str(s.date), "start_time": str(s.start_time), "end_time": str(s.end_time)}
                    for s in available
                ]
                typer.echo(f"\n  {f.name} ({f.id}):")
                typer.echo(f"    Config: calendar={config_obj.calendar_id}, service={config_obj.service_id}")
                if config_obj.duration_prices:
                    prices = ", ".join(
                        f"{dp.minutes}min=${dp.resident_price:.0f}(R)/${dp.non_resident_price:.0f}(NR)"
                        for dp in config_obj.duration_prices
                    )
                    typer.echo(f"    Pricing: {prices}")
                if available:
                    typer.echo(f"    Available slots ({len(available)}):")
                    for s in available[:10]:
                        typer.echo(f"      {s.date} {s.start_time}-{s.end_time}")
                    if len(available) > 10:
                        typer.echo(f"      ... and {len(available) - 10} more")
                    if book_target is None:
                        book_target = (f.id, config_obj, available[0])
                else:
                    typer.echo(f"    No available slots")
    except ScrapeError as e:
        typer.echo(f"ERROR: {e}", err=True)
        try:
            await session.manager.save_storage_state(auth_path)
        except Exception:
            pass
        await session.stop()
        raise typer.Exit(1)

    if dry_run and book_target:
        fid, _, slot = book_target
        typer.echo(f"\n[Dry run] Would book: {fid} on {slot.date} at {slot.start_time}")
    elif book_target:
        facility_id, config_obj, slot = book_target
        typer.echo(f"\nBooking first available slot: {facility_id} on {slot.date} at {slot.start_time}")
        try:
            cart = CartManager(session)
            result = await cart.add_to_cart(facility_id, config_obj, slot, number_of_attendees=num_attendees)
            typer.echo(f"  Result: {result.message}")
            await session.manager.save_storage_state(auth_path)
            checkout_state = tempfile.mktemp(suffix=".json")
            await session.manager.save_storage_state(checkout_state)
            await session.stop()
            typer.echo("\nOpening headed browser for checkout...")

            dur_id = next(
                (dp.id for dp in config_obj.duration_prices if dp.minutes == slot.duration_minutes),
                config_obj.duration_prices[0].id if config_obj.duration_prices else "",
            )
            back_url = urllib.parse.quote(
                f"{FACILITY_DETAIL_URL}?facilityId={facility_id}", safe=""
            )
            base_url = "https://cityofoakland.perfectmind.com/SocialSite/BookMe4EventParticipants/FacilityBooking"
            checkout_url = (
                f"{base_url}?facilityId={facility_id}"
                f"&calendarId={config_obj.calendar_id}"
                f"&serviceId={config_obj.service_id}"
                f"&duration={slot.duration_minutes}"
                f"&durationId={dur_id}"
                f"&startDateTimeTicks={slot.ticks}"
                f"&numberOfAttendees={num_attendees}"
                f"&numberOfNights=0"
                f"&feeType=0"
                f"&landingPageBackUrl={back_url}"
            )

            checkout_session = BrowserSession(
                chrome_path=chrome_exe, headless=False,
                state=SessionState(storage_state_path=checkout_state),
            )
            await checkout_session.start()
            page = await checkout_session.manager.new_page()
            await page.goto(checkout_url, wait_until="networkidle")
            typer.echo("Items added to cart. Complete checkout in the browser window.")
            typer.echo("Press Enter to close the browser and finish.")
            input()
            await checkout_session.stop()
            return
        except (CartError, ScrapeError) as e:
            typer.echo(f"  ERROR: {e}", err=True)

    await session.manager.save_storage_state(auth_path)
    await session.stop()

    if json_output:
        data = [
            {
                "id": f.id,
                "name": f.name,
                "location": f.location,
                "type": f.type,
                "slots": slots_by_facility.get(f.id, []),
            }
            for f in facilities
        ]
        typer.echo(json.dumps(data, indent=2))
    else:
        typer.echo(f"\nFound {len(facilities)} facilities:\n")
        for f in facilities:
            avail = ", ".join(f"{s.date} {s.start_time}-{s.end_time}" for s in f.availability[:3])
            more = f"... +{len(f.availability) - 3} more" if len(f.availability) > 3 else ""
            cap = f" — capacity {f.capacity}" if f.capacity is not None else ""
            typer.echo(f"  {f.id}: {f.name} ({f.type}) @ {f.location}{cap}")
            if avail:
                typer.echo(f"       Slots: {avail}{more}")
            typer.echo()


@app.command()
def book(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to constraints file (JSON/YAML)"),
    keywords: Optional[list[str]] = typer.Option(None, "--keywords", "-k", help="Keyword phrase for one search query (repeatable: -k tennis -k 'basketball gym')"),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="End date (YYYY-MM-DD, inclusive)"),
    date_opt: Optional[str] = typer.Option(None, "--date", "-d", help="Single date (YYYY-MM-DD, sets start-date and end-date)"),
    start_time: Optional[str] = typer.Option(None, "--start-time", help="Earliest time (HH:MM)"),
    end_time: Optional[str] = typer.Option(None, "--end-time", help="Latest time (HH:MM)"),
    duration: int = typer.Option(60, "--duration", help="Slot duration in minutes"),
    days: int = typer.Option(7, "--days", help="Number of days to look ahead for slots"),
    number_of_attendees: int = typer.Option(1, "--attendees", "--number-of-attendees", help="Number of attendees for the booking"),
    storage_state: Optional[Path] = typer.Option(None, "--auth-state", help="Path to saved Playwright storage state JSON"),
    headed: bool = typer.Option(False, "--headed", help="Run browser in headed mode"),
    chrome_path: Optional[Path] = typer.Option(None, "--chrome-path", help="Explicit path to Chrome executable"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Search and show slots without booking"),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Search facilities and optionally book the first available slot."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    raw = {}
    if config:
        raw = load_config(config)

    cli_overrides = {k: v for k, v in {
        "keywords": keywords,
        "start_date": start_date,
        "end_date": end_date,
        "date": date_opt,
        "start_time": start_time,
        "end_time": end_time,
        "duration": duration if duration != 60 else None,
        "days": days if days != 7 else None,
        "number_of_attendees": number_of_attendees if number_of_attendees != 1 else None,
    }.items() if v is not None}
    merged = merge_configs(cli_overrides, raw)

    if merged.get("date") and not merged.get("start_date") and not merged.get("end_date"):
        merged["start_date"] = merged["end_date"] = merged["date"]
    elif merged.get("date") and not merged.get("start_date"):
        merged["start_date"] = merged["date"]
    elif merged.get("date") and not merged.get("end_date"):
        merged["end_date"] = merged["date"]

    try:
        constraint = Constraint(
            keywords=None,
            start_date=_parse_date(merged["start_date"]) if merged.get("start_date") else None,
            end_date=_parse_date(merged["end_date"]) if merged.get("end_date") else None,
            time_window_start=_parse_time(merged["start_time"]) if merged.get("start_time") else None,
            time_window_end=_parse_time(merged["end_time"]) if merged.get("end_time") else None,
        )
    except KeyError as e:
        raise typer.BadParameter(f"Missing required field: {e}")

    duration_min = merged.get("duration", 60)
    days_count = merged.get("days", 7)
    num_attendees = merged.get("number_of_attendees", 1)
    raw_kw = merged.get("keywords")
    if isinstance(raw_kw, str):
        kw_list = [raw_kw]
    elif isinstance(raw_kw, list):
        kw_list = raw_kw
    else:
        kw_list = []

    chrome_exe = _resolve_chrome(chrome_path)

    auth_path = asyncio.run(_ensure_auth_session(chrome_exe, storage_state))

    asyncio.run(_async_book(
        constraint, duration_min, days_count, num_attendees, kw_list,
        chrome_exe, auth_path, headed, dry_run, json_output,
    ))


@app.command()
def auth(
    storage_state: str = typer.Option("session_state.json", "--auth-state", help="Path to save storage state JSON"),
    chrome_path: Optional[Path] = typer.Option(None, "--chrome-path", help="Explicit path to Chrome executable"),
):
    """Open a headed browser for manual login and save the session."""
    chrome_exe = _resolve_chrome(chrome_path)

    async def _auth_async():
        async with BrowserSession(chrome_path=chrome_exe, headless=False) as session:
            await capture_login_interactive(session, storage_state)

    asyncio.run(_auth_async())


@app.command(name="generate-config")
def generate_config(
    keywords: Optional[list[str]] = typer.Option(None, "--keywords", "-k", help="Search keywords (repeatable)"),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Start date"),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="End date"),
    date_opt: Optional[str] = typer.Option(None, "--date", "-d", help="Single date (sets start-date and end-date)"),
    start_time: Optional[str] = typer.Option(None, "--start-time", help="Earliest time (HH:MM)"),
    end_time: Optional[str] = typer.Option(None, "--end-time", help="Latest time (HH:MM)"),
    duration: Optional[int] = typer.Option(None, "--duration", help="Slot duration in minutes"),
    days: Optional[int] = typer.Option(None, "--days", help="Number of days to look ahead"),
    number_of_attendees: Optional[int] = typer.Option(None, "--attendees", "--number-of-attendees", help="Number of attendees"),
    output: Optional[Path] = typer.Option(None, "--config", "-c", help="Output file path (default: stdout)"),
):
    """Generate a constraints config file for use with nextrec book --config."""
    config_dict: dict = {}
    if keywords:
        config_dict["keywords"] = keywords
    if start_date:
        config_dict["start_date"] = start_date
    if end_date:
        config_dict["end_date"] = end_date
    if date_opt:
        config_dict["date"] = date_opt
    if start_time:
        config_dict["start_time"] = start_time
    if end_time:
        config_dict["end_time"] = end_time
    if duration is not None:
        config_dict["duration"] = duration
    if days is not None:
        config_dict["days"] = days
    if number_of_attendees is not None:
        config_dict["number_of_attendees"] = number_of_attendees

    if output and output.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            typer.echo("ERROR: PyYAML is required for .yaml output. Install it with: pip install nextrec[yaml]", err=True)
            raise typer.Exit(1)
        text = yaml.safe_dump(config_dict, default_flow_style=False) or ""
    else:
        text = json.dumps(config_dict, indent=2)

    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Config written to {output}")
    else:
        typer.echo(text)


@app.command()
def tui(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to constraints file (JSON/YAML)"),
    keywords: Optional[list[str]] = typer.Option(None, "--keywords", "-k", help="Keyword phrase for one search query (repeatable)"),
    start_date: Optional[str] = typer.Option(None, "--start-date", help="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = typer.Option(None, "--end-date", help="End date (YYYY-MM-DD, inclusive)"),
    date_opt: Optional[str] = typer.Option(None, "--date", "-d", help="Single date (sets start-date and end-date)"),
    start_time: Optional[str] = typer.Option(None, "--start-time", help="Earliest time (HH:MM)"),
    end_time: Optional[str] = typer.Option(None, "--end-time", help="Latest time (HH:MM)"),
    duration: int = typer.Option(60, "--duration", help="Slot duration in minutes"),
    number_of_attendees: int = typer.Option(1, "--attendees", "--number-of-attendees", help="Number of attendees"),
    storage_state: Optional[Path] = typer.Option(None, "--auth-state", help="Path to saved Playwright storage state JSON"),
    chrome_path: Optional[Path] = typer.Option(None, "--chrome-path", help="Explicit path to Chrome executable"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Interactive TUI for facility search and booking."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    chrome_exe = _resolve_chrome(chrome_path)
    auth_path = asyncio.run(_ensure_auth_session(chrome_exe, storage_state))

    raw = {}
    if config:
        raw = load_config(config)

    cli_overrides = {k: v for k, v in {
        "keywords": keywords,
        "start_date": start_date,
        "end_date": end_date,
        "date": date_opt,
        "start_time": start_time,
        "end_time": end_time,
        "duration": duration if duration != 60 else None,
        "number_of_attendees": number_of_attendees if number_of_attendees != 1 else None,
    }.items() if v is not None}
    initial = merge_configs(cli_overrides, raw)

    from nextrec.tui.app import NextRecApp, dump_logs
    app = NextRecApp(chrome_exe=chrome_exe, auth_path=auth_path, initial_constraints=initial)
    try:
        app.run()
    finally:
        dump_logs()


@app.command(name="debug-browse")
def debug_browse(
    storage_state: Optional[Path] = typer.Option(None, "--auth-state", help="Path to saved Playwright storage state JSON"),
    chrome_path: Optional[Path] = typer.Option(None, "--chrome-path", help="Explicit path to Chrome executable"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save traffic summary to JSON file"),
):
    """Open a headed browser, interact freely, then analyze captured network traffic."""

    async def _run():
        chrome_exe = _resolve_chrome(chrome_path)

        session = BrowserSession(chrome_path=chrome_exe, headless=False)
        await session.start()
        if storage_state:
            await session.manager.load_storage_state(str(storage_state))

        page = await session.manager.new_page()

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

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto(FACILITY_LIST_URL, wait_until="load")

        typer.echo("=" * 60)
        typer.echo("Headed browser is open. You can now:")
        typer.echo("  1. Search for facilities")
        typer.echo("  2. Click on a facility card to view its detail page")
        typer.echo("  3. Interact with the detail page to see slot loading")
        typer.echo("Press Enter here when done to analyze the captured traffic.")
        typer.echo("=" * 60)

        input()

        xhr_entries = [
            e for e in all_requests
            if e.get("resource_type") in ("xhr", "fetch") or e.get("content_type", "").startswith("application/json")
        ]

        typer.echo(f"\n=== Network Capture Summary ===")
        typer.echo(f"Total events captured: {len(all_requests)}")
        typer.echo(f"XHR/API calls: {len(xhr_entries)}")

        url_counter = Counter()
        for e in all_requests:
            url_counter[e["url"].split("?")[0].split("#")[0]] += 1

        typer.echo(f"\nUnique endpoints hit:\n")
        seen = set()
        for url, count in url_counter.most_common():
            if url not in seen:
                seen.add(url)
                domain_path = url.split("://", 1)[-1] if "://" in url else url
                typer.echo(f"  [{count}x] {domain_path}")

        json_responses = [e for e in all_requests if e["type"] == "response" and e["body"] is not None]
        if json_responses:
            typer.echo(f"\n=== Response details for API calls ===\n")
            for e in json_responses:
                url = e["url"]
                qs = ""
                if "?" in url:
                    url, qs = url.split("?", 1)
                typer.echo(f"--- {e['status']} {url} ---")
                if qs:
                    typer.echo(f"    Query: {qs}")
                body = e["body"]
                if isinstance(body, dict):
                    top_keys = list(body.keys())
                    typer.echo(f"  Top-level keys: {top_keys}")
                    for k in top_keys:
                        v = body[k]
                        if isinstance(v, list):
                            typer.echo(f"    {k}: list[{len(v)}]")
                            if v and isinstance(v[0], dict):
                                typer.echo(f"      item keys: {list(v[0].keys())}")
                        elif isinstance(v, dict):
                            typer.echo(f"    {k}: dict keys={list(v.keys())}")
                        else:
                            typer.echo(f"    {k}: {v!r}")
                elif isinstance(body, list):
                    typer.echo(f"  List[{len(body)}]")
                    if body and isinstance(body[0], dict):
                        typer.echo(f"  Item keys: {list(body[0].keys())}")
                else:
                    typer.echo(f"  {body}")
                typer.echo()

        post_requests = [
            e for e in all_requests
            if e["type"] == "request" and e["method"] == "POST" and e["url"] in request_bodies
        ]
        if post_requests:
            typer.echo(f"\n=== POST body details ===\n")
            sent_urls = set()
            for e in post_requests:
                url = e["url"]
                if url in sent_urls:
                    continue
                sent_urls.add(url)
                body = request_bodies[url]
                typer.echo(f"--- POST {url} ---")
                params = body.split("&")
                for p in params:
                    typer.echo(f"  {p}")
                typer.echo()

        if output:
            traffic_data = {
                "summary": {
                    "total_events": len(all_requests),
                    "xhr_api_calls": len(xhr_entries),
                    "unique_endpoints": len(url_counter),
                },
                "endpoints": [
                    {"url": url, "count": count}
                    for url, count in url_counter.most_common()
                ],
                "post_bodies": request_bodies,
            }
            output.write_text(json.dumps(traffic_data, indent=2, default=str), encoding="utf-8")
            typer.echo(f"Traffic summary saved to: {output}")

        await page.close()
        await session.stop()

    asyncio.run(_run())
