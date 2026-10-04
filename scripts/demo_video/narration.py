"""Narration lines (caption HTML; spoken text = tags stripped) + TTS generation."""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

VOICE = "en-IN-PrabhatNeural"
RATE = "+10%"
OUT = Path(__file__).parent / "voice"

LINES = {
    "title": "This is <b>Hisaab</b>. Hisaab keeps the receipts.",
    "hook": "Indian finfluencers make thousands of stock calls on YouTube. <b>Nobody keeps score.</b> "
    "The winners get re-shared in thumbnails. The losers are quietly forgotten.",
    "insight": "But every tip is a <b>timestamped, falsifiable prediction</b>. The transcript has the words, "
    "the video has the time, and the market has the outcome. <b>SerpApi gives us all three.</b>",
    "run_intro": "Let's audit a real channel: <b>Rakesh Bansal</b>, ten videos. This is replay mode: "
    "a real recorded audit, running locally, with zero API keys.",
    "run_a": "Hisaab searches the channel with SerpApi's <b>YouTube</b> engine, then pulls each video's "
    "exact publish date and full <b>transcript</b>.",
    "run_b": "An LLM extracts every stock call: company, direction, target, stop-loss. "
    "Then each quote is <b>checked back against the transcript</b>, so nothing is hallucinated.",
    "run_c": "Tickers are resolved to NSE symbols, real prices come from <b>Google Finance</b>, "
    "and <b>Google News</b> explains the biggest moves.",
    "score1": "Here's the scorecard. The hit rate is measured <b>against the NIFTY 50</b>, not against zero, "
    "with a confidence interval and a significance test.",
    "score2": "Because ten tips and a thousand tips <b>shouldn't look equally certain</b>.",
    "score3": "<b>Conviction analysis</b> asks a simple question: do the bold, guaranteed-multibagger calls "
    "actually do better than ordinary ones?",
    "score4": "This is <b>ten thousand rupees on every tip</b>, against the same money in the NIFTY, "
    "over the same dates.",
    "score5": "Every tip is graded twice: on the creator's own terms, target or stop-loss, "
    "and on <b>market terms</b>.",
    "tip1": "<b>This is the receipt.</b> The video, cued to the exact second the tip was said, "
    "with the original Hindi quote and an English translation.",
    "tip2": "Entry and exit come from <b>real daily closing prices</b>, with the creator's target "
    "and stop-loss drawn right on the chart.",
    "tip3": "Pick any tip and verify it yourself. That's the difference between "
    "<b>a claim and a receipt</b>.",
    "method1": "The rule is simple: <b>the LLM reads, Python judges.</b> Every number on the scorecard "
    "comes from deterministic, auditable code.",
    "method2": "And the limitations are <b>stated up front, not hidden</b>: survivorship bias, "
    "selection bias, closing prices only.",
    "end": "Five SerpApi engines, doing real work. <b>Hisaab keeps the receipts.</b>",
}


def spoken(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


async def build():
    import edge_tts

    OUT.mkdir(exist_ok=True)
    durations = {}
    for key, html in LINES.items():
        path = OUT / f"{key}.mp3"
        await edge_tts.Communicate(spoken(html), VOICE, rate=RATE).save(str(path))
        durations[key] = duration(path)
    (OUT / "durations.json").write_text(json.dumps(durations, indent=2))
    total = sum(durations.values())
    print(json.dumps(durations, indent=1))
    print(f"total speech: {total:.1f}s")


if __name__ == "__main__":
    asyncio.run(build())
    sys.exit(0)
