import asyncio
import logging
import sys
import tempfile
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from textual.logging import TextualHandler

_textual_handler = TextualHandler(stderr=False, stdout=False)
_textual_handler.setLevel(logging.DEBUG)
_textual_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger("nextrec").setLevel(logging.DEBUG)
logging.getLogger("nextrec").propagate = False
logging.getLogger("nextrec.browser").setLevel(logging.INFO)
logging.getLogger("nextrec").addHandler(_textual_handler)


class DumpOnExitHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def dump(self, stream=sys.stderr) -> None:
        fmt = self.formatter or logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        for record in self.records:
            stream.write(fmt.format(record) + "\n")


_dump_handler = DumpOnExitHandler()
_dump_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
logging.getLogger("nextrec").addHandler(_dump_handler)


def dump_logs() -> None:
    _dump_handler.dump()


from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import MouseDown, MouseUp
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from nextrec.browser import BrowserSession, SessionState
from nextrec.tui.timeline import build_timeline_rows
from nextrec.cart import CartManager
from nextrec.models import Constraint, FacilityConfig, TimeSlot
from nextrec.scrapers.perfectmind import (
    FACILITY_DETAIL_URL,
    FACILITY_LIST_URL,
    PerfectMindScraper,
    ScrapeError,
)
from nextrec.search import search_and_fetch

logger = logging.getLogger(__name__)

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


@dataclass
class TimelineFilter:
    time_ranges: set[tuple[time, time]] = field(default_factory=set)
    facility_time_pairs: set[tuple[str, time]] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.time_ranges and not self.facility_time_pairs

    def matches(self, facility_id: str, slot_time: time) -> bool:
        if self.is_empty():
            return True
        if (facility_id, slot_time) in self.facility_time_pairs:
            return True
        for lo, hi in self.time_ranges:
            if lo <= slot_time <= hi:
                return True
        return False


class CheckoutScreen(ModalScreen):
    def __init__(self, checkout_session: BrowserSession, **kwargs):
        super().__init__(**kwargs)
        self._checkout_session = checkout_session

    def compose(self) -> ComposeResult:
        with Vertical(id="checkout-box"):
            yield Label("Checkout", id="checkout-title")
            yield Static(
                "Items added to cart. A browser has opened for checkout.\n"
                "Complete your booking in the browser, then click Done.",
                id="checkout-msg",
            )
            yield Button("Done", id="done-btn", variant="primary")

    @on(Button.Pressed, "#done-btn")
    def done(self):
        asyncio.ensure_future(self._checkout_session.stop())
        self.dismiss(True)


class ResultItem(Static):
    def __init__(self, slot_info: SlotInfo, index: int, **kwargs):
        super().__init__(**kwargs)
        self.slot_info = slot_info
        self.index = index
        self.checked = False


