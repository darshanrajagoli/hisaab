"""Record the Hisaab demo video by driving the local Streamlit app (replay mode)."""

import json
import re
import sys
import time
from pathlib import Path

from narration import LINES
from playwright.sync_api import sync_playwright

DUR = json.loads((Path(__file__).parent / "voice" / "durations.json").read_text())
GAP = 0.45

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8599"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "video_raw")
W, H = 1920, 1080

OVERLAY_JS = """
() => {
  if (document.getElementById('hz-cap')) return;
  const style = document.createElement('style');
  style.textContent = `
    #hz-cap { position: fixed; left: 50%; bottom: 44px; transform: translateX(-50%);
      max-width: 1500px; padding: 18px 34px; border-radius: 14px;
      background: rgba(13,17,23,0.92); color: #E6EDF3; z-index: 999999;
      font: 600 30px/1.35 'Segoe UI', system-ui, sans-serif; text-align: center;
      box-shadow: 0 8px 30px rgba(0,0,0,.45); border: 1px solid #30363D;
      transition: opacity .35s; opacity: 0; pointer-events: none; }
    #hz-cap b { color: #58A6FF; }
    #hz-card { position: fixed; inset: 0; z-index: 1000000; background: #0D1117;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      color: #E6EDF3; font-family: 'Segoe UI', system-ui, sans-serif;
      transition: opacity .5s; opacity: 0; pointer-events: none; }
    #hz-card .t { font-size: 110px; font-weight: 800; letter-spacing: -2px; }
    #hz-card .s { font-size: 40px; color: #8B949E; margin-top: 8px; }
    #hz-card .l { font-size: 30px; color: #58A6FF; margin-top: 10px; }
    #hz-card .bars { display: flex; gap: 14px; align-items: flex-end; height: 120px; margin-bottom: 30px; }
    #hz-card .bars div { width: 34px; border-radius: 6px; }
  `;
  document.head.appendChild(style);
  const cap = document.createElement('div'); cap.id = 'hz-cap'; document.body.appendChild(cap);
  const card = document.createElement('div'); card.id = 'hz-card'; document.body.appendChild(card);
  // Sync marker: flips color at each narration cue so the muxer can find
  // cues in the actual frames (the recording drops frames under load).
  const mk = document.createElement('div'); mk.id = 'hz-mk';
  mk.style.cssText = 'position:fixed;left:0;top:0;width:12px;height:12px;z-index:1000001;background:#000';
  document.body.appendChild(mk);
}
"""


def caption(page, html):
    page.evaluate(OVERLAY_JS)
    page.evaluate(
        """(h) => { const c = document.getElementById('hz-cap');
                     if (!h) { c.style.opacity = 0; return; }
                     c.innerHTML = h; c.style.opacity = 1; }""",
        html,
    )


def card(page, html):
    page.evaluate(OVERLAY_JS)
    page.evaluate(
        """(h) => { const c = document.getElementById('hz-card');
                     if (!h) { c.style.opacity = 0; return; }
                     c.innerHTML = h; c.style.opacity = 1; }""",
        html,
    )


BARS = (
    '<div class="bars"><div style="height:50px;background:#F85149"></div>'
    '<div style="height:80px;background:#8B949E"></div>'
    '<div style="height:65px;background:#58A6FF"></div>'
    '<div style="height:120px;background:#3FB950"></div></div>'
)


def nav(page, label):
    page.get_by_text(label, exact=True).first.click()
    page.wait_for_timeout(2500)


def pick_tip(page, prefix):
    """Choose a tip in the Tip Detail combobox by its label prefix."""
    try:
        box = page.get_by_role("combobox", name="Select tip")
        box.click(timeout=5000)
        # The option list is virtualized; typing filters it so the target renders.
        box.fill(prefix)
        page.wait_for_timeout(600)
        page.get_by_role("option", name=re.compile("^" + re.escape(prefix))).first.click(timeout=5000)
        page.wait_for_timeout(2500)
    except Exception as exc:  # selector drift shouldn't kill the take
        print("tip pick skipped:", prefix, exc)
        page.keyboard.press("Escape")


def smooth_scroll(page, total, steps=40, pause=60):
    for _ in range(steps):
        page.mouse.wheel(0, total / steps)
        page.wait_for_timeout(pause)


MARKER_COLORS = ["#FF0000", "#00FF00", "#0000FF"]


