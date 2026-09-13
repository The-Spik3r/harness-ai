"""The Reports section in a real browser, driven over the Chrome DevTools Protocol.

`tests/test_reports_pages.py` proves the routes compile and each URL lands in the
right state arm; it cannot prove the browser shows it. This file does: it loads
the pages from a running server in headless Chrome and asserts on the DOM, the
address bar, computed styles and the console.

**Opt-in.** The suite does not build the frontend, so there is nothing to point a
browser at in CI. Run a server, then set `REPORTS_E2E_URL`:

    cd chat_ui
    DB_BOOTSTRAP_ENABLED=false PII_REDACTION_ENABLED=false RBAC_ENABLED=false \\
      reflex run --env prod --single-port --backend-port 3107
    REPORTS_E2E_URL=http://127.0.0.1:3107 pytest tests/test_reports_e2e.py

Chrome is found at its usual install path or `CHROME_PATH`. Without either
variable resolving, every test here skips.

**Expectations come from the service, not from literals.** The server reads the
repository's own `.agents/`, which grows with every story, so the expected cards,
neighbours and commits are computed with `app.services.reports` against the same
directory rather than typed in.

**Waiting is explicit.** A Reflex page paints its shell first and receives state
over a websocket afterwards, so a DOM read straight after navigation sees an empty
feed. Every assertion waits on a condition in the page, never on a sleep.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.services import reports
from chat_ui.chat_ui import reports_copy

BASE_URL = os.environ.get("REPORTS_E2E_URL", "").rstrip("/")

_CHROME_CANDIDATES = (
    os.environ.get("CHROME_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
CHROME = next((c for c in _CHROME_CANDIDATES if c and Path(c).exists()), None)

pytestmark = [
    pytest.mark.skipif(not BASE_URL, reason="set REPORTS_E2E_URL to a running server"),
    pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium found (set CHROME_PATH)"),
]

WIDE = 1400
NARROW = 700  # below theme.SESSION_RAIL_COLLAPSE_W (60rem = 960px)
PHONE = 420


# --- A minimal CDP client ------------------------------------------------------------


class Page:
    """One tab: navigate, evaluate, wait, and collect console errors."""

    def __init__(self, ws):
        self._ws = ws
        self._next_id = 0
        self.errors: list[str] = []

    def _call(self, method: str, **params):
        self._next_id += 1
        call_id = self._next_id
        self._ws.send(json.dumps({"id": call_id, "method": method, "params": params}))
        while True:
            message = json.loads(self._ws.recv(timeout=30))
            if message.get("id") == call_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            self._record(message)

    def _record(self, message: dict) -> None:
        method = message.get("method")
        params = message.get("params", {})
        if method == "Runtime.exceptionThrown":
            self.errors.append(params["exceptionDetails"].get("text", "exception"))
        elif method == "Runtime.consoleAPICalled" and params.get("type") == "error":
            self.errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in params["args"]))

    def enable(self) -> None:
        self._call("Page.enable")
        self._call("Runtime.enable")

    def goto(self, path: str, width: int = WIDE) -> None:
        self._call("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=False)
        self._call("Page.navigate", url=BASE_URL + path)

    def js(self, expression: str):
        result = self._call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise AssertionError(f"page script failed: {result['exceptionDetails']}")
        return result.get("result", {}).get("value")

    def wait(self, predicate: str, timeout: float = 15.0):
        """Poll a JS expression until truthy; return its value or fail with the page text."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = self.js(predicate)
            except AssertionError:
                value = None
            if value:
                return value
            time.sleep(0.15)
        text = self.js("document.body ? document.body.innerText.slice(0, 600) : ''")
        raise AssertionError(f"timed out waiting for: {predicate}\n--- page text ---\n{text}")

    def text(self) -> str:
        return self.js("document.body.innerText")

    def screenshot(self, name: str) -> Path:
        import base64

        out = Path(tempfile.gettempdir()) / "reports-e2e" / f"{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(self._call("Page.captureScreenshot", format="png")["data"]))
        return out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def browser():
    from websockets.sync.client import connect

    port = _free_port()
    profile = tempfile.mkdtemp(prefix="reports-e2e-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        target = None
        while time.monotonic() < deadline and target is None:
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                target = next((t for t in targets if t["type"] == "page"), None)
            except (OSError, ValueError):
                time.sleep(0.2)
        assert target, "Chrome did not expose a page target"
        with connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            page = Page(ws)
            page.enable()
            yield page
    finally:
        proc.kill()
        proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)


@pytest.fixture
def page(browser):
    """The shared tab, on the light ground, with a clean error log per test."""
    browser.goto("/reports")
    browser.wait("document.readyState === 'complete'")
    browser.js("localStorage.setItem('theme', 'light')")
    browser.errors.clear()
    yield browser
    assert browser.errors == [], f"console errors: {browser.errors}"


