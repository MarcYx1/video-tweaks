#!/usr/bin/python3
"""Engine self-check, no GUI: python3 test_engine.py"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path

here = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("vt", str(here / "video-tweaks"))
spec = importlib.util.spec_from_loader("vt", loader)
vt = importlib.util.module_from_spec(spec)
loader.exec_module(vt)


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def streams(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", p],
                         capture_output=True, text=True, check=True).stdout
    return [s["codec_type"] for s in json.loads(out)["streams"]]


def run(steps, dur, tmp):
    prog, lines = [], []
    job = vt.Job(steps, dur, dict(os.environ, TMPDIR=tmp), lines.append, prog.append)
    rc = job.run()
    if rc:
        print("\n".join(lines[-15:]))
    return rc, prog


with tempfile.TemporaryDirectory() as d:
    src = os.path.join(d, "clip one.mp4")
    ff("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30", *[x for f in (220, 330, 440, 550)
       for x in ("-f", "lavfi", "-i", f"sine=f={f}")], "-t", "10",
       "-map", "0", "-map", "1", "-map", "2", "-map", "3", "-map", "4",
       "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", src)
    dur, titles = vt.probe(src)
    assert abs(dur - 10) < 0.5 and len(titles) == 4, (dur, titles)

    # only mix: video copied, one audio track
    out, steps = vt.plan(src, 4, [0, 2], True, 8, d, d)
    assert out.endswith("clip one_mixed.mp4")
    rc, prog = run(steps, dur, d)
    assert rc == 0 and streams(out) == ["video", "audio"], streams(out)
    assert prog[-1] == 1.0

    # noise filter: on one track of a mix, and on a single track alone (no plain copy then)
    assert vt.MODEL, "models/sh.rnnn missing"
    out, steps = vt.plan(src, 4, [0, 3], True, 8, d, d, denoise=3)
    assert "arnndn" in " ".join(steps[0][1])
    rc, _ = run(steps, dur, d)
    assert rc == 0 and streams(out) == ["video", "audio"]
    out, steps = vt.plan(src, 4, [3], True, 8, d, d, denoise=3)
    assert "copy" not in steps[0][1][steps[0][1].index("-c:a") + 1]
    rc, _ = run(steps, dur, d)
    assert rc == 0 and streams(out) == ["video", "audio"]
    # length that ends in a partial 10 ms frame: arnndn used to emit NaNs there and aac failed
    odd = os.path.join(d, "odd.mp4")
    ff("-f", "lavfi", "-i", "testsrc=size=320x240:rate=30", "-f", "lavfi", "-i", "anoisesrc=a=0.1",
       "-t", "3.0035", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", odd)
    out, steps = vt.plan(odd, 1, [0], True, 8, d, d, denoise=0)
    rc, _ = run(steps, 3.0, d)
    assert rc == 0, "denoise on a partial last frame failed"
    _, steps = vt.plan(src, 1, [0], False, 8, d, d, denoise=0)
    assert len(steps) == 2, "single-track compress with filter needs the mix step"

    # compress + mix: under target size, one audio track, bar rises
    tmp = tempfile.mkdtemp(dir=d)
    out, steps = vt.plan(src, 4, [0, 1, 2, 3], False, 1, d, tmp)
    assert out.endswith("clip one_1mb.mp4") and len(steps) == 2
    rc, prog = run(steps, dur, tmp)
    assert rc == 0 and streams(out) == ["video", "audio"]
    # x264 overshoots ~5-10 % on a 10 s synthetic clip; a real 60 s clip at 8 MB came out 7.3 MB
    assert os.path.getsize(out) <= 1_100_000, os.path.getsize(out)
    assert prog == sorted(prog) and len(prog) > 5 and prog[-1] == 1.0, prog

    # trim, keep original: video copied, so it may start at the keyframe before 2 s
    out, steps = vt.plan(src, 4, [1], True, 8, d, d, trim=(2, 6))
    assert out.endswith("clip one_trimmed.mp4")
    rc, _ = run(steps, 4, d)
    assert rc == 0 and streams(out) == ["video", "audio"]
    assert 3.9 < vt.probe(out)[0] < 6.1, vt.probe(out)[0]
    first = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                            "-of", "csv=p=0", out], capture_output=True, text=True).stdout.split()[0]
    assert float(first) >= 0, f"hidden lead-in frames (VLC freezes): first pts {first}"
    # volume: forces the filter path, and plays
    out, steps = vt.plan(src, 4, [0, 1], True, 8, d, d, volumes={1: 0.5})
    assert "volume=0.5" in " ".join(steps[0][1])
    rc, _ = run(steps, dur, d)
    assert rc == 0 and streams(out) == ["video", "audio"]
    assert vt.find_mic(["Chat", "Game", "Media", "Mic"]) == 3
    assert vt.find_mic(["Devices: Monitor of Speakers", "Devices: alsa_input.usb-mic"]) == 1
    assert vt.find_mic(["Game"]) is None
    # trim + mix + compress: exact length
    tmp = tempfile.mkdtemp(dir=d)
    out, steps = vt.plan(src, 4, [0, 1], False, 1, d, tmp, trim=(2, 6))
    rc, prog = run(steps, 4, tmp)
    assert rc == 0 and streams(out) == ["video", "audio"]
    assert abs(vt.probe(out)[0] - 4) < 0.15, vt.probe(out)[0]
    assert prog[-1] == 1.0

    # cancel mid-encode: no ffmpeg left, pass logs only in the job's TMPDIR
    tmp = tempfile.mkdtemp(dir=d)
    out, steps = vt.plan(src, 4, [0, 1], False, 2, d, tmp)
    os.unlink(os.path.join(d, "clip one_1mb.mp4"))
    job = vt.Job(steps, dur, dict(os.environ, TMPDIR=tmp), lambda l: None, lambda f: None)
    t = threading.Thread(target=job.run)
    t.start()
    time.sleep(1.5)
    pid = job.proc.pid
    job.cancel()
    t.join(10)
    assert not t.is_alive() and job.cancelled
    time.sleep(0.5)
    left = subprocess.run(["ps", "-eo", "pgid="], capture_output=True, text=True).stdout.split()
    assert str(pid) not in left, "process group still alive"

print("engine ok")