class Timeline:
    def __init__(self, page):
        self.page = page
        self.t0 = time.time()
        self.events = []
        self.until = 0.0

    def now(self):
        return time.time() - self.t0

    def _flip(self):
        color = MARKER_COLORS[len(self.events) % len(MARKER_COLORS)]
        self.page.evaluate(OVERLAY_JS)
        self.page.evaluate("(c) => { document.getElementById('hz-mk').style.background = c; }", color)

    def mark(self, name):
        if name != "start":  # same instant as the first cue; derived from it
            self._flip()
        self.events.append({"key": name, "t": self.now()})

    def say(self, key, block=True, show_caption=True):
        """Start narration line `key` now; caption it; optionally wait until it ends."""
        self.wait()
        self._flip()
        self.events.append({"key": key, "t": self.now()})
        if show_caption:
            caption(self.page, LINES[key])
        self.until = time.time() + DUR[key] + GAP
        if block:
            self.wait()

    def wait(self):
        left = self.until - time.time()
        if left > 0:
            self.page.wait_for_timeout(int(left * 1000))


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(OUT),
            record_video_size={"width": W, "height": H},
            color_scheme="dark",
        )
        page = ctx.new_page()
        tl = Timeline(page)
        page.goto(URL)
        page.get_by_text("Run Audit").wait_for(timeout=90000)
        page.wait_for_timeout(2000)
        page.mouse.move(W - 50, H - 50)

        # Title card (narrated, no caption)
        card(page, BARS + '<div class="t">Hisaab</div>'
             '<div class="s">hisaab keeps the receipts</div>'
             '<div class="l" style="margin-top:40px;color:#8B949E">'
             'Grading Indian finfluencer stock tips against the market</div>')
        page.wait_for_timeout(700)
        tl.mark("start")
        tl.say("title", show_caption=False)
        card(page, None)
        page.wait_for_timeout(500)

        tl.say("hook")
        tl.say("insight")

        tl.say("run_intro", block=False)
        page.wait_for_timeout(int(DUR["run_intro"] * 1000) - 1200)
        page.get_by_role("button", name="Run Audit").click()
        tl.say("run_a", block=False)
        page.get_by_text("Audit complete!").first.wait_for(timeout=180000)
        tl.wait()
        tl.say("run_b", block=False)
        smooth_scroll(page, 900, steps=60, pause=120)
        tl.say("run_c")

        caption(page, None)
        nav(page, "📊 Scorecard")
        page.mouse.move(W - 50, H - 50)
        tl.say("score1")
        tl.say("score2")
        tl.say("score3", block=False)
        smooth_scroll(page, 550)
        tl.say("score4", block=False)
        smooth_scroll(page, 600)
        tl.say("score5", block=False)
        smooth_scroll(page, 900)
        tl.wait()

        caption(page, None)
        nav(page, "🔍 Tip Detail")
        pick_tip(page, "BEL —")
        page.mouse.move(W - 50, H - 50)
        tl.say("tip1")
        tl.say("tip2", block=False)
        smooth_scroll(page, 750)
        tl.wait()
        smooth_scroll(page, -1500, steps=15, pause=30)
        pick_tip(page, "HINDCOPPER —")
        page.mouse.move(W - 50, H - 50)
        tl.say("tip3", block=False)
        page.wait_for_timeout(2500)
        smooth_scroll(page, 750, steps=30)
        tl.wait()

        caption(page, None)
        nav(page, "📐 Methodology")
        page.mouse.move(W - 50, H - 50)
        tl.say("method1")
        tl.say("method2", block=False)
        smooth_scroll(page, 1400, steps=50, pause=90)
        tl.wait()

        caption(page, None)
        card(page, BARS + '<div class="t">Hisaab</div>'
             '<div class="s">5 SerpApi engines · deterministic scoring · every tip has a receipt</div>'
             '<div class="l" style="margin-top:40px">github.com/darshanrajagoli/hisaab</div>'
             '<div class="l">hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app</div>'
             '<div class="s" style="font-size:28px;margin-top:36px">Built for the SerpApi India '
             'Hackathon 2026 · Educational only, not investment advice</div>')
        page.wait_for_timeout(600)
        tl.say("end", show_caption=False)
        page.wait_for_timeout(1500)
        tl.mark("stop")
        page.wait_for_timeout(600)  # let the stop marker reach a recorded frame

        video_path = page.video.path()
        ctx.close()
        browser.close()
        (OUT / "timeline.json").write_text(json.dumps({"video": str(video_path), "events": tl.events}, indent=1))
        print("VIDEO", video_path, "length", tl.events[-1]["t"] - tl.events[0]["t"])


if __name__ == "__main__":
    main()
