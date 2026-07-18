from pathlib import Path
from unittest.mock import Mock

import pytest

from nextrec.browser import BrowserManager, BrowserSession, SessionState, find_system_chrome


class TestFindSystemChrome:
    def test_uses_known_windows_location(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setenv("ProgramFiles", r"C:\ProgramFiles")
        monkeypatch.setenv("ProgramFiles(x86)", r"C:\ProgramFiles (x86)")

        candidate_path = Path(r"C:\ProgramFiles\Google\Chrome\Application\chrome.exe")
        monkeypatch.setattr(Path, "exists", lambda self: self == candidate_path)

        found = find_system_chrome()
        assert found == str(candidate_path)

    def test_falls_back_to_shutil_which(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setattr("nextrec.browser.Path.exists", lambda self: False)
        monkeypatch.setattr("nextrec.browser.shutil.which", lambda name: "/usr/bin/chrome" if name == "chrome" else None)

        found = find_system_chrome()
        assert found == "/usr/bin/chrome"

    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr("platform.system", lambda: "Windows")
        monkeypatch.setattr("nextrec.browser.Path.exists", lambda self: False)
        monkeypatch.setattr("nextrec.browser.shutil.which", lambda name: None)

        found = find_system_chrome()
        assert found is None


class TestBrowserManager:
    def test_launch_and_close(self, fake_playwright):
        mock_playwright = fake_playwright["playwright"]
        mock_browser = fake_playwright["browser"]
        mock_context = fake_playwright["context"]

        manager = BrowserManager(headless=True, chrome_path="/fake/chrome", storage_state_path=None)
        manager.launch()

        assert mock_playwright.chromium.launch.called
        mock_browser.new_context.assert_called_once()
        assert manager._context is mock_context

        manager.close()
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    def test_launch_is_idempotent(self, fake_playwright):
        mock_playwright = fake_playwright["playwright"]
        mock_browser = fake_playwright["browser"]

        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        manager.launch()
        manager.launch()

        mock_playwright.chromium.launch.assert_called_once()
        mock_browser.new_context.assert_called_once()

    def test_save_storage_state_calls_context_storage_state(self):
        manager = BrowserManager(headless=True, chrome_path=None, storage_state_path=None)
        mock_context = Mock()
        manager._context = mock_context

        target_path = Path("/tmp/storage_state.json")
        manager.save_storage_state(str(target_path))

        mock_context.storage_state.assert_called_once_with(path=str(target_path))

    def test_load_storage_state_updates_path_and_replaces_context(self, fake_playwright):
        mock_browser = fake_playwright["browser"]
        mock_context1 = fake_playwright["context"]
        mock_context2 = Mock()

        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        manager.launch()
        assert manager._context is mock_context1

        mock_browser.new_context.return_value = mock_context2
        manager.load_storage_state("/fake/storage.json")

        assert manager.storage_state_path == str(Path("/fake/storage.json").expanduser())
        mock_context1.close.assert_called_once()
        assert manager._context is mock_context2

    def test_load_storage_state_without_launch(self):
        manager = BrowserManager(headless=True)
        manager.load_storage_state("/fake/storage.json")

        assert manager.storage_state_path == str(Path("/fake/storage.json").expanduser())

    def test_fetch_json_uses_context_request(self, fake_playwright):
        mock_context = fake_playwright["context"]
        mock_response = Mock()
        mock_response.json.return_value = {"key": "value"}
        mock_context.request.fetch.return_value = mock_response

        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        manager.launch()

        result = manager.fetch_json("https://example.com/api", method="POST", headers={"X-Test": "1"}, data='{"q":"test"}')

        mock_context.request.fetch.assert_called_once_with(
            "https://example.com/api",
            method="POST",
            timeout=30000,
            headers={"X-Test": "1"},
            data='{"q":"test"}',
        )
        assert result == {"key": "value"}

    def test_fetch_json_raises_on_http_error(self, fake_playwright):
        mock_context = fake_playwright["context"]
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")
        mock_context.request.fetch.return_value = mock_response

        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        manager.launch()

        with pytest.raises(Exception, match="HTTP 500"):
            manager.fetch_json("https://example.com/api")

    def test_ensure_context_raises_when_not_launched(self):
        manager = BrowserManager(headless=True)

        with pytest.raises(RuntimeError, match="Browser context is not available"):
            manager.new_page()

        with pytest.raises(RuntimeError, match="Browser context is not available"):
            manager.save_storage_state("/tmp/s.json")

        with pytest.raises(RuntimeError, match="Browser context is not available"):
            manager.fetch_json("https://example.com")

    def test_context_manager(self, fake_playwright):
        mock_playwright = fake_playwright["playwright"]
        mock_browser = fake_playwright["browser"]
        mock_context = fake_playwright["context"]

        with BrowserManager(headless=True, chrome_path="/fake/chrome") as manager:
            assert manager._browser is not None
            assert manager._context is not None

        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    def test_new_page_without_request_logging(self, fake_playwright):
        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        manager.launch()

        page = manager.new_page(log_requests=False)
        assert page is not None


class TestSessionState:
    def test_default_fallback_to_headed(self):
        state = SessionState()
        assert state.fallback_to_headed is True
        assert state.storage_state_path is None
        assert state.resolve_storage_path() is None

    def test_resolve_storage_path_returns_none_when_missing(self, tmp_path):
        state = SessionState(storage_state_path=str(tmp_path / "nonexistent.json"))
        assert state.resolve_storage_path() is None

    def test_resolve_storage_path_returns_path_when_exists(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text("{}")
        state = SessionState(storage_state_path=str(p))
        resolved = state.resolve_storage_path()
        assert resolved == p


class TestBrowserSession:
    def test_start_and_stop(self, fake_playwright):
        mock_playwright = fake_playwright["playwright"]
        mock_browser = fake_playwright["browser"]
        mock_context = fake_playwright["context"]

        session = BrowserSession(chrome_path="/fake/chrome")
        session.start()

        assert session.manager is not None
        assert mock_playwright.chromium.launch.called

        session.stop()
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    def test_start_raises_if_already_started(self, fake_playwright):
        session = BrowserSession(chrome_path="/fake/chrome")
        session.start()

        with pytest.raises(TypeError, match="already started"):
            session.start()

    def test_stop_raises_if_not_started(self):
        session = BrowserSession()

        with pytest.raises(TypeError, match="not been started"):
            session.stop()

    def test_request_log_collects_entries(self):
        manager = BrowserManager(headless=True, chrome_path="/fake/chrome")
        log = []
        manager._request_log = log

        mock_page = Mock()
        mock_context = Mock()
        mock_context.new_page.return_value = mock_page
        manager._context = mock_context

        page = manager.new_page()
        assert page is mock_page

        mock_req = Mock()
        mock_req.method = "GET"
        mock_req.url = "https://example.com"
        mock_req.resource_type = "xhr"

        handlers = []
        for call in mock_page.on.call_args_list:
            cal = call[0]
            if len(cal) >= 2 and cal[0] == "request":
                handlers.append(cal[1])

        assert len(handlers) >= 2, "expected at least 2 request handlers (debug + log)"
        handlers[-1](mock_req)

        assert len(log) == 1
        assert log[0] == {"method": "GET", "url": "https://example.com", "type": "xhr"}

    def test_request_log_property(self):
        session = BrowserSession()
        session._request_log.append({"method": "GET", "url": "https://example.com", "type": "xhr"})
        assert session.request_log == [{"method": "GET", "url": "https://example.com", "type": "xhr"}]
        assert session.request_log is not session._request_log

    def test_context_manager_auto_starts(self, fake_playwright):
        mock_playwright = fake_playwright["playwright"]
        mock_browser = fake_playwright["browser"]
        mock_context = fake_playwright["context"]

        with BrowserSession(chrome_path="/fake/chrome") as session:
            assert session.manager is not None

        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        assert session.manager is None
