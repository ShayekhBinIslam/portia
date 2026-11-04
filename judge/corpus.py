"""portia/judge/corpus.py: read-only access to the video library the judge explores.

Nothing here is copied or rebuilt; it reads what the benchmark's final campaign already has:
  * domain -> playlists -> videos (titles):  play/videos_list/database_v3.json
  * per-playlist 30-second segment vectors:  play/3_inference/.cache/retrieval/Qwen--Qwen3-VL-Embedding-8B/
    (Qwen3-VL-Embedding-8B @ 418d038, L2-normalised, the same index the static judges were fed from)
  * transcripts + clips:                      <segment dir>/<stem>.{txt,mp4}

A segment is addressed by a short handle "<video id>@<start seconds>" (e.g. "VOQeRJHkP40@930"), which is
what the tools show the model and accept back.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from judge.paths import INDEX, VIDEOS  # noqa: E402  (pre-hackathon data: env, paths.local.json, or data/)


@lru_cache(maxsize=1)
def database() -> dict:
    return json.loads((VIDEOS / "database_v3.json").read_text(encoding="utf-8"))


def domain_playlists(domain: str) -> list[str]:
    return sorted(database().get(domain, {}))


@lru_cache(maxsize=1)
def titles() -> dict:
    """video id -> (title, playlist, domain). database_v3.json lists only the videos chosen for QA
    generation; ~10% of indexed segments belong to other videos of the same playlists, whose titles
    live in each playlist folder's playlist_info*.json; merge those too."""
    out = {}
    for dom, pls in database().items():
        for pl, vids in pls.items():
            for v in vids:
                out.setdefault(v["id"], (v.get("title", ""), pl, dom))
            for f in sorted((VIDEOS / pl).glob("playlist_info*.json")):
                try:
                    for v in json.loads(f.read_text(encoding="utf-8")):
                        if isinstance(v, dict) and v.get("id"):
                            out.setdefault(v["id"], (v.get("title", ""), pl, dom))
                except Exception:
                    pass
    return out


def _key(playlist: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", playlist)[:150]


@lru_cache(maxsize=64)
def index(playlist: str) -> dict:
    from safetensors.numpy import load_file
    emb = load_file(str(INDEX / f"{_key(playlist)}.safetensors"))["embeddings"].astype(np.float32)
    meta = json.loads((INDEX / f"{_key(playlist)}.json").read_text(encoding="utf-8"))
    segs = meta["segments"]
    for i, s in enumerate(segs):
        s["playlist"], s["row"] = playlist, i
        s["handle"] = f"{s['vid']}@{int(s['start'])}"
    return {"emb": emb, "segs": segs}


_HANDLES: dict = {}
_BY_VID: dict = {}                        # video id -> its registered segments, time-ordered


def _handles() -> dict:
    return _HANDLES


def register(playlists: list[str]) -> int:
    """Make every segment of these playlists resolvable by handle (a contest registers its domain)."""
    n = 0
    for pl in playlists:
        for s in index(pl)["segs"]:
            if s["handle"] not in _HANDLES:
                _HANDLES[s["handle"]] = s
                _BY_VID.setdefault(s["vid"], []).append(s)
                n += 1
    for v in {s["vid"] for pl in playlists for s in index(pl)["segs"]}:
        _BY_VID[v].sort(key=lambda s: s["start"])
    return n


def segment(handle: str) -> dict | None:
    """Resolve a handle. Registered playlists first; otherwise via the video's playlist, if known."""
    if handle in _HANDLES:
        return _HANDLES[handle]
    pl = titles().get(handle.split("@")[0], (None, None, None))[1]
    if pl:
        register([pl])
    return _HANDLES.get(handle)


def search(qvec: np.ndarray, playlists: list[str], k: int = 8, exclude: set | None = None) -> list[dict]:
    """Top-k segments by cosine over the given playlists (both sides unit-normalised)."""
    q = qvec.astype(np.float32).reshape(-1)
    q = q / (np.linalg.norm(q) + 1e-12)
    hits = []
    for pl in playlists:
        ix = index(pl)
        sc = ix["emb"] @ q
        top = np.argsort(-sc)[: k + len(exclude or ())]
        for i in top:
            s = ix["segs"][i]
            _handles().setdefault(s["handle"], s)
            if exclude and s["handle"] in exclude:
                continue
            hits.append({**s, "score": float(sc[i])})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]


