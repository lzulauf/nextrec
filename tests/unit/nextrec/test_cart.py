from datetime import date, time
from unittest.mock import AsyncMock, Mock

import pytest

from nextrec.cart import CartError, CartManager
from nextrec.models import TimeSlot


class TestCartManager:
    def test_booking_key_unique(self, make_config, make_slot):
        cm = CartManager(Mock())
        k1 = cm._booking_key("a", make_slot(ticks=100))
        k2 = cm._booking_key("a", make_slot(ticks=200))
        k3 = cm._booking_key("b", make_slot(ticks=100))
        assert k1 != k2
        assert k1 != k3

    @pytest.mark.asyncio
    async def test_add_to_cart_success(self, mock_session, mock_httpx_client, make_config, make_slot):
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        config = make_config()
        slot = make_slot()
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert result.facility_id == "fac-1"
        assert result.slot_date == date(2026, 7, 20)
        assert "Added 1 slot(s)" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_idempotent(self, mock_session, mock_httpx_client, make_config, make_slot):
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        config = make_config()
        slot = make_slot()
        await cm.add_to_cart("fac-1", config, slot)

        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_validate_failure(self, mock_session, mock_httpx_client, make_config, make_slot):
        from tests.conftest import make_mock_response
        mock_httpx_client.post = AsyncMock(return_value=make_mock_response(ok=False))
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        with pytest.raises(CartError, match="ValidateFacilityBooking"):
            await cm.add_to_cart("fac-1", make_config(), make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_raises_on_store_failure(self, mock_session, mock_httpx_client, make_config, make_slot):
        from tests.conftest import make_mock_response
        ok_resp = make_mock_response(ok=True)
        fail_resp = make_mock_response(ok=False)
        mock_httpx_client.post = AsyncMock(side_effect=[ok_resp, fail_resp])
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        with pytest.raises(CartError, match="StoreOccupancyItems"):
            await cm.add_to_cart("fac-1", make_config(), make_slot())

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot(self, mock_session, mock_httpx_client, make_config):
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        config = make_config()
        slot = TimeSlot(
            date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0),
            ticks=0, duration_minutes=60, duration_ticks=36000000000,
            is_disabled=False, base_slot_ticks=[0, 18000000000],
        )
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Added 2 slot(s)" in result.message

    @pytest.mark.asyncio
    async def test_add_to_cart_multi_slot_idempotent(self, mock_session, mock_httpx_client, make_config):
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
        cm = CartManager(mock_session)
        config = make_config()
        slot = TimeSlot(
            date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0),
            ticks=0, duration_minutes=60, duration_ticks=36000000000,
            is_disabled=False, base_slot_ticks=[0, 18000000000],
        )
        await cm.add_to_cart("fac-1", config, slot)
        result = await cm.add_to_cart("fac-1", config, slot)

        assert result.success
        assert "Already added" in result.message
