from unittest.mock import AsyncMock, Mock

import pytest

from nextrec import checkout
from nextrec.checkout import (
    CartAddReport,
    NotLoggedInError,
    Pricing,
    SlotAddResult,
    add_slots_to_cart,
    build_booking_url,
    choose_fee,
    open_checkout,
    parse_pricing,
    summarize,
)

SITE = "https://cityofoakland.perfectmind.com"
PARTICIPANTS_URL = f"{SITE}/Clients/BookMe4EventParticipants?eventId=ev-1"
EXTRAS_URL = f"{SITE}/Clients/BookMe4Extras/Extras"
CART_URL = f"{SITE}/Clients/BookMe4Cart/Cart?memberId=m-1&waitListMode=False"
DEFAULT_FEES = [
    {"id": "m-1_p-non", "name": "Hourly Rental: Non-Resident"},
    {"id": "m-1_p-res", "name": "Hourly Rental: Resident"},
]


class FakeLocator:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    async def count(self):
        return 0 if self._selector in self._page.missing else 1

    async def is_checked(self):
        return self._page.checked.get(self._selector.split('"')[1] if '"' in self._selector else self._selector, False)

    async def check(self, force=False):
        self._page.checked[self._selector] = True

    async def wait_for(self, state="visible", timeout=None):
        if self._selector in self._page.missing:
            raise TimeoutError(f"{self._selector} never appeared")

    async def click(self):
        self._page.clicks.append(self._selector)
        if self._selector == checkout.PARTICIPANTS_NEXT:
            self._page.url = EXTRAS_URL
        elif self._selector.startswith("label[for="):
            fee_id = self._selector.split('"')[1]
            if fee_id not in self._page.unclickable_fees:
                self._page.checked[fee_id] = True


class FakeResponseContext:
    def __init__(self, page):
        self._page = page

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None and self._page.cart_status is None:
            if self._page.dialog_message and "dialog" in self._page.handlers:
                await self._page.handlers["dialog"](Mock(message=self._page.dialog_message, dismiss=AsyncMock()))
            raise TimeoutError("no cart response")
        return False

    @property
    def value(self):
        async def _value():
            status = self._page.cart_status
            self._page.url = CART_URL
            return Mock(ok=200 <= status < 400, status=status)
        return _value()


class FakePage:
    """Scripted stand-in for the Participants -> Extras -> Cart pages."""

    def __init__(self, landing_url=PARTICIPANTS_URL, fees=None, cart_status=200, missing=(),
                 participant_checked=True, unclickable_fees=(), dialog_message=None):
        self.landing_url = landing_url
        self.url = "about:blank"
        self.fees = DEFAULT_FEES if fees is None else fees
        self.cart_status = cart_status
        self.missing = set(missing)
        self.unclickable_fees = set(unclickable_fees)
        self.checked = {checkout.SELF_PARTICIPANT_CHECKBOX: participant_checked}
        self.clicks = []
        self.handlers = {}
        self.closed = False
        self.dialog_message = dialog_message

    def on(self, event, handler):
        self.handlers[event] = handler

    async def goto(self, url, wait_until=None):
        self.goto_url = url
        self.url = self.landing_url

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def wait_for_url(self, pattern, timeout=None):
        if checkout.EXTRAS_PATH not in self.url:
            raise TimeoutError("not on extras")

    async def eval_on_selector_all(self, selector, script):
        return list(self.fees)

    def expect_response(self, predicate, timeout=None):
        return FakeResponseContext(self)

    async def wait_for_load_state(self, state=None):
        pass

    async def close(self):
        self.closed = True


@pytest.fixture
def selection(make_config, make_slot):
    return ("fac-1", make_config(), make_slot())


@pytest.fixture
def booking_session(mock_session, mock_httpx_client):
    mock_session.get_httpx_client = AsyncMock(return_value=mock_httpx_client)
    return mock_session


def use_pages(session, *pages):
    session.manager.new_page = AsyncMock(side_effect=list(pages))