def transcript(seg: dict) -> str:
    try:
        return (Path(seg["dir"]) / f"{seg['stem']}.txt").read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""


def neighbors(seg: dict, before: int = 1, after: int = 1) -> list[dict]:
    """The same video's adjacent 30-second segments, in time order (inclusive of seg)."""
    segs = [s for s in index(seg["playlist"])["segs"] if s["vid"] == seg["vid"]]
    segs.sort(key=lambda s: s["start"])
    i = next((j for j, s in enumerate(segs) if s["start"] == seg["start"]), None)
    if i is None:
        return [seg]
    for s in segs:
        _handles().setdefault(s["handle"], s)
    return segs[max(0, i - before): i + after + 1]


def frames(seg: dict, n: int = 4, max_side: int = 448):
    """n frames spread evenly across the 30-second clip, as (PIL image, absolute seconds)."""
    from decord import VideoReader, cpu
    from PIL import Image
    vr = VideoReader(str(Path(seg["dir"]) / f"{seg['stem']}.mp4"), ctx=cpu(0), num_threads=1)
    total, fps = len(vr), (float(vr.get_avg_fps()) or 25.0)
    idx = sorted({min(total - 1, int((j + 0.5) / n * total)) for j in range(n)})
    out = []
    for fi, arr in zip(idx, vr.get_batch(idx).asnumpy()):
        im = Image.fromarray(arr)
        s = max_side / max(im.size)
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)))
        out.append((im, seg["start"] + fi / fps))
    return out


def search_video(qvec: np.ndarray, vid: str, k: int = 6) -> list[dict]:
    """Top-k segments of ONE video by cosine (the same index as search, restricted to that video)."""
    segs = video_segments(vid)
    if not segs:
        return []
    q = qvec.astype(np.float32).reshape(-1)
    q = q / (np.linalg.norm(q) + 1e-12)
    sc = index(segs[0]["playlist"])["emb"][[s["row"] for s in segs]] @ q
    return [{**segs[i], "score": float(sc[i])} for i in np.argsort(-sc)[:k]]


def video_segments(vid: str) -> list[dict]:
    """Every registered 30-second segment of one video, in time order (register its playlist first)."""
    return _BY_VID.get(vid, [])


def frame_at(vid: str, t: float):
    """The NATIVE-resolution frame of video `vid` nearest absolute second t, as (PIL image, exact seconds),
    or None if the video has no registered segment. view_frames shows 448 px thumbnails; this is the source."""
    from decord import VideoReader, cpu
    from PIL import Image
    segs = video_segments(vid)
    if not segs:
        return None
    seg = next((s for s in segs if s["start"] <= t < s["end"]), None) or min(segs, key=lambda s: min(abs(s["start"] - t), abs(s["end"] - t)))
    vr = VideoReader(str(Path(seg["dir"]) / f"{seg['stem']}.mp4"), ctx=cpu(0), num_threads=1)
    fps = float(vr.get_avg_fps()) or 25.0
    fi = max(0, min(len(vr) - 1, int((t - seg["start"]) * fps)))
    return Image.fromarray(vr[fi].asnumpy()), seg["start"] + fi / fps


def parse_time(t) -> float:
    """Seconds from 1234 / 1234.5 / "20:34" / "1:02:03" / "1234"."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(x) for x in str(t).strip().split(":")]
    sec = 0.0
    for x in parts:
        sec = sec * 60 + x
    return sec


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"
