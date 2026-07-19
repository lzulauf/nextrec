import dataclasses
from datetime import date, time
from typing import List, Optional


@dataclasses.dataclass(frozen=True)
class Constraint:
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None
    keywords: Optional[str] = None
    facility_types: Optional[List[str]] = None
    min_capacity: Optional[int] = None
    max_capacity: Optional[int] = None


@dataclasses.dataclass(frozen=True)
class AvailabilitySlot:
    date: str
    start_time: str
    end_time: str
    book_button_selector: Optional[str] = None
    item_id: Optional[str] = None


@dataclasses.dataclass(frozen=True)
class DurationPrice:
    id: str
    minutes: int
    resident_price: float
    non_resident_price: float


@dataclasses.dataclass(frozen=True)
class FacilityConfig:
    facility_id: str
    calendar_id: str
    service_id: str
    program_id: str
    duration_prices: List[DurationPrice]


@dataclasses.dataclass(frozen=True)
class TimeSlot:
    date: date
    start_time: time
    end_time: time
    ticks: int
    duration_minutes: int
    duration_ticks: int
    is_disabled: bool
    title: str = "Reserve"


@dataclasses.dataclass(frozen=True)
class Facility:
    id: str
    name: str
    location: str
    type: str
    availability: List[AvailabilitySlot]
    capacity: Optional[int] = None


@dataclasses.dataclass(frozen=True)
class BookingAction:
    facility_id: str
    slot_id: str
    quantity: int = 1
    metadata: Optional[dict] = None


@dataclasses.dataclass(frozen=True)
class BookingResult:
    success: bool
    facility_id: str
    slot_date: date
    slot_start: time
    message: str = ""
