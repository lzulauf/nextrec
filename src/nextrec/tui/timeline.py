from dataclasses import dataclass
from datetime import date, time
from typing import Dict, List, Optional, Set, Tuple

from rich.text import Text

from nextrec.models import FacilityConfig, TimeSlot

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


@dataclass
class TimelineCell:
    """A DataTable cell with metadata for click-to-filter resolution."""
    display: str = ""
    date: Optional[date] = None
    time: Optional[time] = None
    facility_id: Optional[str] = None

    def __rich__(self) -> Text:
        return Text.from_markup(self.display)


def build_timeline_rows(
    visible_results: List[SlotInfo],
    facility_names: Dict[str, str],
    mode: str,
    *,
    selected_time_pairs: Optional[Set[Tuple[date, time]]] = None,
    selected_facility_pairs: Optional[Set[Tuple[str, date, time]]] = None,
    time_window_start: Optional[time] = None,
    time_window_end: Optional[time] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
) -> Tuple[List[str], List[List[TimelineCell]], Dict[str, int]]:
    """Build timeline DataTable data.

    Returns (column_labels, rows, facility_col_map).
    facility_col_map maps facility_id to column index (0-based, for the
    first data column after the Time column).
    """
    if not visible_results:
        return [], [], {}

    selected_time_pairs = selected_time_pairs or set()
    selected_facility_pairs = selected_facility_pairs or set()

    from datetime import timedelta

    def _slot_rows():
        if date_start and date_end:
            # Show all days in the requested range
            days = [date_start + timedelta(days=i) for i in range((date_end - date_start).days + 1)]
        else:
            # Fall back to days that have results
            day_bounds: Dict[date, List[int]] = {}
            for _, _, s in visible_results:
                day_bounds.setdefault(s.date, []).append(s.start_time.hour)
            days = sorted(day_bounds.keys())

        for dt in days:
            hours = [s.start_time.hour for _, _, s in visible_results if s.date == dt]
            lo = time_window_start.hour if time_window_start else (min(hours) if hours else 8)
            hi = time_window_end.hour if time_window_end else (max(hours) if hours else 20)
            for h in range(lo, hi + 1):
                for m in (0, 30):
                    t = time(h, m)
                    if time_window_start and t < time_window_start:
                        continue
                    if time_window_end and t >= time_window_end:
                        continue
                    yield (dt, h, m)

    def _has_slot(dt: date, hour: int, minute: int, fid: Optional[str] = None) -> bool:
        for f_id, _, s in visible_results:
            if fid is not None and f_id != fid:
                continue
            if s.date == dt and s.start_time.hour == hour and s.start_time.minute == minute:
                return True
        return False

    def _time_selected(dt: date, t: time) -> bool:
        return (dt, t) in selected_time_pairs

    def _cell(display: str, d: date, t: time, fid: Optional[str] = None) -> TimelineCell:
        return TimelineCell(display=display, date=d, time=t, facility_id=fid)

    fac_ids: List[str] = []
    seen_fid: set = set()
    for fid, _, _ in visible_results:
        if fid not in seen_fid:
            seen_fid.add(fid)
            fac_ids.append(fid)

    fac_col_map: Dict[str, int] = {}
    for idx, fid in enumerate(fac_ids):
        fac_col_map[fid] = idx

    rows: List[List[TimelineCell]] = []

    if mode == "condensed":
        columns = ["Time", "Available"]
        prev_date: Optional[date] = None
        for dt, hour, minute in _slot_rows():
            t = time(hour, minute)
            if dt != prev_date:
                rows.append([
                    TimelineCell(display=f"── {dt.month}/{dt.day} ──", date=dt),
                    TimelineCell(display="───"),
                ])
            prev_date = dt
            found = _has_slot(dt, hour, minute)
            selected = _time_selected(dt, t)
            t_label = f"{hour:02d}:{minute:02d}"
            if found and selected:
                cell = "[bright_yellow]█[/bright_yellow]"
            elif found:
                cell = "[green]█[/green]"
            else:
                cell = "[dim]·[/dim]"
            rows.append([
                _cell(t_label, dt, t),
                _cell(cell, dt, t),
            ])
        return columns, rows, {}

    columns = ["Time"] + [facility_names.get(fid, fid[:12]) for fid in fac_ids]
    prev_date: Optional[date] = None
    for dt, hour, minute in _slot_rows():
        t = time(hour, minute)
        if dt != prev_date:
            sep = [TimelineCell(display=f"── {dt.month}/{dt.day} ──", date=dt)] + \
                  [TimelineCell(display="───") for _ in fac_ids]
            rows.append(sep)
        prev_date = dt
        t_label = f"{hour:02d}:{minute:02d}"
        row = [_cell(t_label, dt, t)]
        for fid in fac_ids:
            found = _has_slot(dt, hour, minute, fid)
            selected = (fid, dt, t) in selected_facility_pairs or _time_selected(dt, t)
            if found and selected:
                row.append(_cell("[bright_yellow]█[/bright_yellow]", dt, t, fid))
            elif found:
                row.append(_cell("[green]█[/green]", dt, t, fid))
            else:
                row.append(_cell("[dim]·[/dim]", dt, t, fid))
        rows.append(row)

    return columns, rows, fac_col_map
