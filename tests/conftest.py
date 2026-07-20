from datetime import date, time
from unittest.mock import AsyncMock, Mock

import httpx2
import pytest

from nextrec.models import DurationPrice, FacilityConfig, TimeSlot


def _async_mock():
    """Return a Mock whose methods are AsyncMock by default."""
    return Mock(spec=[])


@pytest.fixture
def fake_playwright(monkeypatch):
    """Provide a fake Playwright factory that returns a mock playwright object."""
    mock_pw = Mock()
    mock_pw.start = AsyncMock(return_value=mock_pw)
    mock_browser = Mock()
    mock_context = Mock()

    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_pw.stop = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_context.close = AsyncMock()
    mock_context.storage_state = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=Mock())
    mock_context.request.fetch = AsyncMock()

    monkeypatch.setattr("nextrec.browser.async_playwright", lambda: mock_pw)

    return {"playwright": mock_pw, "browser": mock_browser, "context": mock_context}


@pytest.fixture
def make_config():
    def _make(facility_id="fac-1", calendar_id="cal-1", service_id="svc-1",
              duration_prices=None):
        if duration_prices is None:
            duration_prices = [
                DurationPrice(id="dur-1", minutes=60, resident_price=5.0, non_resident_price=6.0),
            ]
        return FacilityConfig(
            facility_id=facility_id, calendar_id=calendar_id,
            service_id=service_id, program_id=service_id,
            duration_prices=duration_prices,
        )
    return _make


@pytest.fixture
def make_slot():
    def _make(ticks=639200664000000000, dt=date(2026, 7, 20),
              start=time(11, 0), end=time(12, 0), duration_minutes=60,
              is_disabled=False, base_slot_ticks=None):
        return TimeSlot(
            date=dt, start_time=start, end_time=end,
            ticks=ticks, duration_minutes=duration_minutes,
            duration_ticks=36000000000, is_disabled=is_disabled,
            base_slot_ticks=base_slot_ticks,
        )
    return _make


@pytest.fixture
def mock_session():
    session = Mock()
    session.manager = Mock()
    session.manager.new_page = AsyncMock()
    session.manager.load_storage_state = AsyncMock()
    session.start = AsyncMock()
    session.stop = AsyncMock()
    session.get_httpx_client = AsyncMock()
    return session


@pytest.fixture
def mock_httpx_client():
    client = Mock()
    client.get = AsyncMock(return_value=make_mock_response(text=_CSRF_HTML))
    client.post = AsyncMock(return_value=make_mock_response(json_data={}))
    client.close = AsyncMock()
    return client


def make_mock_response(text="", json_data=None, ok=True):
    resp = Mock()
    resp.text = text
    resp.json = Mock(return_value=json_data or {})
    resp.status_code = 200 if ok else 500
    if ok:
        resp.raise_for_status = Mock()
    else:
        def _raise():
            raise httpx2.HTTPStatusError("error", request=Mock(), response=resp)
        resp.raise_for_status = _raise
    return resp


_CSRF_HTML = '<html><form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="csrf-token"/></form></html>'
