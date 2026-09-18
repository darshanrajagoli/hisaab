# Hisaab — Demo Recording Script

~3 minutes. Record in this order.

## 0. Before you hit record
- `git pull` to get the latest fixes.
- `streamlit run app/app.py` running locally, browser tab ready on Home.
- Have a terminal tab ready too (for the CLI moment below).
- Know your one-liner: **"Hisaab keeps the receipts on YouTube stock tips."**

## 1. Hook (15s)
Say it straight to camera or over the Home screen:
> "Indian finfluencers give thousands of stock tips on YouTube. Nobody grades them.
> Winners get reshared in thumbnails, losers get forgotten. Hisaab finds every tip,
> timestamps the exact second it was said, and grades it against what the stock
> actually did — versus the NIFTY 50."

## 2. The insight (15s)
> "A stock tip is a falsifiable prediction with a timestamp. The transcript has the
> words, the video metadata has the time, market data has the outcome. All three are
> search data — SerpApi is the entire backbone here."

## 3. Live run (60–90s) — the centerpiece
- On Home, paste a channel handle, hit **Run Audit**.
- While it runs, narrate the pipeline out loud as stages tick by in the terminal/log:
  discover → transcripts → LLM extraction → verify → resolve tickers → price fetch →
  score → stats.
- Land on the **Scorecard** page. Point at: hit rate vs NIFTY, the confidence interval,
  the ₹10,000/tip simulation chart.

## 4. Tip Detail — the proof (45s)
This is the screen that makes the whole pitch credible. Click into one tip:
- The embedded YouTube player jumps to the **exact second** the tip was said.
- Point at the verbatim quote (original + English).
- Point at the price chart: entry marker, exit marker, target/stop-loss lines.
- Say: "Every number traces back to this — a timestamp you can click and verify."

## 5. Methodology page (15s)
Quick scroll-through. Say: "Every score is deterministic Python, not the LLM — the
LLM only reads, Python judges. And the limitations are stated up front, not hidden."

## 6. Close (15s)
> "Built solo for the SerpApi India Hackathon, five SerpApi engines doing real work,
> replay mode so you can run this yourself with zero API keys. Hisaab keeps the
> receipts."

---

## If something breaks live
- **Empty scorecard**: switch the Mode toggle to Replay and re-run — it uses the
  bundled fixtures for the SerpApi side (YouTube/Finance/News), zero network calls
  needed for those. NOTE: the LLM (Gemini) side of replay isn't cached yet, so a
  replay run will fail loudly at extraction unless you've already run this exact
  channel live once this session (which populates `hisaab_llm_cache.db` locally).
  Don't rely on Replay as an on-camera save unless you've verified it works on
  your machine beforehand — pre-flight it, don't discover it live.
- **Slow LLM calls**: this is expected on the free tier (~20s/window) — cut it in
  editing, don't wait live.
- **"insufficient evidence" banner**: pick a channel/run you've already validated
  locally beforehand; don't gamble on a fresh channel during the recording.

## What NOT to demo live
- Don't run against Gemini live on camera without a pre-flight check that the daily
  quota isn't already spent (`python -c "from hisaab.llm import call_llm; print(call_llm('hi', max_tokens=5))"`
  — if that errors with `RESOURCE_EXHAUSTED`, use Replay mode for the recording instead).
