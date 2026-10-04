"""
Cut the raw recording to [start, stop] and lay each narration clip at its cue.

Cue times come from the sync marker the recorder flips in the top-left
corner at every cue, read from the actual frames: Playwright drops frames
when the page is busy, so wall-clock offsets drift by seconds over a take.
The marker is painted over in the output.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
raw_dir = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "video_raw")
out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "hisaab_demo.mp4")

tl = json.loads((raw_dir / "timeline.json").read_text())
video = tl["video"]
events = tl["events"]
FPS = 25
MK = 12  # marker size in px


def marker_colors() -> list[str]:
    """Classify the marker color in every frame as K/R/G/B."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={FPS},crop=4:4:4:4",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    frame_bytes = 4 * 4 * 3
    labels = []
    for i in range(0, len(raw) - frame_bytes + 1, frame_bytes):
        px = raw[i:i + frame_bytes]
        r = sum(px[0::3]) / 16
        g = sum(px[1::3]) / 16
        b = sum(px[2::3]) / 16
        m = max(r, g, b)
        labels.append("K" if m < 90 else "RGB"[[r, g, b].index(m)])
    return labels


labels = marker_colors()
# Video time of every color change, in order.
flips = [i / FPS for i in range(1, len(labels)) if labels[i] != labels[i - 1]]

cued = [e for e in events if e["key"] != "start"]
if len(flips) == len(cued) - 1 and cued[-1]["key"] == "stop":
    # The stop flip can land after the last recorded frame; derive it.
    cued = cued[:-1]
if len(flips) != len(cued):
    sys.exit(f"sync marker: found {len(flips)} flips for {len(cued)} cues — not muxing")

vt = {e["key"]: flips[i] for i, e in enumerate(cued)}
by_key = {e["key"]: e["t"] for e in events}
start = vt["title"] - (by_key["title"] - by_key["start"])
stop = vt.get("stop", vt["end"] + by_key["stop"] - by_key["end"])
clips = [e["key"] for e in cued if e["key"] != "stop"]

# Paint the marker over with the pixel colour just beside it.
probe = subprocess.run(
    ["ffmpeg", "-v", "error", "-ss", f"{start + 8:.2f}", "-i", video, "-frames:v", "1",
     "-vf", f"crop=2:2:{MK + 4}:{MK // 2}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
    capture_output=True, check=True,
).stdout
cover = "0x{:02X}{:02X}{:02X}".format(*probe[:3])

cmd = ["ffmpeg", "-y", "-v", "error", "-i", video]
for key in clips:
    cmd += ["-i", str(HERE / "voice" / f"{key}.wav")]

filters = [
    f"[0:v]trim=start={start:.3f}:end={stop:.3f},setpts=PTS-STARTPTS,"
    f"drawbox=x=0:y=0:w={MK + 2}:h={MK + 2}:color={cover}:t=fill[v]"
]
for i, key in enumerate(clips, start=1):
    delay = max(0, int((vt[key] - start) * 1000))
    filters.append(f"[{i}:a]adelay={delay}|{delay}[a{i}]")
mix_inputs = "".join(f"[a{i}]" for i in range(1, len(clips) + 1))
filters.append(f"{mix_inputs}amix=inputs={len(clips)}:normalize=0,apad[aout]")

cmd += [
    "-filter_complex", ";".join(filters),
    "-map", "[v]", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
    "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
    str(out),
]
subprocess.run(cmd, check=True)
dur = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
    capture_output=True, text=True,
).stdout.strip()
drift = (stop - start) - (by_key["stop"] - by_key["start"])
print(f"wrote {out} ({float(dur):.1f}s, {out.stat().st_size / 1e6:.1f} MB); "
      f"corrected drift {drift:+.2f}s")