@pytest.fixture(scope="module")
def corpus():
    reports.clear_cache()
    return {
        "cards": reports.list_stories(),
        "prds": reports.list_prds(),
    }


# The feed's card links, in order: every link to a story that is neither in the
# navigation column nor the detail page's pager.
_CARD_HREFS = "[...new Set([...document.querySelectorAll('a[href*=\"/story-\"]')].filter(a => a.closest('#reports-nav') === null && !a.innerText.startsWith('←') && !a.innerText.endsWith('→')).map(a => a.getAttribute('href')))]"


def _cards_js() -> str:
    return _CARD_HREFS


def _button(label: str) -> str:
    return f"[...document.querySelectorAll('button')].find(b => b.innerText.trim() === {json.dumps(label)})"


def _set_input(element_js: str, value: str, prototype: str = "HTMLInputElement", event: str = "input") -> str:
    return (
        f"(() => {{ const el = {element_js}; "
        f"Object.getOwnPropertyDescriptor({prototype}.prototype, 'value').set.call(el, {json.dumps(value)}); "
        f"el.dispatchEvent(new Event({json.dumps(event)}, {{bubbles: true}})); return true; }})()"
    )


# --- HTTP ------------------------------------------------------------------------------


def _status(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def test_the_feed_route_answers_200():
    status, body = _status("/reports")
    assert status == 200
    assert reports_copy.PAGE_TITLE.split(" ")[0] in body


@pytest.mark.parametrize("path", ["/reports/prd-001", "/reports/prd-001/story-001"])
def test_dynamic_routes_are_served_the_app_shell(path):
    """Dynamic routes have no prerendered file: the server answers with the SPA
    shell, which boots the client router. Reflex's own single-port server sends it
    with a 404 status; the Docker image's Caddy `try_files ... /404.html` sends 200.
    What must hold either way is that the shell, not an error page, arrives."""
    status, body = _status(path)
    assert status in (200, 404)
    assert "<script" in body and "entry.client" in body


# --- Feed ------------------------------------------------------------------------------


def test_feed_renders_every_story_newest_first(page, corpus):
    page.goto("/reports")
    expected = [f"/reports/{c.prd_slug}/{c.slug}" for c in corpus["cards"]]
    hrefs = page.wait(f"(() => {{ const h = {_cards_js()}; return h.length === {len(expected)} ? h : null; }})()")
    assert hrefs == expected
    assert page.js("document.title") == reports_copy.PAGE_TITLE


def test_first_card_shows_the_newest_story(page, corpus):
    newest = corpus["cards"][0]
    page.goto("/reports")
    page.wait(f"document.body.innerText.includes({json.dumps(newest.story_id + reports_copy.TITLE_SEPARATOR)})")
    card_text = page.js(
        f"document.querySelector('a[href=\"/reports/{newest.prd_slug}/{newest.slug}\"]').innerText"
    )
    assert newest.prd_id in card_text
    assert reports_copy.STATUS_LABELS[newest.status] in card_text
    if newest.commit:
        assert newest.commit in card_text


def test_url_filters_are_applied_and_restored_into_the_controls(page, corpus):
    target = next(c for c in corpus["cards"] if c.commit and c.status == "done")
    page.goto(f"/reports?status=done&q={target.commit}")
    expected = [f"/reports/{c.prd_slug}/{c.slug}" for c in reports.list_stories(status="done", q=target.commit)]
    hrefs = page.wait(f"(() => {{ const h = {_cards_js()}; return h.length === {len(expected)} ? h : null; }})()")
    assert hrefs == expected
    assert page.js("document.getElementById('reports_search_input').value") == target.commit
    assert page.js("document.querySelector('select').value") == "done"


def test_typing_filters_live_and_rewrites_the_address(page, corpus):
    page.goto("/reports")
    page.wait(f"{_cards_js()}.length === {len(corpus['cards'])}")
    page.js(_set_input("document.getElementById('reports_search_input')", "turso"))
    expected = reports.list_stories(q="turso")
    page.wait(f"{_cards_js()}.length === {len(expected)}")
    page.wait("location.search === '?q=turso'")
    assert page.js("location.pathname").rstrip("/") == "/reports"


def test_status_select_filters_and_rewrites_the_address(page):
    page.goto("/reports/prd-001")
    page.wait(f"{_cards_js()}.length > 0")
    page.js(_set_input("document.querySelector('select')", "in-progress", "HTMLSelectElement", "change"))
    expected = reports.list_stories(prd_id="prd-001", status="in-progress")
    page.wait("location.search === '?status=in-progress'")
    if expected:
        page.wait(f"{_cards_js()}.length === {len(expected)}")
    else:
        page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.NO_MATCH_TITLE)})")


