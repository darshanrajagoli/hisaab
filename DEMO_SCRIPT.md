# Hisaab — Recording Script & Editor Brief

Target length: **2:45–3:15**. Written so you (Darshan) only need to press
record and follow the clicks — and so you can hand this whole file, plus
your raw footage, to a video editor (human or AI) with zero extra context.

---

## Part A — What YOU do before recording

### 1. Open exactly these two things
1. **Browser tab:** `https://hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app`
   (this is the live, hosted app — nothing to install, just this URL)
2. **A second browser tab:** `https://github.com/darshanrajagoli/hisaab`
   (for the 3-second repo glance in the close)

That's it. You do not need a terminal, VS Code, or anything local — the
whole recording happens in a browser, on the hosted app.

### 2. Check the app is actually working right now
Load the app URL. You should see the sidebar with **🏠 Home / 📊 Scorecard
/ 🔍 Tip Detail / ⚖️ Compare / 📐 Methodology**, and a "💰 API Budget" box
on the Home page showing real numbers (not an error). If you see a Google
login prompt first, click through it — that's normal, that's Streamlit's
own platform login, not part of the app.

### 3. Do ONE full test run before you hit record
On Home: paste `@RakeshBansal`, set "Max videos" to 10, leave Mode on
**Live**, click **Run Audit**. Watch what happens:

- **If it finishes with tips scored (a real number, not 0):** great, you
  have real data — go to Scorecard, confirm it looks populated, and
  record for real using this exact same run (click Run Audit again on
  camera, or screen-record the already-populated Scorecard/Tip Detail
  pages directly — either is fine, see Shot 3 below).
- **If it finishes with "0 tips scored":** this means Gemini's free daily
  quota is currently exhausted (a known, expected limitation, not a bug —
  see README Limitations). **Don't record the live run today.** Instead:
  wait for a day where quota is fresh (early in the day, before other
  usage), run the test again first thing, and only start recording once
  you've confirmed a real scored result. Recording an empty scorecard
  live would be the single worst thing to put in this video.

This test-first step is the most important instruction in this whole
document. Everything below assumes you already have a working, scored
run to show.

---

## Part B — Shot-by-shot script

Say the lines out loud as you record, in your own voice. Text in
`[brackets]` is a stage direction, not something you say.

### Shot 1 — Hook (0:00–0:15)
`[Screen: Home page, before clicking anything]`

> "Indian finfluencers give thousands of stock tips on YouTube. Nobody
> grades them. Winners get reshared in thumbnails, losers get forgotten.
> Hisaab finds every tip, timestamps the exact second it was said, and
> grades it against what the stock actually did — versus the NIFTY 50."

### Shot 2 — The insight (0:15–0:30)
`[Screen: still Home page]`

> "A stock tip is a falsifiable prediction with a timestamp. The
> transcript has the words, the video metadata has the time, market data
> has the outcome. All three are search data — SerpApi is the entire
> backbone here: five of their engines, doing real work."

### Shot 3 — The run (0:30–1:30) — the centerpiece
`[Screen: Home page → click into the "YouTube Channel or Video URL" box]`

- Type `@RakeshBansal` (or whichever channel you validated in Part A.3).
- Click **🚀 Run Audit**.
- While it's running, the app prints each pipeline stage live
  (discover → select → metadata → transcripts → extract → verify →
  resolve → prices → corporate_actions → score → stats → explain). Let
  the camera sit on this for a few seconds, then narrate over it:

> "Discover pulls every video from the channel through SerpApi's YouTube
> engine. Transcripts come in per video. An LLM reads each transcript
> window and extracts structured tips — company, direction, target, stop
> loss. Every tip gets fuzzy-matched back against the transcript so
> nothing's hallucinated. Tickers get resolved to real NSE symbols, and
> then it's pure math: real closing prices from Google Finance, scored
> against what was actually said."

- When it finishes, click through to **📊 Scorecard**.

### Shot 4 — Scorecard (1:30–1:50)
`[Screen: Scorecard page]`

Point the cursor at, in this order:
1. **Scored Tips** number
2. **Hit Rate (vs NIFTY)** with its confidence interval
3. **Conviction Analysis** section (if it has data — this is one of the
   most interesting findings the tool can produce)
4. The **₹10,000/tip Portfolio vs NIFTY 50** chart

> "This is the whole pitch on one screen. Hit rate against the actual
> index, not against zero. A confidence interval, because ten tips and a
> thousand tips shouldn't look equally certain. And conviction analysis —
> does 'guaranteed multibagger' actually perform differently than an
> ordinary call?"

