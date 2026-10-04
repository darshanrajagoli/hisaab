# Hisaab — SerpApi India Hackathon 2026 submission (copy-paste)

**Project name:** Hisaab

**Track:** Commerce & Market Intelligence

**Public GitHub repository:** https://github.com/darshanrajagoli/hisaab

**Demo video:** <VIDEO_URL>

## Project description

Hisaab grades Indian finfluencer stock tips against what the market actually did.

Millions of new retail investors in India act on stock calls from Hindi, Hinglish and English YouTube channels — "buy X, target ₹850, stop-loss ₹690". Nobody keeps score: winners get re-shared in thumbnails, losers are quietly forgotten, and SEBI's 2024 crackdown on unregistered advice hasn't given investors any way to check a creator's record.

Hisaab treats every tip as a timestamped, falsifiable prediction. Paste a channel handle and it:
1. finds the creator's tip videos and their exact publish dates,
2. reads the transcripts (Hindi/Hinglish/English) and extracts every stock call — company, direction, target, stop-loss, horizon — with the exact second it was said,
3. verifies each quote back against the transcript (fuzzy match + LLM check) so nothing is hallucinated, and resolves names to NSE tickers (2,300+ listed equities),
4. scores each call deterministically against real daily closes: on the creator's own terms (target vs stop-loss hit first) and on market terms (excess return vs the NIFTY 50 over identical dates),
5. reports hit rate with a Wilson confidence interval, bootstrap CI on excess return, a binomial test against a coin flip, a "do 'guaranteed multibagger' calls do better?" conviction analysis, and a ₹10,000-per-tip portfolio vs NIFTY.

Every number is computed by auditable Python — the LLM only reads, it never does the arithmetic. Every tip links to a YouTube player cued to the exact second it was said, so anyone can check the receipt. Unscored tips (F&O, intraday, unresolved, not yet matured) are shown, not hidden, and the limitations (survivorship and selection bias, close-only prices, ASR errors) are documented in-app.

Who it's for: retail investors deciding whom to trust, journalists and researchers studying finfluencers, and honest creators who want a verifiable track record.

Try it: live app https://hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app — click "Run Audit" (Replay mode replays a real recorded audit with zero API keys), or run it locally with `pip install -e . && hisaab audit @RakeshBansal --replay demo`. CLI + Streamlit UI, 60+ tests, CI on every push.

## How the project uses SerpApi

SerpApi is the entire data backbone — five engines, each doing a job nothing else in the stack does (official `google-search-results` Python SDK):

- **YouTube Channel API** (`youtube_channel`, `channel_id` = @handle, `search_query`) — within-channel search with tip keywords to discover candidate videos, plus channel identity. ~2 calls/audit.
- **YouTube Video API** (`youtube_video`, `v`) — exact publish date, which anchors every trade's entry (first close strictly after publication), plus title/description/views. 1 call/video.
- **YouTube Video Transcript API** (`youtube_video_transcript`, `v`, `language_code`) — the spoken words with millisecond timestamps. This is where the tips live, and the timestamps power "jump to the exact second" receipts. 1 call/video.
- **Google Finance API** (`google_finance`, `q=TICKER:NSE`, `window`) — daily closing price history for every resolved stock and the NIFTY 50 benchmark; one call per unique ticker, window chosen to cover the oldest tip. Scoring is computed entirely from this.
- **Google News API** (`google_news`, `q`, `gl=in`) — news context explaining the biggest wins and losses.

Engineering around SerpApi: a persistent SQLite cache (transcripts/metadata cached forever, prices/news 24h), a budget governor enforcing per-run and monthly caps before any call, SerpApi's own cache respected (no `no_cache`), and a replay mode that serves recorded SerpApi responses so judges can reproduce a full real audit with zero keys. A typical 10-video audit costs ~35–50 searches. Every field mapping was verified against live responses (e.g. `youtube_channel` videos live in `search_results` filtered by `type`; transcript `start_ms` is already milliseconds).

## AI tools used

Claude (Anthropic, via Claude Code) for code generation, architecture, debugging, documentation, and producing the demo video (scripted browser recording + text-to-speech narration). Google Gemini (gemini-3.1-flash-lite) is used inside the product to classify video titles, extract structured tips from transcripts, and cross-check quotes. All scoring and statistics are deterministic Python, not AI.

## Other form fields (fill yourself)

- Lead participant name: Darshan Rajagoli
- Email: <your email>
- Mobile number: <your number>
- Occupation: Student
- Years of experience: 0
- How did you hear about the hackathon: <your answer>
- Pre-existing project checkbox: built new for this hackathon (first commit Sep 18, 2026, during the hackathon window Sep 1 – Oct 10)
- Tick: link tested in incognito, rules, terms
