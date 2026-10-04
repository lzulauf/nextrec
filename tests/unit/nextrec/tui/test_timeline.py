from datetime import date, time

from nextrec.models import DurationPrice, FacilityConfig, TimeSlot
from nextrec.tui.timeline import TimelineCell, build_timeline_rows

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


def _labels(row):
    return [c.display if isinstance(c, TimelineCell) else c for c in row]


class TestBuildTimelineRows:
    def test_empty_results(self):
        cols, rows, fcm = build_timeline_rows([], {}, "condensed")
        assert cols == []
        assert rows == []
        assert fcm == {}

    def test_condensed_single_day(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows, fcm = build_timeline_rows(results, {}, "condensed")
        assert cols == ["Time", "Available"]
        assert fcm == {}
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[1]) == ["08:00", "[green]█[/green]"]
        assert _labels(rows[2]) == ["08:30", "[dim]·[/dim]"]
        assert rows[1][0].date == date(2026, 7, 25)
        assert rows[1][0].time == time(8, 0)

    def test_condensed_missing_slots_dim(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 9, 0))]
        cols, rows, fcm = build_timeline_rows(results, {}, "condensed")
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[1]) == ["09:00", "[green]█[/green]"]
        assert _labels(rows[2]) == ["09:30", "[dim]·[/dim]"]

    def test_condensed_two_days(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f1", _CFG, _slot(date(2026, 7, 26), 10, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(results, {}, "condensed")
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[3]) == ["── 7/26 ──", "───"]
        assert _labels(rows[4]) == ["10:00", "[green]█[/green]"]
        assert rows[4][0].date == date(2026, 7, 26)
        assert rows[4][0].time == time(10, 0)

    def test_full_single_facility(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows, fcm = build_timeline_rows(results, {"f1": "Court A"}, "full")
        assert cols == ["Time", "Court A"]
        assert fcm == {"f1": 0}
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[1]) == ["08:00", "[green]█[/green]"]
        assert rows[1][1].facility_id == "f1"

    def test_full_two_facilities(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f2", _CFG2, _slot(date(2026, 7, 25), 8, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(results, {"f1": "Crt A", "f2": "Crt B"}, "full")
        assert cols == ["Time", "Crt A", "Crt B"]
        assert fcm == {"f1": 0, "f2": 1}
        assert _labels(rows[1]) == ["08:00", "[green]█[/green]", "[green]█[/green]"]

    def test_full_facility_dot_per_column(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f2", _CFG2, _slot(date(2026, 7, 25), 9, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(results, {"f1": "Crt A", "f2": "Crt B"}, "full")
        assert cols == ["Time", "Crt A", "Crt B"]
        assert _labels(rows[0]) == ["── 7/25 ──", "───", "───"]
        assert _labels(rows[1]) == ["08:00", "[green]█[/green]", "[dim]·[/dim]"]
        assert _labels(rows[3]) == ["09:00", "[dim]·[/dim]", "[green]█[/green]"]

    def test_selected_time_range_condensed(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f1", _CFG, _slot(date(2026, 7, 25), 10, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(
            results, {}, "condensed",
            selected_time_pairs={(date(2026, 7, 25), time(10, 0))},
        )
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[5]) == ["10:00", "[bright_yellow]█[/bright_yellow]"]
        assert _labels(rows[1]) == ["08:00", "[green]█[/green]"]

    def test_selected_facility_time_full(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f2", _CFG2, _slot(date(2026, 7, 25), 8, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(
            results, {"f1": "Crt A", "f2": "Crt B"}, "full",
            selected_facility_pairs={("f1", date(2026, 7, 25), time(8, 0))},
        )
        assert _labels(rows[0]) == ["── 7/25 ──", "───", "───"]
        assert _labels(rows[1]) == ["08:00", "[bright_yellow]█[/bright_yellow]", "[green]█[/green]"]

    def test_facility_name_used_directly(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows, fcm = build_timeline_rows(
            results, {"f1": "Montclair PB Court # 1"}, "full",
        )
        assert cols[1] == "Montclair PB Court # 1"

    def test_full_two_dat_date_separator(self):
        results = [
            ("f1", _CFG, _slot(date(2026, 7, 25), 8, 0)),
            ("f1", _CFG, _slot(date(2026, 7, 26), 10, 0)),
        ]
        cols, rows, fcm = build_timeline_rows(results, {"f1": "Court A"}, "full")
        assert _labels(rows[0]) == ["── 7/25 ──", "───"]
        assert _labels(rows[3]) == ["── 7/26 ──", "───"]
        assert _labels(rows[4]) == ["10:00", "[green]█[/green]"]
        results = [("abc123def456", _CFG, _slot(date(2026, 7, 25), 8, 0))]
        cols, rows, fcm = build_timeline_rows(results, {}, "full")
        assert cols[1] == "abc123def456"

    def test_condensed_12h_format(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 14, 0))]
        cols, rows, fcm = build_timeline_rows(results, {}, "condensed", time_format="12h")
        assert _labels(rows[1]) == ["2:00pm", "[green]█[/green]"]
        assert _labels(rows[2]) == ["2:30pm", "[dim]·[/dim]"]

    def test_full_12h_format(self):
        results = [("f1", _CFG, _slot(date(2026, 7, 25), 14, 0))]
        cols, rows, fcm = build_timeline_rows(results, {"f1": "Court A"}, "full", time_format="12h")
        assert _labels(rows[1]) == ["2:00pm", "[green]█[/green]"]

    def test_12h_am_pm_boundaries(self):
        am_slot = _slot(date(2026, 7, 25), 8, 0)
        noon_slot = _slot(date(2026, 7, 25), 12, 0)
        pm_slot = _slot(date(2026, 7, 25), 14, 0)
        results = [("f1", _CFG, s) for s in (am_slot, noon_slot, pm_slot)]
        cols, rows, fcm = build_timeline_rows(results, {}, "condensed", time_format="12h")
        time_labels = [label for row in rows for label in _labels(row) if label.startswith("TimelineCell")]
        displays = [_labels(row)[0] for row in rows if "──" not in _labels(row)[0]]
        assert "8:00am" in displays
        assert "12:00pm" in displays
        assert "2:00pm" in displays