def test_no_match_then_clear_filters_restores_the_whole_feed(page, corpus):
    page.goto("/reports?status=blocked&q=zz-no-story-has-this")
    page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.NO_MATCH_TITLE)})")
    assert page.js(f"{_cards_js()}.length") == 0
    page.js(f"{_button(reports_copy.CLEAR_FILTERS_LABEL)}.click()")
    page.wait(f"{_cards_js()}.length === {len(corpus['cards'])}")
    page.wait("location.search === ''")
    assert page.js("document.getElementById('reports_search_input').value") == ""


def test_the_empty_and_no_match_states_are_not_the_fault_state(page):
    page.goto("/reports?q=zz-no-story-has-this")
    page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.NO_MATCH_TITLE)})")
    text = page.text()
    assert reports_copy.FAULT_TITLE not in text
    assert reports_copy.EMPTY_TITLE not in text
    assert page.js("document.querySelectorAll('[role=alert]').length") == 0


# --- Navigation ----------------------------------------------------------------------------


def test_every_prd_is_listed_with_its_progress(page, corpus):
    page.goto("/reports")
    nav_text = page.wait(
        f"(() => {{ const t = document.getElementById('reports-nav').innerText; "
        f"return t.includes({json.dumps(corpus['prds'][-1].name)}) ? t : null; }})()"
    )
    for prd in corpus["prds"]:
        assert prd.name in nav_text
        label = f"{prd.done}/{prd.total} done" if prd.total else reports_copy.NAV_NO_STORIES
        assert label in nav_text


def test_the_prd_route_scopes_the_feed_and_marks_the_link(page):
    prd = next(p for p in reports.list_prds() if p.total)
    page.goto(f"/reports/{prd.slug}")
    expected = [f"/reports/{c.prd_slug}/{c.slug}" for c in reports.list_stories(prd_id=prd.slug)]
    hrefs = page.wait(f"(() => {{ const h = {_cards_js()}; return h.length === {len(expected)} ? h : null; }})()")
    assert hrefs == expected
    current = page.js("[...document.querySelectorAll('#reports-nav a[aria-current=page]')].map(a => a.getAttribute('href'))")
    assert current == [f"/reports/{prd.slug}"]


def test_clicking_a_prd_navigates_client_side(page):
    prd = next(p for p in reports.list_prds() if p.total)
    page.goto("/reports")
    page.wait(f"!!document.querySelector('#reports-nav a[href=\"/reports/{prd.slug}\"]')")
    page.js("window.__noReload = true")
    page.js(f"document.querySelector('#reports-nav a[href=\"/reports/{prd.slug}\"]').click()")
    page.wait(f"location.pathname === '/reports/{prd.slug}'")
    expected = len(reports.list_stories(prd_id=prd.slug))
    page.wait(f"{_cards_js()}.length === {expected}")
    assert page.js("window.__noReload === true"), "the click reloaded the page"


def test_unknown_prd_shows_not_found(page):
    page.goto("/reports/prd-999")
    page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.PRD_NOT_FOUND_TITLE)})")


# --- Detail ---------------------------------------------------------------------------------


def _story_with_neighbours():
    for card in reports.list_stories():
        detail = reports.get_story_detail(card.prd_slug, card.slug)
        if detail and detail.has_report and detail.prev and detail.next and detail.files and detail.validation:
            return detail
    pytest.skip("no story with a report and both neighbours in this record")


def test_detail_renders_the_report(page):
    detail = _story_with_neighbours()
    card = detail.card
    page.goto(f"/reports/{card.prd_slug}/{card.slug}")
    heading = page.wait("document.querySelector('h1') && document.querySelector('h1').innerText")
    assert heading == f"{card.story_id}{reports_copy.TITLE_SEPARATOR}{card.title}"
    text = page.text()
    assert detail.summary[0][:60] in text
    for item in detail.acceptance[:3]:
        assert item.text[:40] in text
    assert detail.plan in text


def test_detail_links_commit_and_neighbours(page):
    detail = _story_with_neighbours()
    card = detail.card
    page.goto(f"/reports/{card.prd_slug}/{card.slug}")
    page.wait("!!document.querySelector('h1')")
    commit = page.js("document.querySelector('a[href*=\"/commit/\"]').href")
    assert commit == reports.commit_url(card.commit)
    assert page.js("document.querySelector('a[href*=\"/commit/\"]').target") == "_blank"
    pager = page.js(
        "[...document.querySelectorAll('a')].filter(a => /^←|→$/.test(a.innerText.trim())).map(a => a.getAttribute('href'))"
    )
    assert pager == [
        f"/reports/{card.prd_slug}/{detail.prev.slug}",
        f"/reports/{card.prd_slug}/{detail.next.slug}",
    ]
    crumbs = page.js("[...document.querySelectorAll('a')].map(a => a.getAttribute('href'))")
    assert f"/reports/{card.prd_slug}" in crumbs


