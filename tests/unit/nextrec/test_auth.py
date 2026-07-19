from unittest.mock import AsyncMock, Mock, call

import pytest

from nextrec.auth import (
    AuthError,
    CaptchaDetectedError,
    LoginFailedError,
    SessionNotStartedError,
    _detect_captcha,
    _extract_csrf,
    capture_login_interactive,
    ensure_logged_in,
    is_logged_in,
    try_auto_login,
)


@pytest.mark.asyncio
class TestIsLoggedIn:
    async def test_returns_false_on_login_page(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn?returnUrl=.../List"
        assert await is_logged_in(page) is False

    async def test_returns_true_when_logout_link_present(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
        page.wait_for_selector = AsyncMock(return_value=Mock())
        assert await is_logged_in(page) is True

    async def test_returns_false_when_csrf_form_present_but_no_logout(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        call_log: dict = {"count": 0}

        async def wait_for_selector(selector, **kw):
            call_log["count"] += 1
            is_logout = any(
                kw in selector.lower()
                for kw in ["logout", "signout", "logoff", "member"]
            )
            if is_logout:
                raise Exception("not found")
            if "ajaxantiforgeryform" in selector.lower():
                return Mock()
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        assert await is_logged_in(page) is False

    async def test_returns_true_when_facility_list_url_matches(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        async def wait_for_selector(*a, **kw):
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        assert await is_logged_in(page) is True


@pytest.mark.asyncio
class TestExtractCsrf:
    async def test_returns_token_when_found(self):
        page = Mock()
        element = Mock()
        element.get_attribute = AsyncMock(return_value="abc123")
        page.wait_for_selector = AsyncMock(return_value=element)

        result = await _extract_csrf(page)
        assert result == "abc123"
        page.wait_for_selector.assert_awaited_once()
        element.get_attribute.assert_awaited_once_with("value")

    async def test_returns_none_when_not_found(self):
        page = Mock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        result = await _extract_csrf(page)
        assert result is None


@pytest.mark.asyncio
class TestDetectCaptcha:
    async def test_returns_true_when_recaptcha_present(self):
        page = Mock()
        page.wait_for_selector = AsyncMock(return_value=Mock())

        assert await _detect_captcha(page) is True

    async def test_returns_false_when_no_recaptcha(self):
        page = Mock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))

        assert await _detect_captcha(page) is False


@pytest.mark.asyncio
class TestTryAutoLogin:
    async def test_raises_captcha_if_recaptcha_detected(self):
        page = Mock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))
        page.goto = AsyncMock()

        async def side_effect(selector, **kw):
            if "recaptcha" in selector:
                return Mock()
            raise Exception("not found")

        page.wait_for_selector = side_effect

        with pytest.raises(CaptchaDetectedError, match="reCAPTCHA"):
            await try_auto_login(page, "user", "pass")

    async def test_raises_if_no_csrf_token(self):
        page = Mock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("not found"))
        page.goto = AsyncMock()

        call_count = {"recaptcha": 0, "csrf": 0}

        async def side_effect(selector, **kw):
            if "recaptcha" in selector:
                call_count["recaptcha"] += 1
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                call_count["csrf"] += 1
                raise Exception("timeout")
            raise Exception("not found")

        page.wait_for_selector = side_effect

        with pytest.raises(LoginFailedError, match="CSRF"):
            await try_auto_login(page, "user", "pass")

    async def test_raises_if_no_input_fields(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        page.goto = AsyncMock()

        async def side_effect(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                element = Mock()
                element.get_attribute = AsyncMock(return_value="token123")
                return element
            raise Exception("not found")

        page.wait_for_selector = side_effect
        username_el = Mock()
        username_el.count.return_value = 0
        password_el = Mock()
        password_el.count.return_value = 0

        def locator(sel):
            if "UserName" in sel or "Email" in sel or "email" in sel:
                return type("_", (), {"first": username_el})()
            if "Password" in sel or "password" in sel:
                return type("_", (), {"first": password_el})()
            return Mock()
        page.locator = locator

        with pytest.raises(LoginFailedError, match="username/password"):
            await try_auto_login(page, "user", "pass")

    async def test_submits_form_and_succeeds(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
        page.goto = AsyncMock()
        page.keyboard.press = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        csrf_element = Mock()
        csrf_element.get_attribute = AsyncMock(return_value="token123")

        async def wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector

        username_input = Mock()
        username_input.count.return_value = 1
        username_input.fill = AsyncMock()
        password_input = Mock()
        password_input.count.return_value = 1
        password_input.fill = AsyncMock()
        submit_btn = Mock()
        submit_btn.count.return_value = 0

        def locator(sel):
            if "UserName" in sel or "Email" in sel or "email" in sel:
                return type("_", (), {"first": username_input})()
            if "Password" in sel or "password" in sel:
                return type("_", (), {"first": password_input})()
            if "submit" in sel or "Sign In" in sel or "Log In" in sel:
                return type("_", (), {"first": submit_btn})()
            return Mock()
        page.locator = locator

        await try_auto_login(page, "testuser", "testpass")

        username_input.fill.assert_called_once_with("testuser")
        password_input.fill.assert_called_once_with("testpass")
        page.keyboard.press.assert_awaited_once_with("Enter")

    async def test_raises_on_login_failure(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        page.goto = AsyncMock()
        page.keyboard.press = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        csrf_element = Mock()
        csrf_element.get_attribute = AsyncMock(return_value="token123")

        async def wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector

        username_input = Mock()
        username_input.count.return_value = 1
        username_input.fill = AsyncMock()
        password_input = Mock()
        password_input.count.return_value = 1
        password_input.fill = AsyncMock()
        submit_btn = Mock()
        submit_btn.count.return_value = 0

        error_el = Mock()
        error_el.count.return_value = 1
        error_el.text_content.return_value = "Invalid credentials"

        def locator(sel):
            if "UserName" in sel or "Email" in sel or "email" in sel:
                return type("_", (), {"first": username_input})()
            if "Password" in sel or "password" in sel:
                return type("_", (), {"first": password_input})()
            if "submit" in sel or "Sign In" in sel or "Log In" in sel:
                return type("_", (), {"first": submit_btn})()
            if "validation" in sel or "alert" in sel:
                return type("_", (), {"first": error_el})()
            return Mock()
        page.locator = locator

        with pytest.raises(LoginFailedError, match="Invalid credentials"):
            await try_auto_login(page, "testuser", "testpass")


@pytest.mark.asyncio
class TestCaptureLoginInteractive:
    async def test_raises_if_session_not_started(self):
        session = Mock()
        session.manager = None

        with pytest.raises(SessionNotStartedError, match="Call session.start"):
            await capture_login_interactive(session, "/tmp/state.json")

    async def test_saves_storage_state(self, monkeypatch, tmp_path):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.goto = AsyncMock()
        session.manager.new_page = AsyncMock(return_value=page)
        session.manager.save_storage_state = AsyncMock()

        monkeypatch.setattr("builtins.input", lambda prompt="": "")

        state_path = tmp_path / "state.json"
        await capture_login_interactive(session, str(state_path))

        page.goto.assert_awaited_once()
        session.manager.save_storage_state.assert_awaited_once_with(str(state_path))


@pytest.mark.asyncio
class TestEnsureLoggedIn:
    async def test_raises_if_session_not_started(self):
        session = Mock()
        session.manager = None

        with pytest.raises(SessionNotStartedError, match="Call session.start"):
            await ensure_logged_in(session)

    async def test_returns_early_if_already_logged_in(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
        page.goto = AsyncMock()
        page.close = AsyncMock()

        async def wait_for_selector(*a, **kw):
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        session.manager.new_page = AsyncMock(return_value=page)

        await ensure_logged_in(session)

        page.close.assert_awaited_once()

    async def test_tries_auto_login_when_not_logged_in(self):
        session = Mock()
        session.manager = Mock()

        first_page = Mock()
        first_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        first_page.goto = AsyncMock()
        first_page.close = AsyncMock()

        async def first_wait(selector, **kw):
            raise Exception("not found")

        first_page.wait_for_selector = first_wait

        second_page = Mock()
        second_page.goto = AsyncMock()
        second_page.close = AsyncMock()
        second_page.keyboard.press = AsyncMock()
        second_page.wait_for_load_state = AsyncMock()
        csrf_element = Mock()
        csrf_element.get_attribute = AsyncMock(return_value="token123")

        async def second_wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        second_page.wait_for_selector = second_wait_for_selector
        second_page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        username_input = Mock()
        username_input.count.return_value = 1
        username_input.fill = AsyncMock()
        password_input = Mock()
        password_input.count.return_value = 1
        password_input.fill = AsyncMock()
        submit_btn = Mock()
        submit_btn.count.return_value = 0

        def locator(sel):
            if "UserName" in sel or "Email" in sel or "email" in sel:
                return type("_", (), {"first": username_input})()
            if "Password" in sel or "password" in sel:
                return type("_", (), {"first": password_input})()
            if "submit" in sel or "Sign In" in sel or "Log In" in sel:
                return type("_", (), {"first": submit_btn})()
            return Mock()
        second_page.locator = locator

        session.manager.new_page = AsyncMock(side_effect=[first_page, second_page])
        session.manager.save_storage_state = AsyncMock()

        await ensure_logged_in(session, username="testuser", password="testpass", storage_state_path="/tmp/state.json")

        assert session.manager.save_storage_state.called

    async def test_falls_back_to_capture_on_captcha(self, monkeypatch, tmp_path):
        session = Mock()
        session.manager = Mock()
        state_path = str(tmp_path / "state.json")

        first_page = Mock()
        first_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        first_page.goto = AsyncMock()
        first_page.close = AsyncMock()

        async def first_wait(*a, **kw):
            raise Exception("not found")

        first_page.wait_for_selector = first_wait

        second_page = Mock()
        second_page.goto = AsyncMock()

        async def second_wait(selector, **kw):
            if "recaptcha" in selector:
                return Mock()
            raise Exception("not found")
        second_page.wait_for_selector = second_wait
        second_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        third_page = Mock()
        third_page.goto = AsyncMock()
        third_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        session.manager.new_page = AsyncMock(side_effect=[first_page, second_page, third_page])
        session.manager.save_storage_state = AsyncMock()

        monkeypatch.setattr("builtins.input", lambda prompt="": "")

        await ensure_logged_in(session, username="user", password="pass", storage_state_path=state_path)

        session.manager.save_storage_state.assert_awaited_with(state_path)

    async def test_raises_if_no_credentials_and_no_path(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        page.goto = AsyncMock()
        page.close = AsyncMock()

        async def wait(*a, **kw):
            raise Exception("not found")

        page.wait_for_selector = wait
        session.manager.new_page = AsyncMock(return_value=page)

        with pytest.raises(AuthError, match="No credentials"):
            await ensure_logged_in(session)
