from datetime import date, time
from unittest.mock import AsyncMock, Mock

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
    async def test_extract_csrf_returns_token(self):
        session = Mock()
        cm = CartManager(session)
        page = Mock()
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-abc")
        page.wait_for_selector = AsyncMock(return_value=element)
        assert await cm._extract_csrf(page) == "csrf-abc"
        page.wait_for_selector.assert_awaited_once()
        element.get_attribute.assert_awaited_once_with("value")

    @pytest.mark.asyncio
    async def test_extract_csrf_raises_when_missing(self):
        session = Mock()
        cm = CartManager(session)
        page = Mock()
        page.wait_for_selector = AsyncMock(return_value=None)
        with pytest.raises(CartError, match="not found"):
            await cm._extract_csrf(page)

    @pytest.mark.asyncio
    async def test_extract_csrf_raises_when_empty(self):
        session = Mock()
        cm = CartManager(session)
        page = Mock()
        element = Mock()
        element.get_attribute = AsyncMock(return_value="")
        page.wait_for_selector = AsyncMock(return_value=element)
        with pytest.raises(CartError, match="was empty"):
            await cm._extract_csrf(page)

    @pytest.mark.asyncio
    async def test_add_to_cart_success(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)

        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()

        validate_resp = Mock()
        validate_resp.ok = True
        validate_resp.status = 200
        store_resp = Mock()
        store_resp.ok = True
        store_resp.status = 200
        page.request.post = AsyncMock(side_effect=[validate_resp, store_resp])

        cm = CartManager(session)
        config = _make_config()
        slot = _make_slot()
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert result.facility_id == "fac-1"
        assert result.slot_date == date(2026, 7, 20)
        assert "Added 1 slot(s)" in result.message
        assert page.goto.called
        assert page.request.post.call_count == 2

    @pytest.mark.asyncio
    async def test_add_to_cart_idempotent(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()
        validate_resp = Mock()
        validate_resp.ok = True
        validate_resp.status = 200
        store_resp = Mock()
        store_resp.ok = True
        store_resp.status = 200
        page.request.post = AsyncMock(side_effect=[validate_resp, store_resp])

        cm = CartManager(session)
        config = _make_config()
        slot = _make_slot()
        await cm.add_to_cart("fac-1", config, slot)

        page.request.post.reset_mock()
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message
        page.request.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_validate_failure(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()
        validate_resp = Mock()
        validate_resp.ok = False
        validate_resp.status = 400
        validate_resp.status_text = "Bad Request"
        page.request.post = AsyncMock(return_value=validate_resp)

        cm = CartManager(session)
        with pytest.raises(CartError, match="ValidateFacilityBooking returned 400"):
            await cm.add_to_cart("fac-1", _make_config(), _make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_store_failure(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()
        validate_resp = Mock()
        validate_resp.ok = True
        validate_resp.status = 200
        store_resp = Mock()
        store_resp.ok = False
        store_resp.status = 500
        store_resp.status_text = "Server Error"
        page.request.post = AsyncMock(side_effect=[validate_resp, store_resp])

        cm = CartManager(session)
        with pytest.raises(CartError, match="StoreOccupancyItems returned 500"):
            await cm.add_to_cart("fac-1", _make_config(), _make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()

        ok = Mock(ok=True, status=200)
        page.request.post = AsyncMock(side_effect=[ok, ok, ok, ok])

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
        assert page.request.post.call_count == 4

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot_idempotent(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.set_default_navigation_timeout = AsyncMock()
        page.set_default_timeout = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        element = Mock()
        element.get_attribute = AsyncMock(return_value="csrf-token")
        page.wait_for_selector = AsyncMock(return_value=element)
        page.goto = AsyncMock()

        ok = Mock(ok=True, status=200)
        page.request.post = AsyncMock(side_effect=[ok, ok, ok, ok])

        cm = CartManager(session)
        config = _make_config()
        slot = TimeSlot(
            date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0),
            ticks=0, duration_minutes=60, duration_ticks=36000000000,
            is_disabled=False, base_slot_ticks=[0, 18000000000],
        )
        await cm.add_to_cart("fac-1", config, slot)
        page.request.post.reset_mock()
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message
        page.request.post.assert_not_called()