### Shot 5 — Tip Detail: the proof (1:50–2:35)
`[Screen: click 🔍 Tip Detail in the sidebar, pick any scored tip from the dropdown]`

This is the screen that makes the whole thing credible — don't rush it.

- Point at the embedded YouTube player and say the tip jumps to the exact
  second it was said — then actually **press play on it** for 2–3
  seconds so the viewer sees real video, not a mockup.
- Point at the original-language quote and its English translation.
- Point at the price chart: entry marker, exit marker, target/stop-loss
  lines if present.

> "Every number traces back to this — a real timestamp in a real video
> you can click and verify yourself. That's the difference between a
> claim and a receipt."

### Shot 6 — Methodology (2:35–2:50)
`[Screen: 📐 Methodology page, slow scroll]`

> "Every score on this scorecard is deterministic Python — the LLM only
> reads the transcript, it never touches the arithmetic. And the
> limitations are stated up front, not hidden — things like survivorship
> bias and selection bias that most tools like this would just not
> mention."

### Shot 7 — Close (2:50–3:05)
`[Screen: switch to the GitHub repo tab for 2 seconds, then back to the app]`

> "Built solo for the SerpApi India Hackathon 2026. Five SerpApi engines
> doing real work, fully hosted, one click to try it yourself. Hisaab
> keeps the receipts."

`[Hold on the Home page or a title card for the last second]`

---

## Part C — Brand kit (for on-screen text / title cards / end card)

If your editor adds title cards, lower-thirds, or an end card, use this
so it matches `social_preview.png` (already in the repo root) and the
app's own dark theme:

- **Name:** Hisaab (always lowercase tagline, capitalized name)
- **Tagline:** "hisaab keeps the receipts"
- **Palette:** near-black background `#0D1117`, panel `#1E242C`, text
  white `#E6EDF3`, dim gray `#8B949E`, accent blue `#58A6FF`, accent green
  `#3FB950`, accent red `#F85149`
- **Font style:** bold sans-serif for titles (the app/preview image use
  Segoe UI Bold) — any clean geometric sans works if that's unavailable
- **Icon:** a simple 4-bar bar-chart glyph (see `social_preview.png` for
  the exact shape/colors) — no emoji, they don't render consistently
- **End card must include:**
  - Live demo: `hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app`
  - Repo: `github.com/darshanrajagoli/hisaab`
  - "Built for the SerpApi India Hackathon 2026"

---

## Part D — Instructions for whoever edits this (human or AI)

1. **Source material** is one continuous screen recording plus voiceover,
   following the shots above in order. Cut between shots on the
   stage-direction boundaries (`0:00–0:15`, etc.) — those timestamps are
   targets, not hard cuts; trim dead air and long load times (e.g. LLM
   calls take ~15–20s each — speed up or cut that waiting, don't leave it
   real-time).
2. Add **lower-third captions** for each shot using the spoken lines
   above as the caption text (viewers often watch muted).
3. Add a **title card** at 0:00 (Hisaab name + tagline, brand kit above)
   and an **end card** at the very end (Part C's end card contents),
   each held for ~2 seconds.
4. Background music: optional, low-key/corporate, should duck under the
   voiceover, not compete with it.
5. Do not add any sound effect, transition, or caption implying real-time
   guaranteed returns, investment advice, or endorsement of any stock —
   this project is explicitly framed as educational/analytical, and nothing
   in the edit should undercut that framing.
6. Final export: 1920x1080, mp4, under the hackathon's stated size/length
   limit if one exists (check the submission page — not something this
   repo tracks).

---

## Part E — If something goes wrong on the day

- **Empty scorecard live:** stop, don't record it. See Part A.3 — this
  means Gemini's daily quota is exhausted; try again another time of day.
- **"insufficient evidence" banner:** you're on a channel/run with too
  few scored tips (<10). Use a channel you've already validated has
  enough, don't gamble on a fresh one during the take.
- **App itself won't load / shows a Streamlit error page:** the hosted
  app may be asleep (Streamlit Community Cloud free tier sleeps after
  inactivity) — reload once, wait ~30 seconds for it to wake up, then
  proceed. This is normal, don't panic-cut the recording.
- **Slow LLM calls during Shot 3:** expected on the free tier — either
  let the editor speed up that segment, or cut to Scorecard on an
  already-completed run instead of waiting live.
