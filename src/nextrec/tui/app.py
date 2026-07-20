import asyncio
import logging
import sys
import tempfile
import time as _time_module
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
logging.getLogger("nextrec").setLevel(logging.INFO)
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
from nextrec.tui.timeline import build_timeline_rows, TimelineCell
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
    time_pairs: set[tuple[date, time]] = field(default_factory=set)
    facility_pairs: set[tuple[str, date, time]] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.time_pairs and not self.facility_pairs

    def matches(self, facility_id: str, slot_date: date, slot_time: time) -> bool:
        if self.is_empty():
            return True
        if (facility_id, slot_date, slot_time) in self.facility_pairs:
            return True
        if (slot_date, slot_time) in self.time_pairs:
            return True
        return False

    def __repr__(self) -> str:
        parts = []
        if self.time_pairs:
            parts.append(f"times={self.time_pairs}")
        if self.facility_pairs:
            parts.append(f"pairs={self.facility_pairs}")
        return f"TimelineFilter({', '.join(parts)})" if parts else "TimelineFilter(empty)"


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


class SelectOnClickDataTable(DataTable):
    """DataTable that fires CellSelected on every click, not just double-click."""

    async def _on_click(self, event):
        await super()._on_click(event)
        if self.show_cursor and self.cursor_type != "none":
            self._post_selected_message()


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

    .constraint-half {
        width: 1fr;
    }

    .constraint-half > Label {
        width: auto;
        text-style: bold;
        padding: 0 1;
    }

    .constraint-half > Input {
        width: 1fr;
        margin: 0 1;
    }

    .constraint-half > Static {
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
        self._last_toggled = None
        self._search_start = 0.0

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
                with Horizontal(classes="constraint-half"):
                    yield Label("Dates")
                    yield Input(placeholder="Start (M/D)", id="start-date", value=sd)
                    yield Static(" to ")
                    yield Input(placeholder="End (M/D)", id="end-date", value=ed)
                with Horizontal(classes="constraint-half"):
                    yield Label("Times")
                    yield Input(placeholder="From (HH:MM)", id="start-time", value=self._iv("start_time"))
                    yield Static(" to ")
                    yield Input(placeholder="To (HH:MM)", id="end-time", value=self._iv("end_time"))
            with Horizontal(classes="constraint-row"):
                with Horizontal(classes="constraint-half"):
                    yield Label("Duration")
                    yield Input(placeholder="Minutes", id="duration", value=self._iv("duration", "60"))
                with Horizontal(classes="constraint-half"):
                    yield Label("Attendees")
                    yield Input(placeholder="Count", id="attendees", value=self._iv("number_of_attendees", "1"))
            with Horizontal(id="search-row"):
                yield Button("Search [F5]", id="search-btn", variant="primary")
                yield Button("Book Selected [F2]", id="book-btn", variant="success")
        with Horizontal(id="main-area"):
            with Vertical(id="timeline-panel"):
                yield Static("Timeline (time × facility)", classes="panel-header")
                yield SelectOnClickDataTable(id="timeline-table")
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
        self._search_start = _time_module.monotonic()
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
                        slot_date = constraint.start_date or date.today()
                        config_obj, slots = await scraper.fetch_config_and_slots(
                            f.id, slot_date,
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
                if self._timeline_filter.matches(r[0], r[2].date, r[2].start_time)]

    def _on_search_done(self, results: List[SlotInfo], fac_names: Dict[str, str]):
        self._search_results = results
        self._selected_indices = set()
        self._facility_names = fac_names
        self._timeline_filter = TimelineFilter()
        logger.debug("_on_search_done: results=%d filter reset", len(results))
        self._build_timeline()
        self._build_results_list()
        self._set_status(f"Found {len(results)} slot(s) across {len(fac_names)} facility(ies)")
        if not results:
            self._set_status("No available slots found. Try different constraints.")
        logger.info("Search complete: %d slots, %d facilities, rendered in %.1fs",
                     len(results), len(fac_names),
                     _time_module.monotonic() - getattr(self, '_search_start', _time_module.monotonic()))

    def _build_timeline(self):
        table = self.query_one("#timeline-table", DataTable)
        table.clear(columns=True)

        if not self._search_results:
            logger.debug("_build_timeline: no results at all")
            return

        cols, rows, self._facility_col_map = build_timeline_rows(
            visible_results=self._search_results,
            facility_names=self._facility_names,
            mode=self._timeline_mode,
            selected_time_pairs=self._timeline_filter.time_pairs,
            selected_facility_pairs=self._timeline_filter.facility_pairs,
        )
        logger.debug("_build_timeline: cols=%s rows=%d fcm=%s", cols, len(rows), self._facility_col_map)
        table.add_columns(*cols)
        for row in rows:
            table.add_row(*row)

    def _build_results_list(self):
        lv = self.query_one("#results-list", ListView)
        lv.clear()

        filtered_count = 0
        for search_idx, item in enumerate(self._search_results):
            fid, cfg, slot = item
            if not self._timeline_filter.matches(fid, slot.date, slot.start_time):
                filtered_count += 1
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

        logger.debug("_build_results_list: total=%d filtered=%d displayed=%d filter=%s",
                     len(self._search_results), filtered_count,
                     len(self._search_results) - filtered_count,
                     self._timeline_filter)
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

    def _toggle_time_filter(self, d: date, t: time) -> None:
        key = (d, t)
        if key in self._timeline_filter.time_pairs:
            self._timeline_filter.time_pairs.discard(key)
            action = "removed"
        else:
            self._timeline_filter.time_pairs.add(key)
            action = "added"
        logger.debug("_toggle_time_filter: %s %s on %s, pairs=%s",
                     action, t, d, self._timeline_filter.time_pairs)
        self._build_timeline()
        self._build_results_list()
        self._set_status(f"Time filter {action}: {t} on {d}")
        self.notify(f"{'Added' if action == 'added' else 'Removed'} filter: {t} on {d}", severity="information", timeout=2)

    def _extract_cell_meta(self, row) -> Optional['TimelineCell']:
        for cell in row:
            if isinstance(cell, TimelineCell) and cell.time is not None:
                return cell
        return None

    def _col_to_facility(self, col_idx: int) -> Optional[str]:
        for fid, idx in self._facility_col_map.items():
            if idx + 1 == col_idx:
                return fid
        return None

    @on(DataTable.CellHighlighted)
    def handle_timeline_highlight(self, event: DataTable.CellHighlighted):
        try:
            cell_key = event.cell_key
            row_key = cell_key.row_key
            col_coord = event.coordinate
            col_idx = col_coord[1] if col_coord is not None else None
            table = self.query_one("#timeline-table", DataTable)
            try:
                row = table.get_row(row_key)
            except Exception:
                return
            if not row:
                return
            meta = self._extract_cell_meta(row)
            if meta is None or meta.time is None:
                return
            t = meta.time
            d = meta.date

            if self._timeline_mode == "full":
                fid = self._col_to_facility(col_idx) if col_idx is not None else None
                if fid:
                    name = self._facility_names.get(fid, fid[:12])
                    self._set_status(f"Preview: {name} at {t} (Enter=toggle filter)")
                    return
            n_times = len(self._timeline_filter.time_pairs)
            n_pairs = len(self._timeline_filter.facility_pairs)
            total = n_times + n_pairs
            if total:
                self._set_status(f"Filter: {total} selection(s) (Enter=toggle, Esc=clear)")
            else:
                self._set_status(f"Preview: {t} (Enter=toggle filter)")
        except Exception:
            pass

    @on(DataTable.CellSelected)
    def handle_timeline_selected(self, event: DataTable.CellSelected):
        try:
            cell_key = event.cell_key
            row_key = cell_key.row_key
            col_coord = event.coordinate
            col_idx = col_coord[1] if col_coord is not None else None
            now = _time_module.monotonic()
            key = (row_key, col_idx)
            if self._last_toggled and self._last_toggled[0] == key and now - self._last_toggled[1] < 0.1:
                logger.debug("CellSelected: debounced duplicate %s", key)
                return
            self._last_toggled = (key, now)
            logger.debug("CellSelected: row=%s col=%s", row_key, col_idx)
            table = self.query_one("#timeline-table", DataTable)
            try:
                row = table.get_row(row_key)
            except Exception as e:
                logger.debug("CellSelected: get_row failed for %s: %s", row_key, e)
                return
            if not row:
                logger.debug("CellSelected: empty row for %s", row_key)
                return
            meta = self._extract_cell_meta(row)
            if meta is None:
                logger.debug("CellSelected: no cell meta in row")
                return
            d = meta.date
            t = meta.time
            if d is None or t is None:
                return

            if self._timeline_mode == "full" and col_idx is not None:
                fid = self._col_to_facility(col_idx)
                logger.debug("CellSelected: full mode, col=%s fid=%s", col_idx, fid)
                if fid:
                    pair = (fid, d, t)
                    if pair in self._timeline_filter.facility_pairs:
                        self._timeline_filter.facility_pairs.discard(pair)
                    else:
                        self._timeline_filter.facility_pairs.add(pair)
                    self._build_timeline()
                    self._build_results_list()
                    n = len(self._timeline_filter.facility_pairs)
                    name = self._facility_names.get(fid, fid[:12])
                    self._set_status(f"Facility filter: {n} selection(s) (click=toggle, Esc=clear)")
                    self.notify(f"Toggled {name} at {t} on {d}", severity="information", timeout=2)
                    return

            logger.debug("CellSelected: BEFORE toggle mode=%s date=%s time=%s", self._timeline_mode, d, t)
            self._toggle_time_filter(d, t)
        except Exception as e:
            logger.exception("Timeline select error")
            self._set_status(f"Timeline error: {e}")

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
