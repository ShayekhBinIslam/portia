"""portia/judge/overview.py: the v3 "overview pack": what the static judge sees, in a form the tool agent can act on.

The static (no-tools) arm gets the top-64 segments retrieved for the question: their transcripts and 2 frames each.
v1/v2 started from 8 text lines and had to spend turns rediscovering that evidence. v3 starts from the same 64
segments: their transcripts in time order with real handles, and 8 contact sheets of their 128 frames (4x4 tiles,
each stamped with its handle and time, so any tile can be zoomed). Sheets are cached per question.
"""
from __future__ import annotations

import hashlib
import math
import os
import threading
from pathlib import Path

from judge import corpus

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "overview"
# Portia's three investigators are threads of one process asking for the same question's sheets at the same moment:
# one lock per sheet set makes the others wait for the first build (three threads sharing a pid-only temp name
# broke a live run with FileNotFoundError / UnidentifiedImageError)
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def segments(qvec, playlists: list[str], k: int = 64) -> list[dict]:
    """Top-k segments for the question, grouped by video (videos in order of their best hit), each in time order."""
    hits = corpus.search(qvec, playlists, k=k)
    order = {}
    for i, h in enumerate(hits):
        order.setdefault(h["vid"], i)
    return sorted(hits, key=lambda h: (order[h["vid"]], h["start"]))


def transcript_block(segs: list[dict], max_chars: int = 600) -> str:
    out, vids = [], {}
    for s in segs:
        n = vids.setdefault(s["vid"], len(vids) + 1)
        tx = " ".join(corpus.transcript(s).split())
        tx = tx[:max_chars] + ("…" if len(tx) > max_chars else "")
        title = corpus.titles().get(s["vid"], ("",))[0][:60]
        out.append(f"[V{n} {s['handle']} {corpus.mmss(s['start'])}-{corpus.mmss(s['end'])} · {title}] {tx or '(no speech)'}")
    return "\n".join(out)


def sheets(segs: list[dict], per_frames: int = 2, per_sheet: int = 16, tile_w: int = 400) -> list:
    """Contact sheets of the segments' frames: [(PIL image, label)], cached on disk by the segment list."""
    from PIL import Image, ImageDraw, ImageFont
    key = hashlib.sha1("|".join(s["handle"] for s in segs).encode()).hexdigest()[:16]
    with _lock(key):
        return _sheets(segs, key, per_frames, per_sheet, tile_w)


def _sheets(segs, key, per_frames, per_sheet, tile_w):
    from PIL import Image, ImageDraw, ImageFont
    d = CACHE / key
    n_sheets = math.ceil(len(segs) * per_frames / per_sheet)
    if d.exists() and len(list(d.glob("*.jpg"))) == n_sheets:
        try:
            return [(Image.open(p).convert("RGB"), f"overview sheet {i + 1}/{n_sheets}") for i, p in enumerate(sorted(d.glob("*.jpg")))]
        except OSError:                                   # a sheet cut short (power cut): rebuild this set below
            pass
    frames = []
    for s in segs:
        frames += [(s, im, t) for im, t in corpus.frames(s, n=per_frames, max_side=tile_w)]
    d.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=15)
    out = []
    for k in range(0, len(frames), per_sheet):
        chunk = frames[k:k + per_sheet]
        th = int(tile_w * chunk[0][1].height / chunk[0][1].width)
        cols = 4
        sheet = Image.new("RGB", (cols * tile_w + (cols - 1) * 3, math.ceil(len(chunk) / cols) * (th + 3) - 3), "white")
        draw = ImageDraw.Draw(sheet)
        for i, (s, im, t) in enumerate(chunk):
            x, y = (i % cols) * (tile_w + 3), (i // cols) * (th + 3)
            sheet.paste(im.resize((tile_w, th)), (x, y))
            lab = f"{s['handle']} {corpus.mmss(t)}"
            draw.rectangle((x, y, x + int(draw.textlength(lab, font=font)) + 8, y + 20), fill="black")
            draw.text((x + 4, y + 2), lab, fill="yellow", font=font)
        label = f"overview sheet {k // per_sheet + 1}/{n_sheets}"
        tmp = d / f"{k // per_sheet:02d}.jpg.{os.getpid()}.{threading.get_ident()}.tmp"   # atomic, and per thread
        sheet.save(tmp, "JPEG", quality=85)
        os.replace(tmp, d / f"{k // per_sheet:02d}.jpg")
        # hand out the image as re-read from disk: a cached call re-reads the same file, so every run of a contest
        # sends byte-identical sheets (fresh in-memory sheets encoded differently and broke cache replays)
        out.append((Image.open(d / f"{k // per_sheet:02d}.jpg").convert("RGB"), label))
    return out
