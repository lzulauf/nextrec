import pytest
from unittest.mock import AsyncMock, Mock


def _async_mock():
    """Return a Mock whose methods are AsyncMock by default."""
    return Mock(spec=[])


@pytest.fixture
def fake_playwright(monkeypatch):
    """Provide a fake Playwright factory that returns a mock playwright object.

    Tests should use this to avoid launching real browsers.
    """
    mock_pw = Mock()
    mock_pw.start = AsyncMock(return_value=mock_pw)
    mock_browser = Mock()
    mock_context = Mock()

    # Methods that are awaited in the async API must be AsyncMock
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_pw.stop = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_context.close = AsyncMock()
    mock_context.storage_state = AsyncMock()
    mock_context.new_page = AsyncMock()
    mock_context.request.fetch = AsyncMock()

    # Patch the async_playwright function used in nextrec.browser
    monkeypatch.setattr("nextrec.browser.async_playwright", lambda: mock_pw)

    return {"playwright": mock_pw, "browser": mock_browser, "context": mock_context}
