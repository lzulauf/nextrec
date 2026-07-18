import argparse

from nextrec.auth import capture_login_interactive
from nextrec.browser import BrowserSession, find_system_chrome


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a PerfectMind login session interactively")
    parser.add_argument("--storage-state", default="session_state.json", help="Path to save storage state (default: session_state.json)")
    parser.add_argument("--chrome-path", default=None, help="Explicit Chrome executable path")
    args = parser.parse_args()

    chrome_path = args.chrome_path or find_system_chrome()
    if not chrome_path:
        raise RuntimeError("Chrome executable not found. Provide --chrome-path or install Chrome.")

    with BrowserSession(chrome_path=chrome_path, headless=False) as session:
        capture_login_interactive(session, args.storage_state)


if __name__ == "__main__":
    main()
