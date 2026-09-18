# 📊 Hisaab — Grade Indian Finfluencer Stock Tips

> **hisaab keeps the receipts.**

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

**The LLM reads. Python judges.** The LLM's only job is turning messy Hinglish speech into structured tip data. Every number on the scorecard — returns, hit rates, confidence intervals, p-values — comes from deterministic Python code that can be audited and reproduced.

---

## Quickstart

### Replay Mode (No API Key Needed)

Judges and reviewers can run the full app immediately:

```bash
git clone https://github.com/darshanrajagoli/hisaab.git
cd hisaab
pip install -e .
```

### Live Mode

```bash
cp .env.example .env
# Edit .env with your API keys:
# SERPAPI_API_KEY=your_key
# ANTHROPIC_API_KEY=your_key

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

---

## How Hisaab Uses SerpApi

SerpApi is the **backbone** of Hisaab. Without it, there is no transcript, no timestamp, and no price history — so there is no product.

| Engine | Parameters Used | Response Fields Consumed | Why It's Essential | Calls/Audit |
|--------|----------------|------------------------|-------------------|-------------|
| `youtube_channel` | `channel_id`, `search_query`, `handle` | `videos[]` (video_id, title) | Discovers tip videos via within-channel search with tip keywords | ~2 |
| `youtube_video` | `v` (video_id) | `published_date`, `description`, `views` | Gets exact publish date — the timestamp that anchors every trade | ~10 |
| `youtube_video_transcript` | `video_id`, `lang`, `type=asr` | `transcript_results[]` (text, start_ms, end_ms) | **Core engine.** Extracts the spoken words + millisecond timestamps. This is where tips live. | ~10 |
| `google_finance` | `q` (ticker:NSE), `window` | `graph[]` (date, price) | Price history to score every tip. One call per ticker, not per tip. | ~10–12 |
| `google_news` | `q` (company + dates), `gl=in` | `news_results[]` (title, snippet, link) | Explains the top wins and losses — turns numbers into stories | ~3–6 |

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

If the creator stated a specific entry price, the tip only counts as "triggered" if the close reaches that entry within 5 trading days. Otherwise: `NOT_TRIGGERED`.

### Horizon Rule
| Stated Horizon | Trading Days |
|---------------|-------------|
| Creator's own timeframe | As stated |
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
- **Significance**: One-sided binomial test against 50% coin flip
- **₹10,000/tip Simulation**: Equal-weight portfolio vs NIFTY over same dates
- **Conviction Analysis**: Hit rate for "guaranteed"/"multibagger" calls vs regular

### Unscored Categories (shown, not hidden)
- INTRADAY, F&O, IPO, Mutual Fund, Crypto
- Unresolved tickers
- Corporate action flags (>35% single-day move)
- Not triggered, Open (horizon not elapsed)

### Limitations
- Only closing prices available (not intraday highs/lows)
- Auto-generated transcripts may have errors, especially in Hinglish
- Corporate actions (splits, bonuses, demergers) can distort naive returns
- F&O calls are out of scope — strike, expiry, and premium data unavailable
- Entry timing assumes next-day close; real viewers may enter differently

---

## Tech Stack

- **Python 3.11+** — primary language
- **SerpApi** (`google-search-results`) — search data backbone
- **Anthropic Claude** — transcript extraction and verification
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
│   ├── pipeline/       # Discovery → Score (12 modules)
│   ├── prompts/        # LLM prompts as text files
│   ├── models.py       # Pydantic domain models
│   ├── llm.py          # LLM abstraction
│   ├── store.py        # SQLite persistence
│   └── cli.py          # Typer CLI
├── app/                # Streamlit web UI
├── data/               # NSE equity list, aliases
├── fixtures/demo/      # Replay bundle for offline use
├── tests/              # Unit tests (scoring, stats, cache, resolver)
├── docs/               # Architecture diagram
└── .github/workflows/  # CI (runs in replay mode, no secrets)
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
