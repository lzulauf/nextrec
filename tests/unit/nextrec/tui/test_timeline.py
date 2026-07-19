from datetime import date, time

from nextrec.models import DurationPrice, FacilityConfig, TimeSlot
from nextrec.tui.timeline import build_timeline_rows

_DP = DurationPrice(id="dp1", minutes=60, resident_price=10.0, non_resident_price=12.0)
_CFG = FacilityConfig(
    facility_id="f1", calendar_id="c1", service_id="s1",
    program_id="s1", duration_prices=[_DP],
)
_CFG2 = FacilityConfig(
    facility_id="f2", calendar_id="c2", service_id="s2",
    program_id="s2", duration_prices=[_DP],
)


def _slot(date, hour, minute):
    return TimeSlot(
        date=date, start_time=time(hour, minute), end_time=time(hour + 1, minute),
        ticks=0, duration_minutes=60, duration_ticks=36000000000, is_disabled=False,
    )


class TestBuildTimelineRows:
    def test_empty_results(self):
        cols, rows = build_timeline_rows([], {}, "condensed")
        assert cols == []
        assert rows == []

    def test_condensed_single_day(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows = build_timeline_rows(results, {}, "condensed")
        assert cols == ["Time", "Available"]
        assert rows[0] == ["── 7/25 ──", ""]
        assert rows[1] == ["08:00", "[green]█[/green]"]
        assert rows[2] == ["08:30", "[dim]·[/dim]"]

    def test_condensed_missing_slots_dim(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 9, 0))]
        cols, rows = build_timeline_rows(results, {}, "condensed")
        assert rows[0] == ["── 7/25 ──", ""]
        assert rows[1] == ["09:00", "[green]█[/green]"]
        assert rows[2] == ["09:30", "[dim]·[/dim]"]

    def test_condensed_two_days(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f1", _CFG, _slot(date(2026, 7, 26), 10, 0)),
        ]
        cols, rows = build_timeline_rows(results, {}, "condensed")
        assert rows[0] == ["── 7/25 ──", ""]
        assert rows[3] == ["───", "── 7/26 ──"]
        assert rows[4] == ["10:00", "[green]█[/green]"]

    def test_full_single_facility(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows = build_timeline_rows(results, {"f1": "Court A"}, "full")
        assert cols == ["Time", "Court A"]
        assert rows[0] == ["── 7/25 ──", ""]
        assert rows[1] == ["08:00", "[green]█[/green]"]

    def test_full_two_facilities(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f2", _CFG2, _slot(date(2026, 7, 25), 8, 0)),
        ]
        cols, rows = build_timeline_rows(results, {"f1": "Crt A", "f2": "Crt B"}, "full")
        assert cols == ["Time", "Crt A", "Crt B"]
        assert rows[1] == ["08:00", "[green]█[/green]", "[green]█[/green]"]

    def test_full_facility_dot_per_column(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f2", _CFG2, _slot(date(2026, 7, 25), 9, 0)),
        ]
        cols, rows = build_timeline_rows(results, {"f1": "Crt A", "f2": "Crt B"}, "full")
        assert cols == ["Time", "Crt A", "Crt B"]
        assert rows[0] == ["── 7/25 ──", "", ""]
        assert rows[1] == ["08:00", "[green]█[/green]", "[dim]·[/dim]"]
        assert rows[3] == ["09:00", "[dim]·[/dim]", "[green]█[/green]"]

    def test_time_filter_narrows(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f1", _CFG, _slot(date(2026, 7, 25), 10, 0)),
        ]
        cols, rows = build_timeline_rows(
            results, {}, "condensed",
            time_filter=(time(10, 0), time(10, 0)),
        )
        assert len(rows) == 2
        assert rows[0] == ["── 7/25 ──", ""]
        assert rows[1] == ["10:00", "[green]█[/green]"]

    def test_facility_name_used_directly(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows = build_timeline_rows(
            results, {"f1": "Montclair PB Court # 1"}, "full",
        )
        assert cols[1] == "Montclair PB Court # 1"

    def test_falls_back_to_fid_prefix(self):
        results = [("abc123def456", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows = build_timeline_rows(results, {}, "full")
        assert cols[1] == "abc123def456"
