from datetime import date

from textual.widgets import Button, Input

from nextrec.tui.app import NextRecApp, resolve_date_range


class TestResolveDateRange:
    def test_single_day_uses_start_as_end(self):
        start = date(2026, 12, 3)
        assert resolve_date_range(start, None, range_mode=False) == (start, start)

    def test_single_day_ignores_end_date(self):
        start = date(2026, 12, 3)
        assert resolve_date_range(start, date(2026, 12, 9), range_mode=False) == (start, start)

    def test_single_day_without_start_has_no_dates(self):
        assert resolve_date_range(None, None, range_mode=False) == (None, None)

    def test_range_keeps_both_dates(self):
        start, end = date(2026, 12, 3), date(2026, 12, 9)
        assert resolve_date_range(start, end, range_mode=True) == (start, end)

    def test_range_without_end_is_open_ended(self):
        start = date(2026, 12, 3)
        assert resolve_date_range(start, None, range_mode=True) == (start, None)


def _app(initial=None):
    return NextRecApp(chrome_exe="chrome", auth_path="auth.json", initial_constraints=initial)


class TestDateModeToggle:
    async def test_single_day_is_default(self):
        app = _app()
        async with app.run_test():
            assert app.query_one("#end-date", Input).disabled
            assert str(app.query_one("#date-mode-btn", Button).label) == "Single day"

    async def test_single_day_searches_start_date_only(self):
        app = _app({"start_date": "2026-12-03"})
        async with app.run_test():
            c = app._read_constraints()
            assert (c.start_date, c.end_date) == (date(2026, 12, 3), date(2026, 12, 3))

    async def test_toggle_enables_end_date(self):
        app = _app({"start_date": "2026-12-03"})
        async with app.run_test() as pilot:
            await pilot.click("#date-mode-btn")
            end_input = app.query_one("#end-date", Input)
            assert not end_input.disabled
            assert end_input.value == "2026-12-03"
            assert str(app.query_one("#date-mode-btn", Button).label) == "Date range"
            end_input.value = "2026-12-09"
            c = app._read_constraints()
            assert (c.start_date, c.end_date) == (date(2026, 12, 3), date(2026, 12, 9))

    async def test_toggle_back_to_single_day(self):
        app = _app({"start_date": "2026-12-03", "end_date": "2026-12-09"})
        async with app.run_test() as pilot:
            assert not app.query_one("#end-date", Input).disabled
            await pilot.click("#date-mode-btn")
            assert app.query_one("#end-date", Input).disabled
            c = app._read_constraints()
            assert (c.start_date, c.end_date) == (date(2026, 12, 3), date(2026, 12, 3))

    async def test_single_date_config_opens_in_single_day_mode(self):
        app = _app({"date": "2026-12-03"})
        async with app.run_test():
            assert app.query_one("#end-date", Input).disabled
