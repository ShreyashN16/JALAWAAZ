"""Drive a running Jal Awaaz demo server through all acts and save one screenshot per moment.

Writes raw/<id>.jpg (1440x800 CSS px at DPR 1.5) and raw/moments.json with highlight boxes.
Needs a fresh server started as in README.md (DEMO_MODE=1, short delays, no Gnani key, empty database).
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("JA_BASE", "http://127.0.0.1:8030")
CHROME = os.environ.get("JA_CHROME")
OUT = Path(__file__).parent / "raw"
OUT.mkdir(exist_ok=True)
VW, VH, DPR = 1440, 800, 1.5
moments = {}
log = print


def shot(page, mid, hl=None, settle=500):
    page.wait_for_timeout(settle)
    page.screenshot(path=str(OUT / f"{mid}.jpg"), type="jpeg", quality=92)
    boxes = []
    for sel in ([hl] if isinstance(hl, str) else (hl or [])):
        try:
            b = page.locator(sel).first.bounding_box(timeout=1500)
        except Exception:
            b = None
        if b:
            boxes.append(b)
        else:
            log(f"  ! no box for {sel} in {mid}")
    moments[mid] = {"img": f"{mid}.jpg", "boxes": boxes, "url": page.url.replace(BASE, "")}
    log(f"shot {mid} {page.url.replace(BASE, '')} boxes={len(boxes)}")


def caption(page):
    return page.inner_text("#caption")


def turn(page, text):
    page.evaluate("t => window.JAPhone.sendTurn({text: t})", text)
    page.wait_for_function("() => !window.JAPhone.S.busy", timeout=15000)
    page.wait_for_timeout(300)


def answer_followups(page, max_turns=5):
    """Answer follow-up questions until the read-back (asks 'बरोबर आहे का')."""
    for _ in range(max_turns):
        c = caption(page)
        if "बरोबर" in c:
            return
        if "पिण्याचे" in c:
            turn(page, "हो")
        elif any(w in c for w in ("पोटदुखी", "उलट्या", "ताप")):
            turn(page, "नाही")
        elif "किती घर" in c:
            turn(page, "40")
        elif "किती दिवस" in c:
            turn(page, "3")
        else:
            log("  ? unexpected question:", c)
            turn(page, "नाही")
    raise RuntimeError("no read-back reached")


def await_ring(page, timeout=30000):
    """Leave the end screen if it is still showing, then wait for the next incoming call."""
    if page.locator("#s-ring:not([hidden])").count() == 0 and page.locator("#btn-home").is_visible():
        page.click("#btn-home")
    page.wait_for_selector("#s-ring:not([hidden])", timeout=timeout)


def refresh_dash(dash, view="top"):
    dash.goto(BASE + "/dashboard")
    dash.wait_for_selector(".figure.lead", timeout=10000)
    dash.wait_for_load_state("networkidle")
    dash.wait_for_timeout(1200)
    if view == "map":
        dash.evaluate("document.querySelector('#map').scrollIntoView({block: 'center'})")
        dash.wait_for_timeout(500)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME,
                              args=["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        vp = {"viewport": {"width": VW, "height": VH}, "device_scale_factor": DPR, "locale": "en-IN",
              "timezone_id": "Asia/Kolkata"}
        phone = b.new_context(permissions=["microphone"], **vp).new_page()
        officer_ctx, eng_ctx = b.new_context(**vp), b.new_context(**vp)
        dash, eng = officer_ctx.new_page(), eng_ctx.new_page()
        errors = []
        for pg in (phone, dash, eng):
            pg.on("pageerror", lambda e: errors.append(str(e)))
        dash.request.post(BASE + "/api/login", data={"pin": "1357"})
        eng.request.post(BASE + "/api/login", data={"pin": "2468"})

        # ---- Act 1: missed call
        refresh_dash(dash)
        shot(dash, "d00_empty", ".figure.lead")
        phone.goto(BASE + "/phone")
        phone.wait_for_selector("#btn-missed")
        shot(phone, "p01_home", "#btn-missed", settle=1200)
        phone.click("#btn-missed")
        phone.wait_for_selector("#s-wait:not([hidden])")
        shot(phone, "p02_wait", ".device", settle=700)
        phone.wait_for_selector("#s-ring:not([hidden])", timeout=20000)
        shot(phone, "p03_ring", ".device", settle=600)

        # ---- Act 2: report
        phone.click("#btn-answer")
        phone.wait_for_selector("#s-call:not([hidden])")
        phone.evaluate("document.getElementById('auto').checked = false")
        phone.wait_for_function("() => !window.JAPhone.S.busy", timeout=15000)
        shot(phone, "p04_greet", "#caption", settle=900)
        turn(phone, "खेड शिवापूरमध्ये हातपंप 3 दिवस बंद आहे, 40 घरं")
        shot(phone, "p05_said", ["#slots"], settle=600)
        answer_followups(phone)
        shot(phone, "p06_readback", "#caption", settle=600)
        turn(phone, "हो")
        phone.wait_for_selector("#s-end:not([hidden])", timeout=15000)
        ref1 = phone.inner_text("#end-refnum").strip()
        shot(phone, "p07_ticket", "#s-end", settle=900)
        log("ticket 1:", ref1)

        # ---- Act 3: dashboard
        refresh_dash(dash, "map")
        shot(dash, "d01_newpin", [".vpin:has-text('Khed Shivapur')", "#tlist li:has-text('Khed Shivapur')"])
        dash.locator("#tlist button.trow").first.click()
        dash.wait_for_selector(".drawer")
        shot(dash, "d02_drawer", ".drawer-body section:first-child", settle=900)
        dash.keyboard.press("Escape")
        dash.wait_for_timeout(300)

        # ---- Act 4: engineer
        eng.goto(BASE + "/engineer")
        eng.wait_for_selector("article.job")
        eng.wait_for_load_state("networkidle")
        shot(eng, "e01_queue", "article.job", settle=900)
        eng.locator("article.job", has_text="#" + ref1).locator("button", has_text="Acknowledge").click()
        eng.wait_for_timeout(1200)
        shot(eng, "e02_acked", "article.job")
        eng.locator("article.job", has_text="#" + ref1).locator("button", has_text="Report fix").click()
        eng.wait_for_selector(".sheet")
        shot(eng, "e03_sheet", ".sheet", settle=700)
        eng.locator(".sheet button", has_text="Report fix and request the call").click()
        eng.wait_for_selector("text=Fix reported for #" + ref1)
        shot(eng, "e04_reported", "article.job", settle=600)
        refresh_dash(dash, "map")
        shot(dash, "d03_amber", [".vpin:has-text('Khed Shivapur')", "#tlist li:has-text('Khed Shivapur')"])

        # ---- Act 5: verification, yes
        await_ring(phone)
        shot(phone, "p08_vring", ".device", settle=600)
        phone.click("#btn-answer")
        phone.wait_for_selector("#s-call:not([hidden])")
        phone.evaluate("document.getElementById('auto').checked = false")
        phone.wait_for_function("() => !window.JAPhone.S.busy", timeout=15000)
        shot(phone, "p09_vask", "#caption", settle=900)
        turn(phone, "हो")
        phone.wait_for_selector("#s-end:not([hidden])", timeout=15000)
        shot(phone, "p10_verified", "#s-end", settle=900)
        refresh_dash(dash, "map")
        shot(dash, "d04_green", [".vpin:has-text('Khed Shivapur')", "#tlist li:has-text('Khed Shivapur')"])

        # ---- Act 6: second complaint, fix claimed, caller says no
        phone.click("#btn-home")
        phone.wait_for_timeout(500)
        phone.click("#btn-missed")
        phone.wait_for_selector("#s-ring:not([hidden])", timeout=20000)
        phone.click("#btn-answer")
        phone.wait_for_selector("#s-call:not([hidden])")
        phone.evaluate("document.getElementById('auto').checked = false")
        phone.wait_for_function("() => !window.JAPhone.S.busy", timeout=15000)
        turn(phone, "डोणजे गावात नळाला 2 दिवसांपासून पाणी आलं नाही, 60 घरं")
        answer_followups(phone)
        turn(phone, "हो")
        phone.wait_for_selector("#s-end:not([hidden])", timeout=15000)
        ref2 = phone.inner_text("#end-refnum").strip()
        shot(phone, "p11_ticket2", "#s-end", settle=900)
        log("ticket 2:", ref2)
        eng.goto(BASE + "/engineer")
        eng.wait_for_selector("article.job", timeout=10000)
        eng.locator("article.job", has_text="#" + ref2).locator("button", has_text="Acknowledge").click()
        eng.wait_for_timeout(800)
        eng.locator("article.job", has_text="#" + ref2).locator("button", has_text="Report fix").click()
        eng.locator(".sheet button", has_text="Report fix and request the call").click()
        eng.wait_for_selector("text=Fix reported for #" + ref2)
        await_ring(phone)
        phone.click("#btn-answer")
        phone.wait_for_selector("#s-call:not([hidden])")
        phone.evaluate("document.getElementById('auto').checked = false")
        phone.wait_for_function("() => !window.JAPhone.S.busy", timeout=15000)
        shot(phone, "p12_vask2", "#caption", settle=900)
        turn(phone, "नाही")
        phone.wait_for_selector("#s-end:not([hidden])", timeout=15000)
        shot(phone, "p13_reopened", "#s-end", settle=900)
        refresh_dash(dash)
        shot(dash, "d05_rate", ".figure.lead")
        dash.locator("#tlist button.trow", has_text=ref2).first.click()
        dash.wait_for_selector(".drawer")
        shot(dash, "d06_drawer2", ".drawer-body section:first-child", settle=900)
        dash.keyboard.press("Escape")

        # ---- Synthetic data and evaluation
        dash.click("#btn-demo")
        dash.click("#demo-add")
        dash.wait_for_timeout(1500)
        refresh_dash(dash, "map")
        shot(dash, "d07_full", None)
        dash.goto(BASE + "/metrics")
        dash.wait_for_load_state("networkidle")
        dash.wait_for_timeout(1200)
        shot(dash, "m01_metrics", None)

        json.dump({"moments": moments, "ref1": ref1, "ref2": ref2, "viewport": [VW, VH], "dpr": DPR},
                  open(OUT / "moments.json", "w"), indent=1)
        if errors:
            log("PAGE ERRORS:", errors)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
