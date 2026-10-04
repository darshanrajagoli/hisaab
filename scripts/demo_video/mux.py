"""Cut the raw recording to [start, stop] and lay each narration clip at its timeline offset."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
raw_dir = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "video_raw")
out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "hisaab_demo.mp4")

tl = json.loads((raw_dir / "timeline.json").read_text())
events = tl["events"]
start = next(e["t"] for e in events if e["key"] == "start")
stop = next(e["t"] for e in events if e["key"] == "stop")
clips = [e for e in events if e["key"] not in ("start", "stop")]

cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{stop:.3f}", "-i", tl["video"]]
for c in clips:
    cmd += ["-i", str(HERE / "voice" / f"{c['key']}.wav")]

filters = []
for i, c in enumerate(clips, start=1):
    delay = max(0, int((c["t"] - start) * 1000))
    filters.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
mix_inputs = "".join(f"[a{i}]" for i in range(1, len(clips) + 1))
filters.append(f"{mix_inputs}amix=inputs={len(clips)}:normalize=0,volume=1.0[aout]")

cmd += [
    "-filter_complex", ";".join(filters),
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
    str(out),
]
subprocess.run(cmd, check=True)
dur = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
    capture_output=True, text=True,
).stdout.strip()
print(f"wrote {out} ({float(dur):.1f}s, {out.stat().st_size / 1e6:.1f} MB)")
