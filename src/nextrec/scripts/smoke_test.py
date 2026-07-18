import argparse

from nextrec.browser import BrowserManager, find_system_chrome


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a browser smoke test for nextrec Phase 1")
    parser.add_argument("--url", default="https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List")
    parser.add_argument("--headed", action="store_true", help="Open a headed browser session")
    parser.add_argument("--chrome-path", default=None, help="Explicit Chrome executable path")
    parser.add_argument("--storage-state", default=None, help="Save or load Playwright storage state")
    parser.add_argument("--timeout", type=int, default=30000, help="Navigation timeout in milliseconds")
    args = parser.parse_args()

    chrome_path = args.chrome_path or find_system_chrome()
    if not chrome_path:
        raise RuntimeError("Chrome executable not found. Provide --chrome-path or install Chrome.")

    manager = BrowserManager(headless=not args.headed, chrome_path=chrome_path, storage_state_path=args.storage_state)
    manager.launch()

    try:
        page = manager.new_page()
        print(f"Navigating to {args.url}")
        page.goto(args.url, wait_until="networkidle", timeout=args.timeout)
        print(f"Loaded URL: {page.url}")
        print(f"Page title: {page.title()}")
        if args.storage_state and args.headed:
            manager.save_storage_state(args.storage_state)
            print(f"Saved storage state to {args.storage_state}")
        print("Browser smoke test completed successfully.")
    finally:
        manager.close()


if __name__ == "__main__":
    main()
