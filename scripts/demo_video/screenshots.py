"""Capture README screenshots from the local app after a replay run."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1]
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1000}, color_scheme="dark")
    page.goto(URL)
    page.get_by_role("button", name="Run Audit").wait_for(timeout=90000)
    page.get_by_role("button", name="Run Audit").click()
    page.get_by_text("Audit complete!").first.wait_for(timeout=180000)

    page.get_by_text("📊 Scorecard", exact=True).first.click()
    page.wait_for_timeout(7000)
    page.screenshot(path=str(OUT / "scorecard.png"))

    page.get_by_text("🔍 Tip Detail", exact=True).first.click()
    page.wait_for_timeout(5000)
    page.screenshot(path=str(OUT / "tip_detail.png"))
    b.close()
print("ok")
