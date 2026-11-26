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


class TestValidationResult:
    @pytest.mark.asyncio
    async def test_rejection_is_logged_not_raised(self, mock_session, mock_httpx_client, make_config, make_slot, caplog):
        """isOk=false only warns: the site still lets the booking page continue."""
        from tests.conftest import make_mock_response
        mock_httpx_client.post = AsyncMock(return_value=make_mock_response(json_data={"isOk": False}))
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)

        result = await CartManager(mock_session).add_to_cart("fac-1", make_config(), make_slot())

        assert result.success
        assert mock_httpx_client.post.await_count == 2  # StoreOccupancyItems still sent
        assert "isOk=false" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_payload_matches_site(self, mock_session, mock_httpx_client, make_config, make_slot):
        """Send numberOfNights=1 and no numberOfAttendees, like the site's own request."""
        import urllib.parse
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)

        await CartManager(mock_session).add_to_cart("fac-1", make_config(), make_slot(), number_of_attendees=4)

        fields = dict(urllib.parse.parse_qsl(mock_httpx_client.post.await_args_list[0].kwargs["data"]))
        assert fields["numberOfNights"] == "1"
        assert "numberOfAttendees" not in fields

    @pytest.mark.asyncio
    async def test_non_json_response_is_not_a_rejection(self, mock_session, mock_httpx_client, make_config, make_slot):
        from tests.conftest import make_mock_response
        resp = make_mock_response()
        resp.json = Mock(side_effect=ValueError("not json"))
        mock_httpx_client.post = AsyncMock(return_value=resp)
        mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)

        result = await CartManager(mock_session).add_to_cart("fac-1", make_config(), make_slot())
        assert result.success
