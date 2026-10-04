"""
Visit the hosted demo so Streamlit Community Cloud doesn't put it to sleep.

Free-tier apps sleep after a stretch without visitors, and a sleeping app
greets the next visitor with a "wake it back up?" page. Run on a schedule by
.github/workflows/keep-awake.yml; wakes the app if it's already asleep.
"""

from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

URL = "https://hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, timeout=90000)
        deadline = time.time() + 300
        while time.time() < deadline:
            if any(fr.get_by_role("button", name="Run Audit").count() for fr in page.frames):
                print("app is up")
                browser.close()
                return 0
            wake = page.get_by_role("button", name="Yes, get this app back up!")
            if wake.count():
                print("app was asleep — waking it")
                wake.click()
            page.wait_for_timeout(5000)
        browser.close()
    print("app did not come up within 5 minutes")
    return 1


if __name__ == "__main__":
    sys.exit(main())
