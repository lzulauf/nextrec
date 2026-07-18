import pytest
from unittest.mock import Mock


@pytest.fixture
def fake_playwright(monkeypatch):
    """Provide a fake Playwright factory that returns a mock playwright object.

    Tests should use this to avoid launching real browsers.
    """
    mock_pw = Mock()
    # design the mock to mimic the sync_playwright() return value used by BrowserManager
    mock_pw.start.return_value = mock_pw
    mock_browser = Mock()
    mock_context = Mock()
    mock_pw.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context

    # Patch the sync_playwright function used in nextrec.browser
    monkeypatch.setattr("nextrec.browser.sync_playwright", lambda: mock_pw)

    return {"playwright": mock_pw, "browser": mock_browser, "context": mock_context}
