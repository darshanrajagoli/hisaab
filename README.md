# 📊 Hisaab — Grade Indian Finfluencer Stock Tips

[![CI](https://github.com/darshanrajagoli/hisaab/actions/workflows/ci.yml/badge.svg)](https://github.com/darshanrajagoli/hisaab/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Built with SerpApi](https://img.shields.io/badge/built%20with-SerpApi-000000.svg)](https://serpapi.com)

> **hisaab keeps the receipts.**

**🔴 [Live Demo](https://hisaab-ccb6uxs8tjolxrzvcvpkoc.streamlit.app)** — no install needed, just click.

Every stock tip on YouTube is a timestamped prediction. Hisaab finds each tip in a creator's videos, records the exact second it was said, and grades it against what the stock actually did afterwards — compared to the NIFTY 50. The output is a verifiable scorecard.

---

## The Problem

India has a massive ecosystem of Hindi, Hinglish, and English YouTube channels giving specific stock calls — "buy X, target ₹850, stop loss ₹690, 3-month view." Millions of new retail investors act on these calls. **Nobody keeps score.**

Creators re-share their winners in thumbnails and titles. The losers are quietly forgotten. Viewers only see the survivors.

In June 2024, SEBI barred regulated entities from associating with anyone who gives securities advice without SEBI's permission. Yet a retail investor today has **no public, evidence-based way** to check whether a creator's calls actually made money.

## The Insight

A stock tip is a **falsifiable prediction** with a timestamp. The creator's own words are in the video transcript. The time they said it is in the video metadata. The outcome is in market price history.

**All three are available as search data.** Grading a creator doesn't need their cooperation, a broker integration, or any private data. It only needs SerpApi plus careful processing.

## How It Works

```
Channel URL → Discover Videos → Classify → Select Top N
    → Fetch Transcripts → Window & Pre-filter
    → LLM Extract Tips → Verify (fuzzy + LLM) → Resolve Tickers
    → Fetch Prices → Score Deterministically → Statistics → Scorecard
```

**The LLM reads. Python judges.** Every number on the scorecard — returns, hit rates, confidence intervals, p-values — comes from deterministic Python code that can be audited and reproduced; the LLM never touches that arithmetic. It's still upstream of the sample, though: the LLM also decides which videos look tip-worthy, extracts what counts as a tip in the first place, and cross-checks tips against the transcript — so its judgment shapes *what gets scored*, even though it never computes *the score itself*.

---

## Quickstart

### Replay Mode (No API Key Needed)

Judges and reviewers can run the full app immediately, with zero network
calls, against the bundled fixture bundle for `@RakeshBansal`:

```bash
git clone https://github.com/darshanrajagoli/hisaab.git
cd hisaab
pip install -e .

# CLI
hisaab audit @RakeshBansal --replay demo

# Web UI — pick "Replay" mode in the sidebar, then Run Audit
streamlit run app/app.py
```

**Current limitation:** the fixture bundle covers the five SerpApi engines
(YouTube, Google Finance, Google News) but does not yet ship a cached set
of LLM (Gemini) responses — that half of replay mode still needs a
successful live run to populate. Right now a fresh clone's replay run will
fail loudly with `ReplayFixtureMissing` at the tip-extraction stage rather
than silently returning an empty scorecard (that loud failure is
deliberate — see Limitations). Live mode with your own `GEMINI_API_KEY`
and `SERPAPI_API_KEY` is the reliable path until an LLM fixture cache
ships.

### Live Mode

```bash
cp .env.example .env
# Edit .env with your API keys:
# SERPAPI_API_KEY=your_key
# GEMINI_API_KEY=your_key

# CLI
hisaab audit @channel_handle

# Web UI
streamlit run app/app.py
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Deployment (Streamlit Community Cloud)

The hosted demo above is a free Streamlit Community Cloud app pointed at
this repo:

1. [share.streamlit.io](https://share.streamlit.io) → **New app** → pick
   this GitHub repo, branch `main`, main file path `app/app.py`.
2. In the app's **Settings → Secrets**, paste:
   ```toml
   SERPAPI_API_KEY = "your_key"
   GEMINI_API_KEY = "your_key"
   ```
   (`app/app.py` bridges `st.secrets` into `os.environ` on startup, so
   nothing else needs to change — the same code path as a local `.env`.)
3. Deploy. Judges can then run a Live audit with no setup on their end;
   your keys are the only ones spent.

---

## How Hisaab Uses SerpApi

SerpApi is the **backbone** of Hisaab. Without it, there is no transcript, no timestamp, and no price history — so there is no product.

| Engine | Parameters Used | Response Fields Consumed | Why It's Essential | Calls/Audit |
|--------|----------------|------------------------|-------------------|-------------|
| `youtube_channel` | `channel_id` (accepts `@handle` directly), `search_query` | `search_results[]` (`type=="video"`: video_id, title, extracted_views, published_date), `channel_results` (external_id, title, handle) | Discovers tip videos via within-channel search with tip keywords | ~2 |
| `youtube_video` | `v` (video_id) | `title`, `channel`, `published_date`, `description`, `extracted_views` | Gets exact publish date — the timestamp that anchors every trade | ~1 per selected video |
| `youtube_video_transcript` | `v` (video_id), `language_code` | `transcript[]` (`snippet`, `start_ms`) | **Core engine.** Extracts the spoken words + millisecond timestamps. This is where tips live. | ~1 per selected video |
| `google_finance` | `q` (ticker:NSE), `window`, `gl=in` | `graph[]` (price, date, volume), `summary` | Price history to score every tip. One call per unique ticker, not per tip. | ~1 per unique ticker + 1 for NIFTY |
| `google_news` | `q` (company name + "stock"), `gl=in` | `news_results[]` (title, source, link, date) | Explains the top wins and losses — turns numbers into stories | ~3–6 |

Every field mapping above was verified against real, live SerpApi responses during development — not assumed from docs. See commit history for the specific mismatches this caught (e.g. `youtube_channel`'s video list actually lives in `search_results` filtered by type, not a `videos` key; transcript `start_ms` is already in milliseconds, not seconds as first assumed).

### Caching & Budget

- **Persistent SQLite cache** — transcripts and video details cached forever (immutable data), prices and news cached for 24 hours
- **Budget governor** — enforces per-run and monthly caps, raises `BudgetExceeded` before any over-limit call
- **Replay mode** — `HISAAB_MODE=replay` reads from a fixture bundle with zero network calls
- SerpApi's own 1-hour cache is respected (`no_cache` is never used)

Typical audit: **~35 searches** per channel. Free plan (250/month) supports ~7 full audits.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      User Input                         │
│              (Channel URL / Video URL)                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│                  SerpApi Client Layer                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │  Cache    │ │  Budget  │ │  Replay  │ │  Retries   │ │
│  │ (SQLite)  │ │ Governor │ │ Fixtures │ │  Backoff   │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌────────────┐ ┌──────────┐ ┌──────────┐
   │  YouTube   │ │  Google  │ │  Google  │
   │ Channel +  │ │ Finance  │ │  News    │
   │ Video +    │ │          │ │          │
   │ Transcript │ │          │ │          │
   └─────┬──────┘ └────┬─────┘ └────┬─────┘
         │             │            │
         ▼             │            │
┌────────────────┐     │            │
│   Pipeline     │     │            │
│ ┌────────────┐ │     │            │
│ │  Windows   │ │     │            │
│ │  + Filter  │ │     │            │
│ └─────┬──────┘ │     │            │
│       ▼        │     │            │
│ ┌────────────┐ │     │            │
│ │  LLM       │ │     │            │
│ │  Extract   │ │     │            │
│ │  + Verify  │ │     │            │
│ └─────┬──────┘ │     │            │
│       ▼        │     │            │
│ ┌────────────┐ │     │            │
│ │  Resolve   │◄┼─────┘            │
│ │  Tickers   │ │                  │
│ └─────┬──────┘ │                  │
│       ▼        │                  │
│ ┌────────────┐ │                  │
│ │  Score     │ │                  │
│ │  (Python)  │ │                  │
│ └─────┬──────┘ │                  │
│       ▼        │                  │
│ ┌────────────┐ │                  │
│ │ Statistics │ │                  │
│ │  Wilson CI │ │                  │
│ │ Bootstrap  │ │                  │
│ │  Binomial  │ │                  │
│ └─────┬──────┘ │                  │
│       ▼        │                  │
│ ┌────────────┐ │                  │
│ │  Explain   │◄┼──────────────────┘
│ └────────────┘ │
└───────┬────────┘
        ▼
┌────────────────┐
│   Scorecard    │
│  CLI + Web UI  │
└────────────────┘
```

---

## Scoring Methodology

### Entry Rule
The entry price is the closing price on the **first trading day strictly after** the video's publish date. This avoids using information the viewer couldn't have had.

If the creator stated a specific entry price, the tip only counts as "triggered" if the close reaches within 2% of that stated entry within 5 trading days. Otherwise: `NOT_TRIGGERED`. Either way, scoring always uses the actual next-day close as the entry price — the stated entry is only a trigger gate, never the price used for return math.

### Horizon Rule
The horizon is a fixed default per bucket, not a free-text parse of the
creator's exact words (e.g. "3 months") — the LLM extracts that phrase as
`stated_horizon_text` for display/audit, but scoring uses the bucket default:

| Horizon Bucket | Trading Days |
|---------------|-------------|
| Swing | 10 |
| Positional | 60 |
| Long-term | 250 |
| Unspecified | 60 |

### Outcome — Creator's Terms
Walk the close series from entry to horizon:
- **TARGET_HIT**: Target reached before stop loss
- **STOP_HIT**: Stop loss reached before target
- **EXPIRED**: Neither reached by horizon end

Only closing prices are used — intraday touches not counted.

### Outcome — Market Terms
- **Stock Return**: (exit − entry) / entry (sign flipped for SHORT/AVOID)
- **NIFTY Return**: NIFTY 50 return over identical dates
- **Excess Return**: Stock Return − NIFTY Return

### Statistical Analysis
- **Hit Rate**: Wilson 95% confidence interval
- **Mean Excess Return**: Bootstrap 95% CI (10,000 resamples, fixed seed)
- **Significance**: Two-sided binomial test against 50% coin flip
- **₹10,000/tip Simulation**: Equal-weight portfolio vs NIFTY over same dates
- **Conviction Analysis**: Hit rate for "guaranteed"/"multibagger" calls vs regular

### Unscored Categories (shown, not hidden)
- INTRADAY, F&O, IPO, Mutual Fund, Crypto
- Unresolved tickers
- Corporate action flags (>35% move in a single price-series period —
  a trading day on short windows, a full week on the 5Y window)
- Not triggered, Open (horizon not elapsed)

### Limitations
- Only closing prices available (not intraday highs/lows)
- Auto-generated transcripts may have errors, especially in Hinglish
- F&O calls are out of scope — strike, expiry, and premium data unavailable
- Entry timing assumes next-day close; real viewers may enter differently
- HOLD and WATCHLIST calls are scored as full long positions in the
  ₹10,000/tip simulation (only SHORT/AVOID flip the return sign) — a
  "keep this on your watchlist" mention gets a real P&L entry
- Tips whose price window contains a >35% single-period move are excluded
  from scoring entirely. This is meant to filter split/bonus distortions,
  but it also excludes genuine crashes (fraud, block deals, delisting
  scares) — since those are disproportionately bad outcomes, this biases
  the aggregate stats slightly in the creator's favor
- The NSE ticker list is a snapshot of currently-listed companies; tips on
  since-delisted or suspended stocks (structurally the worst outcomes)
  can never resolve or score — another source of favorable bias
- Video discovery uses SerpApi's search ranking within a channel, which
  correlates with view count and engagement — likely to over-sample the
  same "winner" videos creators themselves promote, rather than a random
  or complete sample of everything they said
- Transcripts are accepted as long as they contain at least one snippet —
  a video whose transcript only actually covers its first minute (a
  common ASR/captioning gap on longer videos) is still counted as "audited"
  in the funnel, and any tip made later in that video is simply never seen
- The stock series and the NIFTY series for the same tip can land on
  different Google Finance windows (e.g. a stock fetched on a 1Y/daily
  window differenced against an index fetched on a wider/weekly window
  for the same run), because the index's window is chosen from the oldest
  tip across the whole run rather than per-tip — excess return can
  therefore compare a daily-bar stock move against a weekly-bar index move
- The demo fixture bundle in `fixtures/demo/` is dated: Google Finance's
  window parameter (1M/6M/1Y/5Y) is chosen from how old a tip is *relative
  to today*, so as real time passes, previously-cached fixtures fall out
  of their original window and a fresh replay run can start missing
  fixtures it used to hit — the bundle isn't permanently reproducible,
  it needs periodic re-export
- A creator saying "I bought X" is treated as a scoreable LONG tip but
  flagged `PERSONAL_POSITION` — it's disclosure of a personal holding, not
  advice given to viewers, and the two are graded identically here. A tip
  hedged in the same breath ("not a recommendation, do your own research")
  is flagged `DISCLAIMED` but still scored — the market outcome doesn't
  care about the disclaimer, but a standing disclaimer said only once,
  elsewhere in the video (e.g. the intro), can't be detected at all, since
  extraction runs per transcript window

---

## Tech Stack

- **Python 3.11+** — primary language
- **SerpApi** (`google-search-results`) — search data backbone
- **Google Gemini** (`gemini-3.1-flash-lite`, free tier) — transcript extraction and verification
- **Pydantic v2** — schema validation
- **pandas + numpy** — price series processing
- **scipy** — statistical tests
- **rapidfuzz** — fuzzy string matching for quotes and tickers
- **SQLite** — persistent cache and data store
- **Streamlit** — web UI
- **Typer + Rich** — CLI with live progress
- **pytest** — test suite

## Project Structure

```
hisaab/
├── hisaab/
│   ├── serp/           # SerpApi client, cache, budget, fixtures
│   ├── pipeline/       # Discovery → Score (14 modules)
│   ├── prompts/        # LLM prompts as text files
│   ├── models.py       # Pydantic domain models
│   ├── llm.py          # LLM abstraction
│   ├── store.py        # SQLite persistence
│   └── cli.py          # Typer CLI
├── app/                # Streamlit web UI
├── data/               # NSE equity list, aliases
├── fixtures/demo/      # Replay bundle for offline use
├── tests/              # Unit tests (scoring, stats, cache, resolver)
└── .github/workflows/  # CI (lints app/hisaab/scripts/tests, runs pytest in replay mode)
```

---

## Testing & CI

Tests cover the most critical components:
- **Scoring**: TARGET_HIT, STOP_HIT, EXPIRED, NOT_TRIGGERED, OPEN, SHORT direction, excess return
- **Statistics**: Wilson CI, bootstrap CI, binomial test edge cases
- **Cache**: Key canonicalization, TTL behavior
- **Windows**: Building, keyword filtering
- **Resolver**: Alias matching, fuzzy matching

CI runs on every push via GitHub Actions **in replay mode** — no API keys needed.

```bash
pytest tests/ -v
```

---

## Ethics & Disclaimer

- All copy stays **neutral**. Hisaab never calls anyone a fraud or a scammer.
- It shows exact quotes, timestamps, a documented method, and market outcomes.
- The tool audits whatever channel the user enters — it's a ledger, not a hit piece.
- Good creators benefit too: verified track records are valuable.
- **This is for educational purposes only and does not constitute investment advice.**

---

## AI Tools Used

This project was built with assistance from **Claude** (Anthropic). AI tools were used for code generation, architecture planning, and documentation. All code was reviewed and the scoring logic is deterministic and auditable.

## Hackathon

Built new for the **SerpApi India Hackathon 2026**.

**Track**: Commerce & Market Intelligence

**Author**: Darshan Rajagoli ([GitHub](https://github.com/darshanrajagoli))

## License

MIT