class NextRecApp(App):
    TITLE = "nextrec — Facility Booking"
    CSS = """
    Screen {
        layout: vertical;
    }

    #constraint-form {
        height: auto;
        min-height: 8;
        padding: 0 1;
        border: solid $primary;
        background: $surface;
    }

    .constraint-row {
        height: 3;
    }

    .constraint-row > Label {
        width: 12;
        text-style: bold;
        padding: 0 1;
    }

    .constraint-row > Input {
        width: 1fr;
        margin: 0 1;
    }

    .constraint-row > Static {
        width: auto;
        padding: 0 1;
    }

    #kw-row Input {
        width: 1fr;
    }

    #search-row {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    #main-area {
        height: 1fr;
    }

    #timeline-panel {
        width: 2fr;
        border: solid $secondary;
        padding: 0 1;
    }

    #timeline-table {
        height: 1fr;
    }

    #results-panel {
        width: 1fr;
        border: solid $secondary;
        padding: 0 1;
    }

    #timeline-mode-btn {
        width: 20;
        margin: 0;
    }

    .panel-header {
        text-style: bold;
        color: $accent;
    }

    #status-bar {
        height: 1;
        background: $surface;
        color: $text-muted;
    }

    Button {
        margin: 0 1;
    }

    CheckoutScreen {
        align: center middle;
    }

    CheckoutScreen #checkout-box {
        width: 50;
        height: 12;
        border: solid $primary;
        padding: 1;
    }

    CheckoutScreen #checkout-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    CheckoutScreen #checkout-msg {
        text-align: center;
        margin-bottom: 1;
    }

    CheckoutScreen Button {
        width: 16;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("f5", "search", "Search"),
        Binding("f2", "book_selected", "Book"),
        Binding("t", "toggle_timeline", "Toggle Timeline"),
        Binding("escape", "clear_time_filter", "Clear filter"),
    ]

    def __init__(self, chrome_exe: str, auth_path: str, initial_constraints: Optional[dict] = None):
        super().__init__()
        self.chrome_exe = chrome_exe
        self.auth_path = auth_path
        self._initial = initial_constraints or {}
        self._session: Optional[BrowserSession] = None
        self._scraper: Optional[PerfectMindScraper] = None
        self._search_results: List[SlotInfo] = []
        self._selected_indices: set[int] = set()
        self._timeline_filter = TimelineFilter()
        self._facility_names: Dict[str, str] = {}
        self._facility_col_map: Dict[str, int] = {}
        self._timeline_mode: str = "condensed"
        self._drag_start_coord = None

    def action_toggle_timeline(self):
        self._timeline_mode = "condensed" if self._timeline_mode == "full" else "full"
        self._build_timeline()
        self._adjust_panel_widths()
        lbl = self.query_one("#timeline-mode-btn", Button)
        lbl.label = f"Mode: {self._timeline_mode.title()}"
        self._set_status(f"Timeline: {self._timeline_mode} view")

    def action_clear_time_filter(self):
        if not self._timeline_filter.is_empty():
            self._timeline_filter = TimelineFilter()
            self._build_timeline()
            self._build_results_list()
            self._set_status("Timeline filter cleared")
            self.notify("Timeline filter cleared", severity="information", timeout=2)

    def _adjust_panel_widths(self):
        tl = self.query_one("#timeline-panel")
        rl = self.query_one("#results-panel")
        if self._timeline_mode == "condensed":
            tl.styles.width = "1fr"
            rl.styles.width = "2fr"
        else:
            tl.styles.width = "2fr"
            rl.styles.width = "1fr"

    async def _start_session(self):
        if self._session is None:
            self._session = BrowserSession(chrome_path=self.chrome_exe, headless=True)
            await self._session.start()
            await self._session.manager.load_storage_state(self.auth_path)
        return self._session

    async def _close_session(self):
        if self._session is not None:
            try:
                await self._session.stop()
            except Exception:
                pass
            self._session = None
            self._scraper = None

    def _get_scraper(self):
        if self._scraper is None:
            self._scraper = PerfectMindScraper(self._session)
        return self._scraper

    def _iv(self, key: str, default: str = "") -> str:
        v = self._initial.get(key)
        if v is None:
            return default
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        return str(v)

    def compose(self) -> ComposeResult:
        sd = self._initial.get("date") or self._iv("start_date")
        ed = self._initial.get("date") or self._iv("end_date")

        yield Header(show_clock=True)
        with Vertical(id="constraint-form"):
            with Horizontal(classes="constraint-row", id="kw-row"):
                yield Label("Keywords")
                yield Input(placeholder="Separate searches with ;", id="kw", value=self._iv("keywords"))
            with Horizontal(classes="constraint-row"):
                yield Label("Dates")
                yield Input(placeholder="Start (M/D)", id="start-date", value=sd)
                yield Static(" to ")
                yield Input(placeholder="End (M/D)", id="end-date", value=ed)
            with Horizontal(classes="constraint-row"):
                yield Label("Times")
                yield Input(placeholder="From (HH:MM)", id="start-time", value=self._iv("start_time"))
                yield Static(" to ")
                yield Input(placeholder="To (HH:MM)", id="end-time", value=self._iv("end_time"))
            with Horizontal(classes="constraint-row"):
                yield Label("Duration")
                yield Input(placeholder="Minutes", id="duration", value=self._iv("duration", "60"))
                yield Label("Attendees")
                yield Input(placeholder="Count", id="attendees", value=self._iv("number_of_attendees", "1"))
            with Horizontal(id="search-row"):
                yield Button("Search [F5]", id="search-btn", variant="primary")
                yield Button("Book Selected [F2]", id="book-btn", variant="success")
        with Horizontal(id="main-area"):
            with Vertical(id="timeline-panel"):
                yield Static("Timeline (time × facility)", classes="panel-header")
                yield DataTable(id="timeline-table")
                yield Button("Mode: Condensed", id="timeline-mode-btn", variant="default")
            with Vertical(id="results-panel"):
                yield Static("Results (click to select)", classes="panel-header")
                yield ListView(id="results-list")
        yield Static(id="status-bar")
        yield Footer()

    def on_mount(self):
        table = self.query_one("#timeline-table", DataTable)
        table.cursor_type = "cell"
        table.zebra_stripes = True
        self._adjust_panel_widths()

        if self._initial:
            self._set_status("Constraints loaded. Press F5 to search.")
        else:
            self._set_status(
                "Set constraints and press F5 to search. "
                "Click timeline time cells to filter by time (first click=start, second=end). "
                "Click a result to toggle selection for booking."
            )

    def action_search(self):
        self.query_one("#search-btn", Button).press()

    def action_book_selected(self):
        self.query_one("#book-btn", Button).press()

    def _read_keywords(self) -> list[str]:
        raw = self.query_one("#kw", Input).value.strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(";") if p.strip()]

    def _read_constraints(self) -> Constraint:
        from dateutil import parser as dateparser

        sd = self.query_one("#start-date", Input).value.strip()
        ed = self.query_one("#end-date", Input).value.strip()
        st = self.query_one("#start-time", Input).value.strip()
        et = self.query_one("#end-time", Input).value.strip()

        start_date = None
        end_date = None
        if sd:
            try:
                start_date = dateparser.parse(sd, default=datetime.today()).date()
            except Exception:
                pass
        if ed:
            try:
                end_date = dateparser.parse(ed, default=datetime.today()).date()
            except Exception:
                pass

        time_start = None
        time_end = None
        if st:
            try:
                parts = st.split(":")
                time_start = time(int(parts[0]), int(parts[1]))
            except Exception:
                pass
        if et:
            try:
                parts = et.split(":")
                time_end = time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        return Constraint(
            start_date=start_date,
            end_date=end_date,
            time_window_start=time_start,
            time_window_end=time_end,
        )

    def _read_num(self, input_id: str, default: int) -> int:
        val = self.query_one(f"#{input_id}", Input).value.strip()
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    @on(Button.Pressed, "#search-btn")
    def handle_search(self):
        self._set_status("Searching...")
        self._run_search()

    @work(thread=False, exclusive=True, exit_on_error=False)
    async def _run_search(self):
        try:
            constraint = self._read_constraints()
            duration_min = self._read_num("duration", 60)
            kw_list = self._read_keywords()

            if kw_list:
                logger.debug("Searching with keyword groups: %s", kw_list)
            logger.debug("Constraint: start=%s end=%s time=%s-%s",
                         constraint.start_date, constraint.end_date,
                         constraint.time_window_start, constraint.time_window_end)

            session = await self._start_session()

            if kw_list:
                fac_names, results = await search_and_fetch(
                    session, kw_list, constraint, duration_min,
                    days_count=365 if not constraint.end_date else 7,
                    end_date=constraint.end_date,
                    time_window_start=constraint.time_window_start,
                    time_window_end=constraint.time_window_end,
                )
            else:
                scraper = self._get_scraper()
                facilities = await scraper.search(constraint)
                results: List[SlotInfo] = []
                fac_names: Dict[str, str] = {}
                for f in facilities:
                    fac_names[f.id] = f.name
                    try:
                        config_obj = await scraper.fetch_config(f.id)
                        slot_date = constraint.start_date or date.today()
                        slots = await scraper.fetch_slots(
                            f.id, slot_date, config_obj,
                            days_count=365 if not constraint.end_date else 7,
                            duration_minutes=duration_min,
                            end_date=constraint.end_date,
                            time_window_start=constraint.time_window_start,
                            time_window_end=constraint.time_window_end,
                        )
                    except ScrapeError:
                        continue
                    for s in slots:
                        if not s.is_disabled:
                            results.append((f.id, config_obj, s))
                results.sort(key=lambda x: (x[2].date, x[2].start_time))

            self._on_search_done(results, fac_names)
        except Exception as e:
            self._set_status(f"Search failed: {e}")

    @property
    def _visible_results(self) -> List[SlotInfo]:
        if self._timeline_filter.is_empty():
            return self._search_results
        return [r for r in self._search_results
                if self._timeline_filter.matches(r[0], r[2].start_time)]

    def _on_search_done(self, results: List[SlotInfo], fac_names: Dict[str, str]):
        self._search_results = results
        self._selected_indices = set()
        self._facility_names = fac_names
        self._timeline_filter = TimelineFilter()
        self._build_timeline()
        self._build_results_list()
        self._set_status(f"Found {len(results)} slot(s) across {len(fac_names)} facility(ies)")
        if not results:
            self._set_status("No available slots found. Try different constraints.")

    def _build_timeline(self):
        table = self.query_one("#timeline-table", DataTable)
        table.clear(columns=True)

        if not self._visible_results:
            return

        cols, rows, self._facility_col_map = build_timeline_rows(
            visible_results=self._visible_results,
            facility_names=self._facility_names,
            mode=self._timeline_mode,
            selected_time_ranges=self._timeline_filter.time_ranges,
            selected_facility_times=self._timeline_filter.facility_time_pairs,
        )
        table.add_columns(*cols)
        for row in rows:
            table.add_row(*row)

    def _build_results_list(self):
        lv = self.query_one("#results-list", ListView)
        lv.clear()

        for search_idx, item in enumerate(self._search_results):
            fid, cfg, slot = item
            if not self._timeline_filter.matches(fid, slot.start_time):
                continue
            name = self._facility_names.get(fid, fid[:8])
            price_str = ""
            if cfg.duration_prices:
                dp = cfg.duration_prices[0]
                price_str = f" ${dp.resident_price:.0f}R/${dp.non_resident_price:.0f}NR"

            checked = search_idx in self._selected_indices
            marker = "[bold yellow]\[X][/bold yellow]" if checked else "\[ ]"
            label = f"{marker} {slot.date} {slot.start_time}-{slot.end_time} ({slot.duration_minutes}min) {name}{price_str}"

            item = ListItem(Static(label))
            item._result_search_idx = search_idx
            lv.append(item)

        if self._selected_indices:
            self._set_status(f"{len(self._selected_indices)} slot(s) selected. Press F2 or Book to proceed.")

    def _update_result_item(self, item: ListItem):
        search_idx = getattr(item, "_result_search_idx", None)
        if search_idx is None:
            return
        for fid, cfg, slot_i in self._search_results:
            pass
        slot = self._search_results[search_idx][2]
        name = self._facility_names.get(self._search_results[search_idx][0], "...")
        price_str = ""
        cfg = self._search_results[search_idx][1]
        if cfg.duration_prices:
            dp = cfg.duration_prices[0]
            price_str = f" ${dp.resident_price:.0f}R/${dp.non_resident_price:.0f}NR"
        checked = search_idx in self._selected_indices
        marker = "[bold yellow]\[X][/bold yellow]" if checked else "\[ ]"
        label = f"{marker} {slot.date} {slot.start_time}-{slot.end_time} ({slot.duration_minutes}min) {name}{price_str}"
        static_w = item.query(Static).first()
        if static_w:
            static_w.update(label)

    @on(ListView.Selected)
    def handle_result_click(self, event: ListView.Selected):
        search_idx = getattr(event.item, "_result_search_idx", None)
        if search_idx is None:
            return

        if search_idx in self._selected_indices:
            self._selected_indices.discard(search_idx)
        else:
            self._selected_indices.add(search_idx)

        self._update_result_item(event.item)

        if self._selected_indices:
            self._set_status(f"{len(self._selected_indices)} slot(s) selected. Press F2 or Book to proceed.")
        else:
            self._set_status("No slots selected. Click results to toggle selection.")

    def _toggle_time_filter(self, t: time) -> None:
        key = (t, t)
        if key in self._timeline_filter.time_ranges:
            self._timeline_filter.time_ranges.discard(key)
            action = "removed"
        else:
            self._timeline_filter.time_ranges.add(key)
            action = "added"
        self._build_timeline()
        self._build_results_list()
        self._set_status(f"Time filter {action}: {t}")
        self.notify(f"Time filter {action}: {t}", severity="information", timeout=2)

    def _extract_time_from_row(self, row) -> Optional[time]:
        time_str = row[0]
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
            return None

    def _col_to_facility(self, col_key) -> Optional[str]:
        if col_key and hasattr(col_key, "value"):
            col_idx = col_key.value
            for fid, idx in self._facility_col_map.items():
                if idx + 1 == col_idx:
                    return fid
        return None

    @on(DataTable.CellHighlighted)
    def handle_timeline_highlight(self, event: DataTable.CellHighlighted):
        try:
            row_key, col_key = event.coordinate
            table = self.query_one("#timeline-table", DataTable)
            try:
                row = table.get_row(row_key)
            except Exception:
                return
            if not row:
                return
            t = self._extract_time_from_row(row)
            if t is None:
                return
            if self._timeline_mode == "full":
                fid = self._col_to_facility(col_key)
                if fid:
                    name = self._facility_names.get(fid, fid[:12])
                    self._set_status(f"Preview: {name} at {t} (Enter=toggle filter)")
                    return
            full = not self._timeline_filter.is_empty()
            if full:
                n_times = len(self._timeline_filter.time_ranges)
                n_pairs = len(self._timeline_filter.facility_time_pairs)
                self._set_status(f"Filter: {n_times + n_pairs} selection(s) (Enter=toggle, Esc=clear)")
            else:
                self._set_status(f"Preview: {t} (Enter=toggle filter)")
        except Exception:
            pass

    @on(DataTable.CellSelected)
    def handle_timeline_selected(self, event: DataTable.CellSelected):
        try:
            row_key, col_key = event.coordinate
            table = self.query_one("#timeline-table", DataTable)
            try:
                row = table.get_row(row_key)
            except Exception:
                return
            if not row:
                return
            t = self._extract_time_from_row(row)
            if t is None:
                return

            if self._timeline_mode == "full" and col_key is not None:
                fid = self._col_to_facility(col_key)
                if fid:
                    pair = (fid, t)
                    if pair in self._timeline_filter.facility_time_pairs:
                        self._timeline_filter.facility_time_pairs.discard(pair)
                    else:
                        self._timeline_filter.facility_time_pairs.add(pair)
                    self._build_timeline()
                    self._build_results_list()
                    n = len(self._timeline_filter.facility_time_pairs)
                    self._set_status(f"Facility filter: {n} selection(s) (Enter=toggle, Esc=clear)")
                    return

            self._toggle_time_filter(t)
        except Exception as e:
            logger.exception("Timeline select error")
            self._set_status(f"Timeline error: {e}")

    @on(MouseDown, "#timeline-table")
    def handle_timeline_mouse_down(self, event):
        try:
            table = self.query_one("#timeline-table", DataTable)
            row_key, col_key = table.coordinate_to_cell_key(event)
            if row_key is not None and col_key is not None:
                self._drag_start_coord = (row_key, col_key)
        except Exception:
            self._drag_start_coord = None

    @on(MouseUp, "#timeline-table")
    def handle_timeline_mouse_up(self, event):
        if self._drag_start_coord is None:
            return
        try:
            table = self.query_one("#timeline-table", DataTable)
            row_key, col_key = table.coordinate_to_cell_key(event)
            if row_key is None or col_key is None:
                self._drag_start_coord = None
                return
            start_row_key, start_col_key = self._drag_start_coord
            self._drag_start_coord = None
            if (start_row_key, start_col_key) == (row_key, col_key):
                self._toggle_single_cell(table, row_key, col_key)
                return

            self._toggle_cell_range(table, start_row_key, start_col_key, row_key, col_key)
        except Exception:
            self._drag_start_coord = None

    def _toggle_single_cell(self, table, row_key, col_key):
        row = table.get_row(row_key)
        if not row:
            return
        t = self._extract_time_from_row(row)
        if t is None:
            return
        if self._timeline_mode == "full" and col_key is not None:
            fid = self._col_to_facility(col_key)
            if fid:
                pair = (fid, t)
                if pair in self._timeline_filter.facility_time_pairs:
                    self._timeline_filter.facility_time_pairs.discard(pair)
                else:
                    self._timeline_filter.facility_time_pairs.add(pair)
                self._build_timeline()
                self._build_results_list()
                n = len(self._timeline_filter.facility_time_pairs)
                self._set_status(f"Facility filter: {n} selection(s) (click/Enter=toggle, Esc=clear)")
                return

        self._toggle_time_filter(t)

    def _toggle_cell_range(self, table, start_row, start_col, end_row, end_col):
        row_keys = list(table._data)
        start_idx = row_keys.index(start_row) if start_row in row_keys else 0
        end_idx = row_keys.index(end_row) if end_row in row_keys else len(row_keys) - 1
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        col_start = start_col.value
        col_end = end_col.value
        if col_start > col_end:
            col_start, col_end = col_end, col_start

        toggled = False
        for idx in range(start_idx, end_idx + 1):
            rk = row_keys[idx]
            row = table.get_row(rk)
            if not row:
                continue
            t = self._extract_time_from_row(row)
            if t is None:
                continue
            if self._timeline_mode == "full":
                for ci in range(max(col_start, 1), min(col_end + 1, len(row))):
                    fid = self._col_to_facility_by_index(ci)
                    if fid:
                        pair = (fid, t)
                        if pair not in self._timeline_filter.facility_time_pairs:
                            self._timeline_filter.facility_time_pairs.add(pair)
                            toggled = True
            else:
                key = (t, t)
                if key not in self._timeline_filter.time_ranges:
                    self._timeline_filter.time_ranges.add(key)
                    toggled = True

        if toggled:
            self._build_timeline()
            self._build_results_list()
            n = len(self._timeline_filter.time_ranges) + len(self._timeline_filter.facility_time_pairs)
            self._set_status(f"Range selected: {n} time(s) (Enter=toggle, Esc=clear)")

    def _col_to_facility_by_index(self, col_idx: int) -> Optional[str]:
        for fid, idx in self._facility_col_map.items():
            if idx + 1 == col_idx:
                return fid
        return None

    def _set_status(self, msg: str):
        try:
            self.query_one("#status-bar", Static).update(msg)
        except Exception:
            pass

    @on(Button.Pressed, "#timeline-mode-btn")
    def handle_toggle_timeline(self):
        self.action_toggle_timeline()

    @on(Button.Pressed, "#book-btn")
    def handle_book(self):
        logger.debug("Book pressed. selected_indices=%s", self._selected_indices)
        if not self._selected_indices:
            self._set_status("No slots selected. Click results to toggle selection.")
            self.notify("No slots selected", severity="warning", timeout=3)
            return
        self._set_status("Booking...")
        self.notify("Booking started", severity="information", timeout=5)
        logger.debug("Calling _run_booking...")
        self._run_booking()

    @work(thread=False, exclusive=True, exit_on_error=False)
    async def _run_booking(self):
        logger.debug("_run_booking coroutine started")
        try:
            selected = [
                self._search_results[i] for i in sorted(self._selected_indices)
                if i < len(self._search_results)
            ]
            if not selected:
                logger.debug("selected list empty")
                return

            logger.debug("Booking %d slot(s): %s", len(selected),
                         [(s.date, s.start_time, fid[:8]) for fid, _, s in selected])

            booked: List[str] = []
            failed: List[str] = []

            from nextrec.cart import CartError

            booking_session = BrowserSession(chrome_path=self.chrome_exe, headless=True)
            await booking_session.start()
            await booking_session.manager.load_storage_state(self.auth_path)
            cart = CartManager(booking_session)

            for fid, cfg, slot in selected:
                name = self._facility_names.get(fid, fid[:8])
                num_att = self._read_num("attendees", 1)
                try:
                    result = await cart.add_to_cart(fid, cfg, slot, number_of_attendees=num_att)
                    booked.append(f"{slot.date} {slot.start_time} @ {name}")
                except (CartError, ScrapeError) as e:
                    failed.append(f"{slot.date} {slot.start_time} @ {name}: {e}")

            await booking_session.manager.save_storage_state(self.auth_path)
            checkout_state = tempfile.mktemp(suffix=".json")
            await booking_session.manager.save_storage_state(checkout_state)
            await booking_session.stop()

            msg = f"Booked {len(booked)}/{len(selected)}"
            if booked:
                short = ", ".join(booked[:2])
                if len(booked) > 2:
                    short += f" ... +{len(booked)-2}"
                msg += f" ({short})"
            if failed:
                msg += f"; {len(failed)} failed"
            self._set_status(msg)

            if not booked:
                self._set_status("No slots were booked successfully.")
                return

            base_url = "https://cityofoakland.perfectmind.com/SocialSite/BookMe4EventParticipants/FacilityBooking"
            by_facility = defaultdict(list)
            for fid, cfg, slot in selected:
                by_facility[fid].append((cfg, slot))

            checkout_session = BrowserSession(
                chrome_path=self.chrome_exe, headless=False,
                state=SessionState(storage_state_path=checkout_state),
            )
            await checkout_session.start()

            num_att = self._read_num("attendees", 1)
            for fid, items in by_facility.items():
                for cfg, slot in items:
                    dur_id = next(
                        (dp.id for dp in cfg.duration_prices if dp.minutes == slot.duration_minutes),
                        cfg.duration_prices[0].id if cfg.duration_prices else "",
                    )
                    back_url = urllib.parse.quote(f"{FACILITY_DETAIL_URL}?facilityId={fid}", safe="")
                    checkout_url = (
                        f"{base_url}?facilityId={fid}"
                        f"&calendarId={cfg.calendar_id}"
                        f"&serviceId={cfg.service_id}"
                        f"&duration={slot.duration_minutes}"
                        f"&durationId={dur_id}"
                        f"&startDateTimeTicks={slot.ticks}"
                        f"&numberOfAttendees={num_att}"
                        f"&numberOfNights=0"
                        f"&feeType=0"
                        f"&landingPageBackUrl={back_url}"
                    )
                    page = await checkout_session.manager.new_page()
                    await page.goto(checkout_url, wait_until="networkidle")

            self._set_status(
                f"Browser opened with {len(selected)} checkout tab(s). Complete booking in the browser."
            )

            wait_event = asyncio.Event()
            self._show_checkout_screen(checkout_session, wait_event)
            await wait_event.wait()

            await self._close_session()
        except Exception as e:
            logger.exception("Booking failed")
            self._set_status(f"Booking error: {e}")

    def _show_checkout_screen(self, checkout_session: BrowserSession, wait_event: asyncio.Event):
        def on_done(result):
            wait_event.set()
        self.push_screen(CheckoutScreen(checkout_session), on_done)
