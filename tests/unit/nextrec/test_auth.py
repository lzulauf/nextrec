from unittest.mock import Mock, PropertyMock, call

import pytest

from nextrec.auth import (
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


class TestIsLoggedIn:
    def test_returns_false_on_login_page(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn?returnUrl=.../List"
        assert is_logged_in(page) is False

    def test_returns_true_when_logout_link_present(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        def wait_for_selector(selector, **kw):
            assert "logout" in selector.lower() or "SignOut" in selector or "LogOff" in selector or "member" in selector
            return Mock()

        page.wait_for_selector = wait_for_selector
        assert is_logged_in(page) is True

    def test_returns_false_when_csrf_form_present_but_no_logout(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        call_count = {"logout": 0, "csrf": 0}

        def wait_for_selector(selector, **kw):
            if "logout" in selector.lower() or "SignOut" in selector or "LogOff" in selector or "member" in selector:
                call_count["logout"] += 1
                raise Exception("not found")
            if "AjaxAntiForgeryForm" in selector:
                call_count["csrf"] += 1
                return Mock()
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        assert is_logged_in(page) is False

    def test_returns_true_when_facility_list_url_matches(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        def wait_for_selector(*a, **kw):
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        assert is_logged_in(page) is True


class TestExtractCsrf:
    def test_returns_token_when_found(self):
        page = Mock()
        element = Mock()
        element.get_attribute.return_value = "abc123"
        page.wait_for_selector.return_value = element

        result = _extract_csrf(page)
        assert result == "abc123"
        page.wait_for_selector.assert_called_once()
        element.get_attribute.assert_called_once_with("value")

    def test_returns_none_when_not_found(self):
        page = Mock()
        page.wait_for_selector.side_effect = Exception("timeout")

        result = _extract_csrf(page)
        assert result is None


class TestDetectCaptcha:
    def test_returns_true_when_recaptcha_present(self):
        page = Mock()
        element = Mock()
        page.wait_for_selector.return_value = element

        assert _detect_captcha(page) is True

    def test_returns_false_when_no_recaptcha(self):
        page = Mock()
        page.wait_for_selector.side_effect = Exception("timeout")

        assert _detect_captcha(page) is False


class TestTryAutoLogin:
    def test_raises_captcha_if_recaptcha_detected(self):
        page = Mock()
        page.wait_for_selector.side_effect = [
            None,
        ]

        def side_effect(selector, **kw):
            if "recaptcha" in selector:
                return Mock()
            raise Exception("not found")

        page.wait_for_selector = side_effect

        with pytest.raises(CaptchaDetectedError, match="reCAPTCHA"):
            try_auto_login(page, "user", "pass")

    def test_raises_if_no_csrf_token(self):
        page = Mock()
        page.wait_for_selector.side_effect = [
            None,
        ]

        call_count = {"recaptcha": 0, "csrf": 0}

        def side_effect(selector, **kw):
            if "recaptcha" in selector:
                call_count["recaptcha"] += 1
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                call_count["csrf"] += 1
                raise Exception("timeout")
            raise Exception("not found")

        page.wait_for_selector = side_effect

        with pytest.raises(LoginFailedError, match="CSRF"):
            try_auto_login(page, "user", "pass")

    def test_raises_if_no_input_fields(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        def side_effect(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                element = Mock()
                element.get_attribute.return_value = "token123"
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
            try_auto_login(page, "user", "pass")

    def test_submits_form_and_succeeds(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
        csrf_element = Mock()
        csrf_element.get_attribute.return_value = "token123"

        def wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector

        username_input = Mock()
        username_input.count.return_value = 1
        password_input = Mock()
        password_input.count.return_value = 1
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

        try_auto_login(page, "testuser", "testpass")

        username_input.fill.assert_called_once_with("testuser")
        password_input.fill.assert_called_once_with("testpass")
        page.keyboard.press.assert_called_once_with("Enter")

    def test_raises_on_login_failure(self):
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        csrf_element = Mock()
        csrf_element.get_attribute.return_value = "token123"

        def wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector

        username_input = Mock()
        username_input.count.return_value = 1
        password_input = Mock()
        password_input.count.return_value = 1
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
            try_auto_login(page, "testuser", "testpass")


class TestCaptureLoginInteractive:
    def test_raises_if_session_not_started(self):
        session = Mock()
        session.manager = None

        with pytest.raises(SessionNotStartedError, match="Call session.start"):
            capture_login_interactive(session, "/tmp/state.json")

    def test_saves_storage_state(self, monkeypatch, tmp_path):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        session.manager.new_page.return_value = page

        monkeypatch.setattr("builtins.input", lambda prompt="": "")

        state_path = tmp_path / "state.json"
        capture_login_interactive(session, str(state_path))

        page.goto.assert_called_once()
        session.manager.save_storage_state.assert_called_once_with(str(state_path))


class TestEnsureLoggedIn:
    def test_raises_if_session_not_started(self):
        session = Mock()
        session.manager = None

        with pytest.raises(SessionNotStartedError, match="Call session.start"):
            ensure_logged_in(session)

    def test_returns_early_if_already_logged_in(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        def wait_for_selector(*a, **kw):
            raise Exception("not found")

        page.wait_for_selector = wait_for_selector
        session.manager.new_page.return_value = page

        ensure_logged_in(session)

        page.close.assert_called_once()

    def test_tries_auto_login_when_not_logged_in(self):
        session = Mock()
        session.manager = Mock()

        first_page = Mock()
        first_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        second_page = Mock()
        csrf_element = Mock()
        csrf_element.get_attribute.return_value = "token123"

        def second_wait_for_selector(selector, **kw):
            if "recaptcha" in selector:
                raise Exception("not found")
            if "__RequestVerificationToken" in selector:
                return csrf_element
            raise Exception("not found")

        second_page.wait_for_selector = second_wait_for_selector
        second_page.url = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"

        username_input = Mock()
        username_input.count.return_value = 1
        password_input = Mock()
        password_input.count.return_value = 1
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

        session.manager.new_page.side_effect = [first_page, second_page]

        ensure_logged_in(session, username="testuser", password="testpass", storage_state_path="/tmp/state.json")

        assert session.manager.save_storage_state.called

    def test_falls_back_to_capture_on_captcha(self, monkeypatch, tmp_path):
        session = Mock()
        session.manager = Mock()
        state_path = str(tmp_path / "state.json")

        first_page = Mock()
        first_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        second_page = Mock()

        def second_wait(selector, **kw):
            if "recaptcha" in selector:
                return Mock()
            raise Exception("not found")
        second_page.wait_for_selector = second_wait
        second_page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        third_page = Mock()
        third_page.url = LOGIN_URL = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"

        session.manager.new_page.side_effect = [first_page, second_page, third_page]

        monkeypatch.setattr("builtins.input", lambda prompt="": "")

        ensure_logged_in(session, username="user", password="pass", storage_state_path=state_path)

        session.manager.save_storage_state.assert_called_with(state_path)

    def test_raises_if_no_credentials_and_no_path(self):
        session = Mock()
        session.manager = Mock()
        page = Mock()
        page.url = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
        session.manager.new_page.return_value = page

        with pytest.raises(Exception, match="No credentials"):
            ensure_logged_in(session)
