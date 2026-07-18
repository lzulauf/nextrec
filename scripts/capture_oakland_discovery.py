#!/usr/bin/env python3
"""Capture network traces and storage state for the Oakland PerfectMind facility list.

Usage:
  python scripts/capture_oakland_discovery.py --url "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List" --out docs/discovery

This script uses Playwright (Python) to record a HAR file and a compact JSON summary of requests.
If the site requires manual login, run the script with `--headed` to perform interactive login, then press Enter to continue capture.
"""

import argparse
import os
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import shutil
import platform


def find_system_chrome() -> str | None:
    candidates = []
    system = platform.system()
    if system == "Windows":
        candidates = [
            Path("%ProgramFiles%") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path("%ProgramFiles(x86)%") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        # Common Linux locations
        candidates = [Path("/usr/bin/google-chrome"), Path("/usr/bin/chrome"), Path("/usr/bin/google-chrome-stable")]

    for p in candidates:
        try:
            p_str = str(p)
            p_expanded = Path(p_str.replace("%ProgramFiles%", os.environ.get("ProgramFiles", ""))
                              .replace("%ProgramFiles(x86)%", os.environ.get("ProgramFiles(x86)", "")))
        except Exception:
            p_expanded = p
        if p_expanded.exists():
            return str(p_expanded)
    # last resort: try shutil.which
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def capture(url: str, out_dir: Path, headed: bool = False, wait: int = 5, chrome_path: str | None = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    har_path = out_dir / "oakland_capture.har"
    summary_path = out_dir / "oakland_endpoints.json"
    storage_path = out_dir / "storage_state.json"

    requests = []

    with sync_playwright() as p:
        launch_args = {}
        if chrome_path:
            launch_args["executable_path"] = chrome_path
        browser = p.chromium.launch(headless=not headed, **launch_args)
        # request HAR will be written when context closes
        context = browser.new_context(record_har_path=str(har_path))
        page = context.new_page()

        def on_request(request):
            try:
                requests.append({
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                })
            except Exception:
                pass

        page.on("request", on_request)

        print(f"Navigating to {url} (headed={headed})...")
        page.goto(url, wait_until="networkidle")

        if headed:
            print("Headed mode: if login is required, please log in in the opened browser now.")
            input("Press Enter after login/when ready to continue capture...")
            # save storage state after manual login
            context.storage_state(path=str(storage_path))
            print(f"Saved storage state to {storage_path}")

        # wait a little to let background XHRs finish
        time.sleep(wait)

        # write summary of observed requests
        with summary_path.open("w", encoding="utf-8") as f:
            json.dump(requests, f, indent=2)

        print(f"Wrote request summary to {summary_path}")
        print(f"HAR file saved to {har_path} (if supported by Playwright version)")

        # close context to flush HAR
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Capture Oakland PerfectMind discovery data")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", dest="out", default="docs/discovery")
    parser.add_argument("--headed", action="store_true", help="Run in headed mode for manual login")
    parser.add_argument("--chrome-path", dest="chrome_path", default=None, help="Path to system Chrome executable to use")
    parser.add_argument("--wait", type=int, default=5, help="Seconds to wait after navigation for XHRs")
    args = parser.parse_args()

    capture(args.url, Path(args.out), headed=args.headed, wait=args.wait, chrome_path=args.chrome_path)


if __name__ == "__main__":
    main()
