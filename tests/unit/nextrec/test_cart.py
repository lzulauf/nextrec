from datetime import date, time
from unittest.mock import AsyncMock, Mock

import httpx2
import pytest

from nextrec.cart import CartError, CartManager
from nextrec.models import BookingResult, DurationPrice, FacilityConfig, TimeSlot


def _make_config(facility_id: str = "fac-1") -> FacilityConfig:
    return FacilityConfig(
        facility_id=facility_id,
        calendar_id="cal-1",
        service_id="svc-1",
        program_id="svc-1",
        duration_prices=[DurationPrice(id="dur-1", minutes=60, resident_price=5.0, non_resident_price=6.0)],
    )


def _make_slot(ticks: int = 639200664000000000) -> TimeSlot:
    return TimeSlot(
        date=date(2026, 7, 20),
        start_time=time(11, 0),
        end_time=time(12, 0),
        ticks=ticks,
        duration_minutes=60,
        duration_ticks=36000000000,
        is_disabled=False,
    )


_CSRF_HTML = '<html><form id="AjaxAntiForgeryForm"><input name="__RequestVerificationToken" value="csrf-token"/></form></html>'


def _mock_resp(text: str = "", json_data: dict = None, ok: bool = True):
    resp = Mock()
    resp.text = text
    resp.json = Mock(return_value=json_data or {})
    resp.status_code = 200 if ok else (500 if ok else 500)
    if ok:
        resp.raise_for_status = Mock()
    else:
        def _raise():
            raise httpx2.HTTPStatusError("error", request=Mock(), response=resp)
        resp.raise_for_status = _raise
    return resp


def _make_http_client():
    client = Mock()
    client.get = AsyncMock(return_value=_mock_resp(text=_CSRF_HTML))
    client.post = AsyncMock(return_value=_mock_resp(json_data={}))
    return client


class TestCartManager:
    def test_booking_key_unique(self):
        session = Mock()
        cm = CartManager(session)
        k1 = cm._booking_key("a", _make_slot(100))
        k2 = cm._booking_key("a", _make_slot(200))
        k3 = cm._booking_key("b", _make_slot(100))
        assert k1 != k2
        assert k1 != k3

    @pytest.mark.asyncio
    async def test_add_to_cart_success(self):
        session = Mock()
        session.get_httpx_client = AsyncMock(return_value=_make_http_client())
        cm = CartManager(session)
        config = _make_config()
        slot = _make_slot()
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert result.facility_id == "fac-1"
        assert result.slot_date == date(2026, 7, 20)
        assert "Added 1 slot(s)" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_idempotent(self):
        session = Mock()
        session.get_httpx_client = AsyncMock(return_value=_make_http_client())
        cm = CartManager(session)
        config = _make_config()
        slot = _make_slot()
        await cm.add_to_cart("fac-1", config, slot)

        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_validate_failure(self):
        session = Mock()
        client = _make_http_client()
        client.post = AsyncMock(return_value=_mock_resp(ok=False))
        session.get_httpx_client = AsyncMock(return_value=client)
        cm = CartManager(session)
        with pytest.raises(CartError, match="ValidateFacilityBooking"):
            await cm.add_to_cart("fac-1", _make_config(), _make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_store_failure(self):
        session = Mock()
        client = _make_http_client()
        ok_resp = _mock_resp(ok=True)
        fail_resp = _mock_resp(ok=False)
        client.post = AsyncMock(side_effect=[ok_resp, fail_resp])
        session.get_httpx_client = AsyncMock(return_value=client)
        cm = CartManager(session)
        with pytest.raises(CartError, match="StoreOccupancyItems"):
            await cm.add_to_cart("fac-1", _make_config(), _make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot(self):
        session = Mock()
        session.get_httpx_client = AsyncMock(return_value=_make_http_client())
        cm = CartManager(session)
        config = _make_config()
        slot = TimeSlot(
            date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0),
            ticks=0, duration_minutes=60, duration_ticks=36000000000,
            is_disabled=False, base_slot_ticks=[0, 18000000000],
        )
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Added 2 slot(s)" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot_idempotent(self):
        session = Mock()
        session.get_httpx_client = AsyncMock(return_value=_make_http_client())
        cm = CartManager(session)
        config = _make_config()
        slot = TimeSlot(
            date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0),
            ticks=0, duration_minutes=60, duration_ticks=36000000000,
            is_disabled=False, base_slot_ticks=[0, 18000000000],
        )
        await cm.add_to_cart("fac-1", config, slot)
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message
