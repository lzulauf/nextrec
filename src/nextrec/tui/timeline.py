from datetime import date, time
from typing import Dict, List, Optional, Set, Tuple

from nextrec.models import FacilityConfig, TimeSlot

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


def build_timeline_rows(
    visible_results: List[SlotInfo],
    facility_names: Dict[str, str],
    mode: str,
    *,
    selected_time_ranges: Optional[Set[Tuple[time, time]]] = None,
    selected_facility_times: Optional[Set[Tuple[str, time]]] = None,
) -> Tuple[List[str], List[List[str]], Dict[str, int]]:
    """Build timeline DataTable data.

    Returns (column_labels, rows, facility_col_map).
    facility_col_map maps facility_id to column index (0-based, for the
    first data column after the Time column).
    """
    if not visible_results:
        return [], [], {}

    selected_time_ranges = selected_time_ranges or set()
    selected_facility_times = selected_facility_times or set()

    def _slot_rows():
        day_bounds: Dict[date, List[int]] = {}
        for _, _, s in visible_results:
            day_bounds.setdefault(s.date, []).append(s.start_time.hour)
        for dt, hours in sorted(day_bounds.items()):
            lo = min(hours)
            hi = max(hours)
            for h in range(lo, hi + 1):
                for m in (0, 30):
                    yield (dt, h, m)

    def _has_slot(dt: date, hour: int, minute: int, fid: Optional[str] = None) -> bool:
        for f_id, _, s in visible_results:
            if fid is not None and f_id != fid:
                continue
            if s.date == dt and s.start_time.hour == hour and s.start_time.minute == minute:
                return True
        return False

    def _time_in_ranges(t: time) -> bool:
        for lo, hi in selected_time_ranges:
            if lo <= t <= hi:
                return True
        return False

    fac_ids: List[str] = []
    seen_fid: set = set()
    for fid, _, _ in visible_results:
        if fid not in seen_fid:
            seen_fid.add(fid)
            fac_ids.append(fid)

    fac_col_map: Dict[str, int] = {}
    for idx, fid in enumerate(fac_ids):
        fac_col_map[fid] = idx

    rows: List[List[str]] = []

    if mode == "condensed":
        columns = ["Time", "Available"]
        prev_date: Optional[date] = None
        for dt, hour, minute in _slot_rows():
            t = time(hour, minute)
            if prev_date is None:
                rows.append([f"── {dt.month}/{dt.day} ──", ""])
            elif dt != prev_date:
                rows.append(["───", f"── {dt.month}/{dt.day} ──"])
            prev_date = dt
            found = _has_slot(dt, hour, minute)
            selected = _time_in_ranges(t)
            t_label = f"{hour:02d}:{minute:02d}"
            if found and selected:
                cell = "[bright_yellow]█[/bright_yellow]"
            elif found:
                cell = "[green]█[/green]"
            else:
                cell = "[dim]·[/dim]"
            rows.append([t_label, cell])
        return columns, rows, {}

    columns = ["Time"] + [facility_names.get(fid, fid[:12]) for fid in fac_ids]
    prev_date: Optional[date] = None
    columns_total = len(fac_ids) + 1
    for dt, hour, minute in _slot_rows():
        t = time(hour, minute)
        if prev_date is None:
            sep = [f"── {dt.month}/{dt.day} ──"] + ["" for _ in fac_ids]
            rows.append(sep)
        elif dt != prev_date:
            sep = ["───"] + [f"── {dt.month}/{dt.day} ──" for _ in fac_ids]
            rows.append(sep)
        prev_date = dt
        t_label = f"{hour:02d}:{minute:02d}"
        row = [t_label]
        for fid in fac_ids:
            found = _has_slot(dt, hour, minute, fid)
            selected = (fid, t) in selected_facility_times or _time_in_ranges(t)
            if found and selected:
                row.append("[bright_yellow]█[/bright_yellow]")
            elif found:
                row.append("[green]█[/green]")
            else:
                row.append("[dim]·[/dim]")
        rows.append(row)

    return columns, rows, fac_col_map
