Decision title: Browser Automation Framework Selection

Problem statement
-----------------
Select a browser automation framework to run headless logins, query facility availability, perform add-to-cart actions, and re-open headed sessions for user checkout.

Why this matters now
--------------------
Browser automation is core to the product. The choice affects reliability, API ergonomics, language bindings, session persistence, and how easily we can detect and handle CAPTCHAs and network/XHR endpoints.

Goals and decision criteria
--------------------------
Goals
- Robust headless and headed browser control with storage state persistence.
- First-class support for network interception and request replay.
- Good documentation, cross-platform stability, and test tooling.

Decision criteria
- Reliability and stability
- Network interception and storageState features
- Language ecosystem / developer familiarity (Python preferred)
- Test tooling and CI friendliness

Options considered
------------------
1) Playwright (Python)
2) Puppeteer (Node) / Playwright (Node)
3) Selenium (WebDriver)

Tradeoff analysis
-----------------

Option 1 — Playwright (Python)
- What this means: Use Playwright's Python bindings to script headless and headed browsers, capture `storageState`, intercept/follow XHR endpoints, and run Playwright tests in CI.
- Pros: Modern API, built-in `storageState` persistence, reliable headless/headed parity, network routing/interception, good test integration, cross-platform. Python bindings are mature.
- Cons: Requires users to install Playwright browsers (CLI helper available). Slightly larger dependency footprint than a pure HTTP approach.
- Criteria impact: Reliability=High, Network features=High, Python ecosystem=High, CI friendliness=High.

Option 2 — Puppeteer / Playwright (Node)
- What this means: Use Node-based Playwright or Puppeteer libraries to automate the browser.
- Pros: Similar automation capabilities as Playwright Python, with large community and tooling. Node Playwright has feature parity.
- Cons: If primary repo uses Python, adding Node creates multi-language complexity. Node packaging can be heavier for Python-first projects.
- Criteria impact: Reliability=High, Network features=High, Python ecosystem=Low (if repo is Python-first), CI friendliness=High.

Option 3 — Selenium WebDriver
- What this means: Use Selenium with a browser driver (geckodriver/chromedriver) to control browsers.
- Pros: Long history, broad compatibility.
- Cons: Less consistent headless/headed parity, more brittle for modern JS-heavy apps, weaker built-in network interception and storageState features.
- Criteria impact: Reliability=Medium, Network features=Low, Python ecosystem=Medium, CI friendliness=Medium.

Recommendation
--------------
Choose Playwright with Python bindings as the primary browser framework. It offers the best balance of reliability, storage state handling, network interception for capturing XHR endpoints, and smooth CI integration for Playwright tests.

Confidence and risks
--------------------
- Confidence: High.
- Risk: Users must install Playwright browsers; mitigate by adding setup scripts and clear `requirements.txt` / `pyproject.toml` instructions and providing `playwright install` automation in setup.

Follow-up actions
-----------------
- Add `playwright` to project dependencies and create `nextrec/browser.py` wrapper.
- Create a discovery spike to record the live endpoints and XHR payloads for the Oakland deployment using Playwright's network tracing.
