import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from nextrec.browser import BrowserSession

logger = logging.getLogger(__name__)

LOGIN_URL = "https://cityofoakland.perfectmind.com/Clients/MemberRegistration/MemberSignIn"
FACILITY_LIST_URL = "https://cityofoakland.perfectmind.com/Clients/BookMe4FacilityList/List"
CSRF_SELECTOR = '#AjaxAntiForgeryForm input[name="__RequestVerificationToken"]'


class AuthError(Exception):
    """Base error for authentication failures."""


class LoginFailedError(AuthError):
    """Credentials were rejected or login form returned an unexpected result."""


class CaptchaDetectedError(AuthError):
    """reCAPTCHA or similar challenge detected; automated login cannot proceed."""


class SessionNotStartedError(AuthError):
    """BrowserSession has not been started."""


def is_logged_in(page: Page) -> bool:
    current = page.url
    logger.debug("Checking login state at: %s", current)
    if LOGIN_URL in current:
        return False
    try:
        page.wait_for_selector("#logoutLink, .logout, a[href*='SignOut'], a[href*='LogOff'], .member-info", timeout=5000)
        return True
    except Exception:
        pass
    try:
        page.wait_for_selector("#AjaxAntiForgeryForm", timeout=2000)
        return False
    except Exception:
        pass
    return FACILITY_LIST_URL in current


def _extract_csrf(page: Page) -> Optional[str]:
    try:
        element = page.wait_for_selector(CSRF_SELECTOR, state="attached", timeout=5000)
        if element:
            token = element.get_attribute("value")
            logger.debug("Extracted CSRF token: %s...", token[:20] if token else "None")
            return token
    except Exception:
        logger.warning("Could not find CSRF token via %s", CSRF_SELECTOR)
    return None


def _detect_captcha(page: Page) -> bool:
    try:
        captcha = page.wait_for_selector(".g-recaptcha, iframe[src*='recaptcha'], div[class*='recaptcha']", timeout=3000)
        return captcha is not None
    except Exception:
        return False


def try_auto_login(page: Page, username: str, password: str, return_url: str = FACILITY_LIST_URL) -> None:
    login_url = f"{LOGIN_URL}?returnUrl={return_url}"
    logger.info("Navigating to login page: %s", login_url)
    page.goto(login_url, wait_until="networkidle")

    if _detect_captcha(page):
        raise CaptchaDetectedError("reCAPTCHA detected on login page; cannot automate login")

    token = _extract_csrf(page)
    if not token:
        raise LoginFailedError("Could not extract CSRF token from login page")

    username_selector = page.locator("input[name='UserName'], input[name='Email'], input[type='email']").first
    password_selector = page.locator("input[name='Password'], input[type='password']").first

    if not username_selector.count() or not password_selector.count():
        raise LoginFailedError("Could not find username/password fields on login page")

    username_selector.fill(username)
    password_selector.fill(password)

    logger.info("Submitting login form")
    submit_selector = page.locator("input[type='submit'], button[type='submit'], button:has-text('Sign In'), button:has-text('Log In')").first
    if submit_selector.count():
        submit_selector.click()
    else:
        page.keyboard.press("Enter")

    page.wait_for_load_state("networkidle")

    if LOGIN_URL in page.url:
        error_msg = page.locator(".field-validation-error, .validation-summary-errors, .alert-danger").first
        text = error_msg.text_content() if error_msg.count() else "Unknown error"
        raise LoginFailedError(f"Login failed: {text.strip()}")


def capture_login_interactive(session: BrowserSession, storage_state_path: str) -> None:
    if session.manager is None:
        raise SessionNotStartedError("Call session.start() before capturing interactive login")

    target = Path(storage_state_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Opening headed browser for manual login...")
    page = session.manager.new_page()
    page.goto(LOGIN_URL, wait_until="load")

    print("=" * 60)
    print("A headed browser has opened. Please log in to the PerfectMind site.")
    print("After logging in successfully, press Enter here to save the session.")
    print("=" * 60)
    input()

    session.manager.save_storage_state(str(target))
    logger.info("Saved storage state to %s", target)


def ensure_logged_in(
    session: BrowserSession,
    username: Optional[str] = None,
    password: Optional[str] = None,
    storage_state_path: Optional[str] = None,
) -> None:
    if session.manager is None:
        raise SessionNotStartedError("Call session.start() before ensure_logged_in")

    page = session.manager.new_page()
    page.goto(FACILITY_LIST_URL, wait_until="networkidle")

    if is_logged_in(page):
        logger.info("Already logged in via stored session")
        page.close()
        return

    page.close()

    if username and password:
        logger.info("Attempting automated login")
        login_page = session.manager.new_page()
        try:
            try_auto_login(login_page, username, password)
            logger.info("Automated login succeeded")
            if storage_state_path:
                session.manager.save_storage_state(storage_state_path)
            return
        except CaptchaDetectedError:
            logger.warning("CAPTCHA detected; falling back to manual login")
        except LoginFailedError:
            logger.warning("Automated login failed; falling back to manual login")

    if storage_state_path:
        capture_login_interactive(session, storage_state_path)
    else:
        raise AuthError("No credentials provided and no storage_state_path for manual fallback")
