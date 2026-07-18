from datetime import date, time

from nextrec.models import AvailabilitySlot, BookingAction, Constraint, Facility


class TestConstraint:
    def test_defaults(self):
        c = Constraint()
        assert c.start_date is None
        assert c.end_date is None
        assert c.keywords is None
        assert c.facility_types is None
        assert c.min_capacity is None
        assert c.max_capacity is None
        assert c.time_window_start is None
        assert c.time_window_end is None

    def test_partial_fields(self):
        d = date(2026, 7, 20)
        c = Constraint(start_date=d, keywords="soccer", min_capacity=10)
        assert c.start_date == d
        assert c.keywords == "soccer"
        assert c.min_capacity == 10
        assert c.end_date is None

    def test_immutable(self):
        c = Constraint(start_date=date(2026, 7, 20))
        try:
            c.start_date = date(2026, 7, 21)
            assert False, "should be frozen"
        except AttributeError:
            pass

    def test_with_times(self):
        c = Constraint(time_window_start=time(8, 0), time_window_end=time(18, 0))
        assert c.time_window_start == time(8, 0)
        assert c.time_window_end == time(18, 0)


class TestAvailabilitySlot:
    def test_minimal(self):
        slot = AvailabilitySlot(date="2026-07-20", start_time="09:00", end_time="11:00")
        assert slot.date == "2026-07-20"
        assert slot.start_time == "09:00"
        assert slot.end_time == "11:00"
        assert slot.book_button_selector is None
        assert slot.item_id is None

    def test_full(self):
        slot = AvailabilitySlot(
            date="2026-07-20",
            start_time="09:00",
            end_time="11:00",
            book_button_selector=".btn-book",
            item_id="item-123",
        )
        assert slot.book_button_selector == ".btn-book"
        assert slot.item_id == "item-123"


class TestFacility:
    def test_minimal(self):
        f = Facility(id="1", name="Soccer Field", location="Park", type="Field", availability=[])
        assert f.id == "1"
        assert f.name == "Soccer Field"
        assert f.capacity is None
        assert f.availability == []

    def test_with_availability(self):
        slot = AvailabilitySlot(date="2026-07-20", start_time="09:00", end_time="11:00")
        f = Facility(id="2", name="Tennis Court", location="Club", type="Court", availability=[slot])
        assert len(f.availability) == 1
        assert f.availability[0].date == "2026-07-20"

    def test_with_capacity(self):
        f = Facility(id="3", name="Large Hall", location="Center", type="Room", capacity=100, availability=[])
        assert f.capacity == 100


class TestBookingAction:
    def test_minimal(self):
        a = BookingAction(facility_id="1", slot_id="slot-1")
        assert a.facility_id == "1"
        assert a.slot_id == "slot-1"
        assert a.quantity == 1
        assert a.metadata is None

    def test_full(self):
        a = BookingAction(facility_id="1", slot_id="slot-1", quantity=3, metadata={"key": "val"})
        assert a.quantity == 3
        assert a.metadata == {"key": "val"}