class TestParsePricing:
    @pytest.mark.parametrize("value, expected", [
        pytest.param(None, Pricing.RESIDENT, id="missing-defaults-to-resident"),
        pytest.param("", Pricing.RESIDENT, id="blank"),
        pytest.param("Resident", Pricing.RESIDENT, id="resident"),
        pytest.param("non-resident", Pricing.NON_RESIDENT, id="non-resident"),
        pytest.param("non_resident", Pricing.NON_RESIDENT, id="underscore"),
        pytest.param("Nonresident", Pricing.NON_RESIDENT, id="one-word"),
    ])
    def test_accepted_values(self, value, expected):
        assert parse_pricing(value) is expected

    def test_rejects_unknown_value(self):
        with pytest.raises(ValueError, match="resident"):
            parse_pricing("senior")


class TestChooseFee:
    NAMES = ["Hourly Rental: Non-Resident", "Hourly Rental: Resident"]

    @pytest.mark.parametrize("pricing, expected", [
        pytest.param(Pricing.RESIDENT, 1, id="resident"),
        pytest.param(Pricing.NON_RESIDENT, 0, id="non-resident"),
    ])
    def test_picks_matching_fee(self, pricing, expected):
        assert choose_fee(self.NAMES, pricing) == expected

    @pytest.mark.parametrize("names", [
        pytest.param(["Hourly Rental"], id="no-match"),
        pytest.param(["Resident A", "Resident B"], id="ambiguous"),
        pytest.param([], id="no-fees"),
    ])
    def test_returns_none_when_a_person_should_choose(self, names):
        assert choose_fee(names, Pricing.RESIDENT) is None


class TestBuildBookingUrl:
    def test_contains_slot_parameters(self, make_config, make_slot):
        url = build_booking_url("fac-1", make_config(), make_slot(), attendees=4)
        assert url.startswith(f"{SITE}/SocialSite/BookMe4EventParticipants/FacilityBooking?facilityId=fac-1")
        assert "&calendarId=cal-1&serviceId=svc-1&duration=60&durationId=dur-1" in url
        assert "&startDateTimeTicks=639200664000000000&numberOfAttendees=4" in url


@pytest.mark.asyncio
class TestAddSlotsToCart:
    async def test_adds_slot_and_returns_cart_url(self, booking_session, selection):
        page = FakePage()
        use_pages(booking_session, page)

        report = await add_slots_to_cart(booking_session, [selection], attendees=1)

        assert [r.added for r in report.results] == [True]
        assert report.cart_url == CART_URL
        assert 'label[for="m-1_p-res"]' in page.clicks
        assert page.clicks[-1] == checkout.EXTRAS_ADD_TO_CART
        assert page.closed

    async def test_non_resident_pricing_selects_non_resident_fee(self, booking_session, selection):
        page = FakePage()
        use_pages(booking_session, page)

        await add_slots_to_cart(booking_session, [selection], attendees=1, pricing=Pricing.NON_RESIDENT)

        assert 'label[for="m-1_p-non"]' in page.clicks

    async def test_ticks_participant_when_not_preselected(self, booking_session, selection):
        page = FakePage(participant_checked=False)
        use_pages(booking_session, page)

        report = await add_slots_to_cart(booking_session, [selection], attendees=1)

        assert report.results[0].added

    @pytest.mark.parametrize("page_kwargs, reason", [
        pytest.param({"fees": [{"id": "x", "name": "Hourly Rental"}]}, "no single Resident fee", id="no-matching-fee"),
        pytest.param({"cart_status": 500}, "HTTP 500", id="cart-error"),
        pytest.param({"cart_status": None}, "no cart response", id="cart-timeout"),
        pytest.param({"landing_url": f"{SITE}/Clients/Other"}, "unexpected page", id="unexpected-page"),
        pytest.param({"missing": [checkout.SELF_PARTICIPANT_CHECKBOX]}, "no participant", id="no-participant"),
        pytest.param({"missing": [checkout.EXTRAS_ADD_TO_CART]}, "TimeoutError", id="no-add-button"),
        pytest.param({"unclickable_fees": ["m-1_p-res"]}, "could not select", id="fee-not-selected"),
        pytest.param({"cart_status": None, "dialog_message": "Cart already has a booking"},
                     "site said: Cart already has a booking", id="site-dialog"),
    ])
    async def test_failure_is_reported_not_raised(self, booking_session, selection, page_kwargs, reason):
        page = FakePage(**page_kwargs)
        use_pages(booking_session, page)

        report = await add_slots_to_cart(booking_session, [selection], attendees=1)

        [result] = report.results
        assert not result.added
        assert reason in result.message
        assert result.booking_url.startswith(f"{SITE}/SocialSite/BookMe4EventParticipants/FacilityBooking")
        assert report.cart_url is None
        assert page.closed

    async def test_mixed_batch_keeps_going(self, booking_session, make_config, make_slot):
        first = ("fac-1", make_config(), make_slot(ticks=1))
        second = ("fac-2", make_config(facility_id="fac-2"), make_slot(ticks=2))
        use_pages(booking_session, FakePage(cart_status=500), FakePage())

        report = await add_slots_to_cart(booking_session, [first, second], attendees=1)

        assert [r.added for r in report.results] == [False, True]
        assert report.cart_url == CART_URL

    async def test_hold_failure_skips_browser(self, booking_session, mock_httpx_client, selection):
        mock_httpx_client.get = AsyncMock(side_effect=RuntimeError("network down"))
        booking_session.manager.new_page = AsyncMock()

        report = await add_slots_to_cart(booking_session, [selection], attendees=1)

        assert "hold failed" in report.results[0].message
        booking_session.manager.new_page.assert_not_called()

    async def test_sign_in_redirect_raises(self, booking_session, selection):
        use_pages(booking_session, FakePage(landing_url=f"{SITE}/Clients/MemberRegistration/MemberSignIn?x"))

        with pytest.raises(NotLoggedInError):
            await add_slots_to_cart(booking_session, [selection], attendees=1)


