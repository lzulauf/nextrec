import logging
import tempfile
import threading
import urllib.parse
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from textual.logging import TextualHandler

_textual_handler = TextualHandler(stderr=True, stdout=False)
_textual_handler.setLevel(logging.DEBUG)
_textual_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger("nextrec").addHandler(_textual_handler)

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
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
    PerfectMindScraper,
    ScrapeError,
)
from nextrec.search import search_multi

logger = logging.getLogger(__name__)

SlotInfo = Tuple[str, FacilityConfig, TimeSlot]


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
        self._checkout_session.stop()
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
        self._time_filter: Optional[Tuple[time, time]] = None
        self._pending_filter_time: Optional[time] = None
        self._facility_names: Dict[str, str] = {}
        self._timeline_mode: str = "condensed"

    def action_toggle_timeline(self):
        self._timeline_mode = "condensed" if self._timeline_mode == "full" else "full"
        self._build_timeline()
        self._adjust_panel_widths()
        lbl = self.query_one("#timeline-mode-btn", Button)
        lbl.label = f"Mode: {self._timeline_mode.title()}"
        self._set_status(f"Timeline: {self._timeline_mode} view")

    def action_clear_time_filter(self):
        if self._time_filter:
            self._time_filter = None
            self._pending_filter_time = None
            self._build_timeline()
            self._build_results_list()
            self._set_status("Time filter cleared")
            self.notify("Time filter cleared", severity="information", timeout=2)

    def _adjust_panel_widths(self):
        tl = self.query_one("#timeline-panel")
        rl = self.query_one("#results-panel")
        if self._timeline_mode == "condensed":
            tl.styles.width = "1fr"
            rl.styles.width = "2fr"
        else:
            tl.styles.width = "2fr"
            rl.styles.width = "1fr"

    def _start_session(self):
        if self._session is None:
            self._session = BrowserSession(chrome_path=self.chrome_exe, headless=True)
            self._session.start()
            self._session.manager.load_storage_state(self.auth_path)
        return self._session

    def _close_session(self):
        if self._session is not None:
            try:
                self._session.stop()
            except Exception:
                pass
            self._session = None
            self._scraper = None

    def _get_scraper(self):
        if self._scraper is None:
            self._scraper = PerfectMindScraper(self._start_session())
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

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _run_search(self):
        try:
            constraint = self._read_constraints()
            duration_min = self._read_num("duration", 60)
            kw_list = self._read_keywords()

            if kw_list:
                logger.debug("Searching with keyword groups: %s", kw_list)
            logger.debug("Constraint: start=%s end=%s time=%s-%s",
                         constraint.start_date, constraint.end_date,
                         constraint.time_window_start, constraint.time_window_end)

            session = self._start_session()
            scraper = self._get_scraper()
            facilities = (
                search_multi(session, kw_list, constraint) if kw_list
                else scraper.search(constraint)
            )

            results: List[SlotInfo] = []
            fac_names: Dict[str, str] = {}
            for f in facilities:
                fac_names[f.id] = f.name
                try:
                    config_obj = scraper.fetch_config(f.id)
                    slot_date = constraint.start_date or date.today()
                    slots = scraper.fetch_slots(
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
            self.call_from_thread(self._on_search_done, results, fac_names)
        except Exception as e:
            self.call_from_thread(self._set_status, f"Search failed: {e}")

    @property
    def _visible_results(self) -> List[SlotInfo]:
        if not self._time_filter:
            return self._search_results
        lo, hi = self._time_filter
        return [r for r in self._search_results if lo <= r[2].start_time <= hi]

    def _on_search_done(self, results: List[SlotInfo], fac_names: Dict[str, str]):
        self._search_results = results
        self._selected_indices = set()
        self._facility_names = fac_names
        self._time_filter = None
        self._pending_filter_time = None
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

        cols, rows = build_timeline_rows(
            visible_results=self._visible_results,
            facility_names=self._facility_names,
            mode=self._timeline_mode,
            time_filter=self._time_filter,
        )
        table.add_columns(*cols)
        for row in rows:
            table.add_row(*row)

    def _build_results_list(self):
        lv = self.query_one("#results-list", ListView)
        lv.clear()

        for search_idx, item in enumerate(self._search_results):
            fid, cfg, slot = item
            if self._time_filter:
                lo, hi = self._time_filter
                if not (lo <= slot.start_time <= hi):
                    continue
            name = self._facility_names.get(fid, fid[:8])
            price_str = ""
            if cfg.duration_prices:
                dp = cfg.duration_prices[0]
                price_str = f" ${dp.resident_price:.0f}R/${dp.non_resident_price:.0f}NR"

            checked = search_idx in self._selected_indices
            marker = "[x]" if checked else "[ ]"
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
        marker = "[x]" if checked else "[ ]"
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

    def _apply_time_filter(self, t: time) -> None:
        if self._time_filter and self._time_filter[0] == t and self._time_filter[1] == t:
            self._time_filter = None
            self._set_status("Time filter cleared")
            self.notify("Time filter cleared", severity="information", timeout=2)
        elif self._time_filter is None:
            self._time_filter = (t, t)
            self._set_status(f"Filtered to: {t}")
            self.notify(f"Showing results at {t}", severity="information", timeout=2)
        else:
            start, end = self._time_filter
            if t < start:
                self._time_filter = (t, end)
            else:
                self._time_filter = (start, t)
            self._set_status(f"Filtered: {self._time_filter[0]}-{self._time_filter[1]}")
            self.notify(f"Time range: {self._time_filter[0]}-{self._time_filter[1]}", severity="information", timeout=2)
        self._build_timeline()
        self._build_results_list()

    def _extract_time_from_row(self, row) -> Optional[time]:
        time_str = row[0]
        try:
            parts = time_str.split(":")
            return time(int(parts[0]), int(parts[1]))
        except Exception:
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
            self._pending_filter_time = t
            if self._time_filter:
                self._set_status(f"Filter: {self._time_filter[0]}-{self._time_filter[1]} (Enter=apply, Esc=clear)")
            else:
                self._set_status(f"Preview: {t} (Enter=apply filter at this time)")
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
            self._apply_time_filter(t)
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

    @work(thread=True, exclusive=True, exit_on_error=False)
    def _run_booking(self):
        logger.debug("_run_booking thread started")
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
            booking_session.start()
            booking_session.manager.load_storage_state(self.auth_path)
            cart = CartManager(booking_session)

            for fid, cfg, slot in selected:
                name = self._facility_names.get(fid, fid[:8])
                num_att = self._read_num("attendees", 1)
                try:
                    result = cart.add_to_cart(fid, cfg, slot, number_of_attendees=num_att)
                    booked.append(f"{slot.date} {slot.start_time} @ {name}")
                except (CartError, ScrapeError) as e:
                    failed.append(f"{slot.date} {slot.start_time} @ {name}: {e}")

            booking_session.manager.save_storage_state(self.auth_path)
            checkout_state = tempfile.mktemp(suffix=".json")
            booking_session.manager.save_storage_state(checkout_state)
            booking_session.stop()

            msg = f"Booked {len(booked)}/{len(selected)}"
            if booked:
                short = ", ".join(booked[:2])
                if len(booked) > 2:
                    short += f" ... +{len(booked)-2}"
                msg += f" ({short})"
            if failed:
                msg += f"; {len(failed)} failed"
            self.call_from_thread(self._set_status, msg)

            if not booked:
                self.call_from_thread(self._set_status, "No slots were booked successfully.")
                return

            fid, cfg, slot = selected[0]
            dur_id = next(
                (dp.id for dp in cfg.duration_prices if dp.minutes == slot.duration_minutes),
                cfg.duration_prices[0].id if cfg.duration_prices else "",
            )
            back_url = urllib.parse.quote(f"{FACILITY_DETAIL_URL}?facilityId={fid}", safe="")
            base_url = "https://cityofoakland.perfectmind.com/SocialSite/BookMe4EventParticipants/FacilityBooking"
            checkout_url = (
                f"{base_url}?facilityId={fid}"
                f"&calendarId={cfg.calendar_id}"
                f"&serviceId={cfg.service_id}"
                f"&duration={slot.duration_minutes}"
                f"&durationId={dur_id}"
                f"&startDateTimeTicks={slot.ticks}"
                f"&numberOfAttendees={self._read_num('attendees', 1)}"
                f"&numberOfNights=0"
                f"&feeType=0"
                f"&landingPageBackUrl={back_url}"
            )

            checkout_session = BrowserSession(
                chrome_path=self.chrome_exe, headless=False,
                state=SessionState(storage_state_path=checkout_state),
            )
            checkout_session.start()
            checkout_session.manager.new_page().goto(checkout_url, wait_until="networkidle")

            self.call_from_thread(
                self._set_status,
                "Browser opened for checkout. Complete booking in the browser window."
            )

            wait_event = threading.Event()
            self.call_from_thread(self._show_checkout_screen, checkout_session, wait_event)
            wait_event.wait()

            self._close_session()
        except Exception as e:
            logger.exception("Booking failed")
            self.call_from_thread(self._set_status, f"Booking error: {e}")

    def _show_checkout_screen(self, checkout_session: BrowserSession, wait_event: threading.Event):
        def on_done(result):
            wait_event.set()
        self.push_screen(CheckoutScreen(checkout_session), on_done)