def test_files_and_validation_start_collapsed_and_open_on_click(page):
    detail = _story_with_neighbours()
    card = detail.card
    page.goto(f"/reports/{card.prd_slug}/{card.slug}")
    page.wait("document.querySelectorAll('details').length === 2")
    assert page.js("[...document.querySelectorAll('details')].map(d => d.open)") == [False, False]
    summaries = page.js("[...document.querySelectorAll('details > summary')].map(s => s.innerText)")
    assert str(len(detail.files)) in summaries[0]
    passed = sum(1 for v in detail.validation if v.passed)
    assert f"{passed}/{len(detail.validation)}" in summaries[1]
    page.js("document.querySelector('details > summary').click()")
    page.wait("document.querySelector('details').open === true")
    visible = page.js("document.querySelector('details').innerText")
    assert detail.files[0].path in visible


def test_pager_navigates_to_the_next_story(page):
    detail = _story_with_neighbours()
    card = detail.card
    page.goto(f"/reports/{card.prd_slug}/{card.slug}")
    page.wait("!!document.querySelector('h1')")
    page.js("[...document.querySelectorAll('a')].find(a => a.innerText.trim().endsWith('→')).click()")
    page.wait(f"location.pathname === '/reports/{card.prd_slug}/{detail.next.slug}'")
    page.wait(f"document.querySelector('h1') && document.querySelector('h1').innerText.startsWith({json.dumps(detail.next.story_id)})")


def test_a_story_without_a_report_says_so(page):
    missing = next(
        (c for c in reports.list_stories() if not reports.get_story_detail(c.prd_slug, c.slug).has_report),
        None,
    )
    if missing is None:
        pytest.skip("every story in this record has a report")
    page.goto(f"/reports/{missing.prd_id}/{missing.story_id}")  # upper case on purpose
    page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.NO_REPORT_TITLE)})")
    assert page.js("document.querySelectorAll('details').length") == 0


def test_unknown_story_shows_not_found(page):
    page.goto("/reports/prd-001/story-999")
    page.wait(f"document.body.innerText.includes({json.dumps(reports_copy.STORY_NOT_FOUND_TITLE)})")


# --- Layout -----------------------------------------------------------------------------------


def test_wide_viewport_shows_the_nav_and_hides_the_disclosure(page):
    page.goto("/reports", WIDE)
    page.wait(f"{_cards_js()}.length > 0")
    assert page.js("getComputedStyle(document.getElementById('reports-nav')).visibility") == "visible"
    button = _button(reports_copy.NAV_DISCLOSURE_LABEL)
    assert page.js(f"getComputedStyle({button}.parentElement).display") == "none"


def test_narrow_viewport_collapses_the_nav_behind_the_disclosure(page):
    page.goto("/reports", NARROW)
    page.wait(f"{_cards_js()}.length > 0")
    button = _button(reports_copy.NAV_DISCLOSURE_LABEL)
    assert page.js("getComputedStyle(document.getElementById('reports-nav')).visibility") == "hidden"
    assert page.js(f"{button}.getAttribute('aria-expanded')") == "false"
    page.js(f"{button}.click()")
    page.wait("getComputedStyle(document.getElementById('reports-nav')).visibility === 'visible'")
    assert page.js(f"{button}.getAttribute('aria-expanded')") == "true"


@pytest.mark.parametrize("path", ["/reports", "/reports/prd-001/story-001"])
def test_no_horizontal_scroll_at_phone_width(page, path):
    page.goto(path, PHONE)
    page.wait("document.body.innerText.includes('STORY-')")
    overflow = page.js("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 0, f"page scrolls sideways by {overflow}px at {PHONE}px"


def test_the_ground_switch_flips_the_palette(page):
    page.goto("/reports")
    page.wait(f"{_cards_js()}.length > 0")
    before = page.js("document.documentElement.className")
    card_bg_before = page.js(f"getComputedStyle(document.querySelector('a[href*=\"/story-\"]')).backgroundColor")
    page.js("document.querySelector('.hx-ground-toggle').click()")
    page.wait(f"document.documentElement.className !== {json.dumps(before)}")
    card_bg_after = page.wait(
        f"(() => {{ const c = getComputedStyle(document.querySelector('a[href*=\"/story-\"]')).backgroundColor; "
        f"return c !== {json.dumps(card_bg_before)} ? c : null; }})()"
    )
    assert card_bg_after != card_bg_before
    page.js("localStorage.setItem('theme', 'light')")
    page.screenshot("feed-after-ground-switch")
