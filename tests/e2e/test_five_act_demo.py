"""The five-act demo in a real browser (headless Chromium): phone reports, engineer acts, the phone
rings for verification, and both answers (yes and no) are exercised. Skipped when Playwright or a
Chromium binary is not installed; run with:  python -m pytest tests/e2e -q
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]
CHROME = os.environ.get("JA_CHROME") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = _free_port()
    env = dict(os.environ, DB_PATH=str(tmp_path_factory.mktemp("e2e") / "e2e.db"), GNANI_API_KEY="", EVON_ENABLED="0",
               DEMO_MODE="1", DEMO_CALLBACK_DELAY_SEC="1", DEMO_VERIFY_DELAY_SEC="1", DEMO_IGNORE_QUIET_HOURS="1",
               APP_SALT="e2e-salt", APP_SECRET="e2e-secret")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.2)
    yield base
    proc.terminate(); proc.wait(5)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        kw = {"args": ["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]}
        if CHROME:
            kw["executable_path"] = CHROME
        try:
            b = p.chromium.launch(**kw)
        except Exception as e:  # no browser available
            pytest.skip(f"Chromium not available: {e}")
        yield b
        b.close()


def phone_turn(page, text):
    page.evaluate("t => window.JAPhone.sendTurn({text: t})", text)
    page.wait_for_function("() => !window.JAPhone.S.busy", timeout=10000)


def report(page, base):
    page.goto(base + "/phone")
    page.click("#btn-missed")
    page.wait_for_selector("#s-ring:not([hidden])", timeout=15000)
    page.click("#btn-answer")
    page.wait_for_selector("#s-call:not([hidden])")
    page.evaluate("document.getElementById('auto').checked = false")
    assert "एआय" in page.inner_text("#caption")                        # AI disclosed first
    phone_turn(page, "Shivapur madhe handpump 3 divas band aahe, 40 ghar")
    phone_turn(page, "nahi")
    assert "बरोबर" in page.inner_text("#caption")                       # read-back before any ticket
    phone_turn(page, "ho")
    page.wait_for_selector("#s-end:not([hidden])", timeout=15000)
    return page.inner_text("#end-refnum").strip()


def engineer_fix(staff, base, ref):
    staff.goto(base + "/engineer")
    card = staff.locator("article.job", has_text="#" + ref)
    card.locator("button", has_text="Acknowledge").click()
    staff.locator("article.job", has_text="#" + ref).locator("button", has_text="Report fix").click()
    staff.locator(".sheet button", has_text="Report fix and request the call").click()
    staff.wait_for_selector("text=Fix reported for #" + ref)


def answer_verification(page, word):
    page.click("#btn-home")
    page.wait_for_selector("#s-ring:not([hidden])", timeout=20000)
    assert page.inner_text("#ring-sub")                               # shows the ticket number
    page.click("#btn-answer")
    page.wait_for_selector("#s-call:not([hidden])")
    page.evaluate("document.getElementById('auto').checked = false")
    phone_turn(page, word)
    page.wait_for_selector("#s-end:not([hidden])", timeout=15000)
    return page.inner_text("#end-title")


def test_report_fix_verify_yes_and_reopen_no(server, browser):
    ctx = browser.new_context(permissions=["microphone"])
    phone, staff = ctx.new_page(), browser.new_context().new_page()
    errors = []
    phone.on("pageerror", lambda e: errors.append(str(e)))
    staff.on("pageerror", lambda e: errors.append(str(e)))
    staff.request.post(server + "/api/login", data={"pin": "2468"})

    ref = report(phone, server)
    assert ref.isdigit() and len(ref) == 5
    engineer_fix(staff, server, ref)
    assert "धन्यवाद" in answer_verification(phone, "ho")              # act 5: yes -> VERIFIED

    ref2 = report(phone, server)
    engineer_fix(staff, server, ref2)
    assert "पुन्हा उघडली" in answer_verification(phone, "nahi")       # no -> REOPENED

    staff.request.post(server + "/api/login", data={"pin": "1357"})
    staff.goto(server + "/dashboard")
    staff.wait_for_selector(".figure.lead")
    lead = staff.inner_text(".figure.lead")
    assert "50%" in lead and "1 reopened of 2" in lead                 # false-closure rate moved, with n
    staff.wait_for_selector(".vpin")                                   # the village pin is on the map
    assert not errors, errors
