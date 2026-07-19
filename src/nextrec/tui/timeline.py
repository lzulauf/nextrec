from datetime import date, time
from typing import Dict, List, Optional, Tuple

from nextrec.models import FacilityConfig, TimeSlot

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


def build_timeline_rows(
    visible_results: List[SlotInfo],
    facility_names: Dict[str, str],
    mode: str,
    *,
    time_filter: Optional[Tuple[time, time]] = None,
) -> Tuple[List[str], List[List[str]]]:
    """Build timeline DataTable data. Returns (column_labels, rows).

    Each row is a list of cell label strings (already marked up for
    Textual's rich-text rendering, e.g. ``[green]|``).
    """

    if not visible_results:
        return [], []

    def _slot_rows():
        day_bounds: Dict[date, List[int]] = {}
        for _, _, s in visible_results:
            day_bounds.setdefault(s.date, []).append(s.start_time.hour)
        for dt, hours in sorted(day_bounds.items()):
            lo = min(hours)
            hi = max(hours)
            for h in range(lo, hi + 1):
                for m in (0, 30):
                    t = time(h, m)
                    if time_filter is not None and not (time_filter[0] <= t <= time_filter[1]):
                        continue
                    yield (dt, h, m)

    def _has_slot(dt: date, hour: int, minute: int, fid: Optional[str] = None) -> bool:
        for f_id, _, s in visible_results:
            if fid is not None and f_id != fid:
                continue
            if s.date == dt and s.start_time.hour == hour and s.start_time.minute == minute:
                return True
        return False

    fac_ids: List[str] = []
    seen_fid: set = set()
    for fid, _, _ in visible_results:
        if fid not in seen_fid:
            seen_fid.add(fid)
            fac_ids.append(fid)

    rows: List[List[str]] = []

    if mode == "condensed":
        columns = ["Time", "Available"]
        prev_date: Optional[date] = None
        for dt, hour, minute in _slot_rows():
            if prev_date is None:
                rows.append([f"── {dt.month}/{dt.day} ──", ""])
            elif dt != prev_date:
                rows.append(["───", f"── {dt.month}/{dt.day} ──"])
            prev_date = dt
            found = _has_slot(dt, hour, minute)
            t_label = f"{hour:02d}:{minute:02d}"
            cell = "[green]█[/green]" if found else "[dim]·[/dim]"
            rows.append([t_label, cell])
        return columns, rows

    columns = ["Time"] + [facility_names.get(fid, fid[:12]) for fid in fac_ids]
    prev_date: Optional[date] = None
    for dt, hour, minute in _slot_rows():
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
            row.append("[green]█[/green]" if found else "[dim]·[/dim]")
        rows.append(row)

    return columns, rows
