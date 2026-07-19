import asyncio
import dataclasses
import logging
import os
import platform
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class SessionState:
    storage_state_path: Optional[str] = None
    fallback_to_headed: bool = True

    def resolve_storage_path(self) -> Optional[Path]:
        if self.storage_state_path is None:
            return None
        p = Path(self.storage_state_path).expanduser()
        return p if p.exists() else None


class BrowserSession:
    def __init__(self, state: Optional[SessionState] = None, *, headless: bool = True, chrome_path: Optional[str] = None):
        self.state = state or SessionState()
        self.headless = headless
        self.chrome_path = chrome_path
        self.manager: Optional[BrowserManager] = None
        self._request_log: List[Dict[str, Any]] = []

    async def start(self) -> None:
        if self.manager is not None:
            raise TypeError("BrowserSession is already started")
        self.manager = BrowserManager(
            headless=self.headless,
            chrome_path=self.chrome_path,
            storage_state_path=self.state.resolve_storage_path(),
        )
        self.manager._request_log = self._request_log
        await self.manager.launch()

    async def stop(self) -> None:
        if self.manager is None:
            raise TypeError("BrowserSession has not been started")
        await self.manager.close()
        self.manager = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    @property
    def request_log(self) -> List[Dict[str, Any]]:
        return list(self._request_log)


def find_system_chrome() -> Optional[str]:
    candidates = []
    system = platform.system()
    if system == "Windows":
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/chrome"),
            Path("/usr/bin/google-chrome-stable"),
        ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


class BrowserManager:
    def __init__(self, headless: bool = True, chrome_path: Optional[str] = None, storage_state_path: Optional[str] = None):
        self.headless = headless
        self.chrome_path = chrome_path
        self.storage_state_path = storage_state_path
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def launch(self) -> None:
        if self._browser is not None:
            return

        self._playwright = await async_playwright().start()
        launch_args = {"headless": self.headless}
        if self.chrome_path:
            launch_args["executable_path"] = self.chrome_path

        self._browser = await self._playwright.chromium.launch(**launch_args)
        self._context = await self._browser.new_context(**self._get_context_options())
        self._context.set_default_timeout(30000)

    def _get_context_options(self) -> Dict[str, Any]:
        options: Dict[str, Any] = {}
        if self.storage_state_path:
            storage_path = Path(self.storage_state_path).expanduser()
            if storage_path.exists():
                options["storage_state"] = str(storage_path)
        return options

    async def new_page(self, log_requests: bool = True) -> Page:
        await self._ensure_context()
        page = await self._context.new_page()
        await page.set_default_navigation_timeout(30000)
        await page.set_default_timeout(30000)

        if log_requests:
            self._setup_request_logging(page)
        return page

    def _setup_request_logging(self, page: Page) -> None:
        log = getattr(self, "_request_log", None)

        page.on("request", lambda req: logger.debug("→ %s %s", req.method, req.url))
        page.on("response", lambda resp: logger.debug("← %s %s (%s)", resp.request.method, resp.url, resp.status))

        if log is not None:
            page.on("request", lambda req: log.append({"method": req.method, "url": req.url, "type": req.resource_type}))

    async def save_storage_state(self, path: str) -> None:
        await self._ensure_context()
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(target))

    async def load_storage_state(self, path: str) -> None:
        self.storage_state_path = str(Path(path).expanduser())
        if self._context is not None:
            await self._context.close()
            self._context = await self._browser.new_context(**self._get_context_options())
            self._context.set_default_timeout(30000)

    async def fetch_json(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, data: Optional[Any] = None, timeout: int = 30000) -> Any:
        await self._ensure_context()
        request_data: Dict[str, Any] = {"method": method.upper(), "timeout": timeout}
        if headers:
            request_data["headers"] = headers
        if data is not None:
            request_data["data"] = data

        response = await self._context.request.fetch(url, **request_data)
        response.raise_for_status()
        return await response.json()

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _ensure_context(self) -> None:
        if self._context is None:
            raise RuntimeError("Browser context is not available. Call launch() first.")