def _result(make_slot, added, url):
    return SlotAddResult("fac-1", make_slot(), added, url, "added" if added else "no cart response")


@pytest.mark.asyncio
class TestOpenCheckout:
    async def test_opens_cart_and_failed_slots(self, mock_session, make_slot):
        pages = [Mock(goto=AsyncMock()), Mock(goto=AsyncMock())]
        mock_session.manager.new_page = AsyncMock(side_effect=pages)
        report = CartAddReport(
            results=(_result(make_slot, True, "u-ok"), _result(make_slot, False, "u-failed")),
            cart_url=CART_URL,
        )

        assert await open_checkout(mock_session, report) == 2
        assert [p.goto.call_args.args[0] for p in pages] == [CART_URL, "u-failed"]

    async def test_opens_nothing_for_empty_report(self, mock_session):
        assert await open_checkout(mock_session, CartAddReport(results=(), cart_url=None)) == 0
        mock_session.manager.new_page.assert_not_called()


class TestSummarize:
    def test_all_added(self, make_slot):
        report = CartAddReport(results=(_result(make_slot, True, "u"),) * 2, cart_url=CART_URL)
        assert summarize(report) == "Added 2/2 to cart"

    def test_mentions_failures(self, make_slot):
        report = CartAddReport(
            results=(_result(make_slot, True, "u"), _result(make_slot, False, "u2")), cart_url=CART_URL,
        )
        assert summarize(report) == "Added 1/2 to cart; 1 need a manual click (no cart response)"


class TestWriteReportLog:
    def test_appends_one_line_per_slot(self, tmp_path, make_slot):
        report = CartAddReport(
            results=(_result(make_slot, True, "u"), _result(make_slot, False, "u2")), cart_url=CART_URL,
        )
        log = tmp_path / "logs" / "booking.log"
        checkout.write_report_log(report, log)
        checkout.write_report_log(report, log)

        lines = log.read_text().splitlines()
        assert len(lines) == 6
        assert "Added 1/2 to cart" in lines[0]
        assert "MANUAL" in lines[2] and "no cart response" in lines[2]


@pytest.mark.asyncio
async def test_open_checkout_survives_slow_tab(mock_session):
    page = Mock(goto=AsyncMock(side_effect=TimeoutError("slow")))
    mock_session.manager.new_page = AsyncMock(return_value=page)
    report = CartAddReport(results=(), cart_url=CART_URL)
    assert await open_checkout(mock_session, report) == 1
