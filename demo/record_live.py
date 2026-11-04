#!/usr/bin/env python3
"""Record a demo video of the LIVE public AgentRush deployment.

Opens http://<host>/ in a fresh Playwright browser (video on), injects a
banner naming the public URL + VM, runs a real task through the web UI,
and lingers on the rendered record. Output: demo/live_run.webm (+mp4).
"""
import sys
import time
from playwright.sync_api import sync_playwright

HOST = sys.argv[1] if len(sys.argv) > 1 else "108.61.171.235"
BASE = f"http://{HOST}:8080"
OUT_DIR = "demo/_vid"

TASK = ("Fetch https://example.com, summarise what the page says in one "
        "sentence, and compute the sha256 of the page body.")

BANNER = """
(() => {
  const b = document.createElement('div');
  b.textContent = 'LIVE demo — public deployment on Vultr VM (fra): ' + location.origin;
  b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;' +
    'background:#0d2818;color:#8fd6a4;padding:8px 14px;font:600 14px system-ui;' +
    'border-bottom:2px solid #2a5a3a;text-align:center';
  document.body.prepend(b);
  document.body.style.paddingTop = '44px';
})();
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False,
                                args=["--window-position=0,0"])
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        record_video_dir=OUT_DIR, record_video_size={"width": 1280, "height": 900})
    page = ctx.new_page()

    # 1. landing page with injected "live" banner
    page.goto(BASE, wait_until="domcontentloaded")
    page.evaluate(BANNER)
    time.sleep(4)

    # 2. type the task + run
    page.fill("#task", TASK)
    time.sleep(1.5)
    page.click("#go")
    page.wait_for_selector(".rec", timeout=120_000)
    time.sleep(2)

    # 3. linger on the record, scroll the raw JSON, then a second run
    page.evaluate("document.querySelector('details').open = true")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(4)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    # 4. second task — fetch + compute, shown as fresh contained run
    page.fill("#task", "Fetch https://example.com and count how many "
                       "times the word 'example' appears in the body.")
    time.sleep(1)
    page.click("#go")
    time.sleep(3)  # let out.innerHTML clear so the wait below is meaningful
    page.wait_for_selector(".rec", timeout=120_000)
    time.sleep(5)

    ctx.close()
    browser.close()
print("done — video in", OUT_DIR)
