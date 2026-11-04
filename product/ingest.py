#!/usr/bin/env python3
"""portia/product/ingest.py: bring your own video: a YouTube link becomes a collection Portia's agents can search.

    python product/ingest.py <collection-id> <youtube-url> [--max-minutes 30] [--transcriber youtube|muse]
    python product/ingest.py <collection-id> --file video.mp4 [--captions subs.vtt|subs.srt] [--title "..."]

Writes product/collections/<id>/ in the corpus's own format, so the unchanged tools (search, search_video,
read_transcript, contact_sheet, zoom, ...) work on it:
  1. yt-dlp: the video (<= 720p) and its captions (manual if any, else automatic; English); or an uploaded file with
     optional .vtt/.srt captions (when YouTube refuses a download, HTTP 403, the user uploads the file instead)
  2. ffmpeg: exact 30-second clips (one encode pass, keyframes forced every 30 s, no audio)
  3. each clip's transcript: the caption cues it overlaps (automatic captions de-duplicated)
  4. each clip embedded as a document (title + transcript) by the query encoder (Qwen3-VL-Embedding-8B, text)
  5. index.json + index.safetensors + collection.json; progress lines in progress.jsonl (the UI polls them)
Up to 30 minutes by default: at most 60 clips, so the agents' 64-segment overview covers the whole video.
Transcripts come from YouTube captions or the upload's own captions by default. With --transcriber muse an uploaded
file is transcribed by Muse Voice Transcribe on the Meta Model API instead, while meta_hackathon/.meta_locked carries
the user's unlock line for it (judge/meta_lock.py), at $0.18 per hour of audio and at most $0.10 per video.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
COLL = HERE / "collections"
PY = sys.executable
from judge.paths import NODE as _NODE, YT_COOKIES  # noqa: E402  (YouTube links only; off by default)
from judge.config import load as config  # noqa: E402
NODE = str(_NODE or "node")                                      # yt-dlp's JavaScript runtime for YouTube
COOKIES = YT_COOKIES or Path("/nonexistent")
ENCODER = config("models")["query_encoder"]["url"]
VID = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


class Progress:
    def __init__(self, d: Path):
        self.p = d / "progress.jsonl"

    def __call__(self, step: str, state: str = "run", **kw):
        with open(self.p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(time.time(), 2), "step": step, "state": state, **kw}, ensure_ascii=False) + "\n")


def vtt_cues(path: Path) -> list[tuple[float, float, str]]:
    """(start, end, text) cues of a WebVTT file; automatic captions repeat each line as it scrolls, so a line already
    seen in the previous cue is dropped."""
    def sec(t):
        h, m, s = (["0"] + t.split(":"))[-3:]
        return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))
    cues, prev = [], set()
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="ignore")):
        m = re.search(r"(\d+:\d{2}:\d{2}[.,]\d+|\d+:\d{2}[.,]\d+)\s+-->\s+(\d+:\d{2}:\d{2}[.,]\d+|\d+:\d{2}[.,]\d+)", block)
        if not m:
            continue
        lines = [html.unescape(re.sub(r"<[^>]+>", "", l)).strip() for l in block[m.end():].splitlines()]
        lines = [l for l in lines if l]
        new = [l for l in lines if l not in prev]
        prev = set(lines)
        if new:
            cues.append((sec(m.group(1)), sec(m.group(2)), " ".join(new)))
    return cues


# Muse Voice Transcribe (Meta Model API, POST /v1/asr/transcribe): 16 kHz mono WAV, at most 10 minutes and 32 MB per request
_ASR = config("models")["muse_voice_transcribe"]  # configs/models.yaml and budgets.yaml
MUSE_ASR_URL, MUSE_ASR_MODEL = _ASR["url"], _ASR["model"]
MUSE_ASR_USD_PER_HOUR = float(_ASR["usd_per_hour"])     # dev.meta.ai pricing: audio processed, billed in whole seconds
MUSE_ASR_CAP_USD = float(config("budgets")["meta_api"]["transcribe_cap_usd_per_video"])   # the user's cap
MUSE_ASR_UNLOCK = "UNLOCKED: META_DEV_KEY for muse-voice-transcribe-1.0"
MUSE_ASR_PART_S = int(_ASR["part_seconds"])


def muse_cues(src: Path, dur: float, vid: str, cid: str, say) -> list[tuple[float, float, str]]:
    """The speech of a video as (start, end, text) cues, one per transcribed turn, sent in parts of six minutes."""
    from judge import meta_client, meta_lock
    meta_lock.check(meta_lock.META_API_URL)
    if not meta_lock.LOCK.exists() or MUSE_ASR_UNLOCK not in meta_lock.LOCK.read_text(encoding="utf-8"):
        raise RuntimeError("Muse Voice Transcribe is locked (meta_hackathon/.meta_locked has no unlock line for it)")
    est = dur / 3600 * MUSE_ASR_USD_PER_HOUR
    if est > MUSE_ASR_CAP_USD or meta_client.spent() + est > meta_lock.META_DEV_CAP_USD:
        raise RuntimeError(f"Muse Voice Transcribe would cost about ${est:.3f}, over the cap")
    key = meta_lock.dev_key()                    # never logged
    work = COLL / cid / "src"
    cues, parts = [], max(1, math.ceil(dur / MUSE_ASR_PART_S))
    for k in range(parts):
        t0 = k * MUSE_ASR_PART_S
        wav = work / f"asr_{k:02d}.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t0), "-t", str(MUSE_ASR_PART_S), "-i", str(src), "-vn",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-map_metadata", "-1", str(wav)], check=True, timeout=600)
        req = {"mode": "DIARIZATION", "model": MUSE_ASR_MODEL, "audioEncoding": "WAV"}
        with open(wav, "rb") as f:
            r = requests.post(f"{MUSE_ASR_URL}?sessionId=portia-{vid}-{k}", headers={"Authorization": f"Bearer {key}"},
                              files={"request": (None, json.dumps(req), "application/json"), "audio": (wav.name, f, "audio/wav")},
                              timeout=900)
        if r.status_code != 200:
            raise RuntimeError(f"Muse Voice Transcribe: HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        secs = int(j.get("audioDurationMs", 0) // 1000)
        with open(meta_client.SPEND, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": "product_transcribe", "run": f"ingest_{cid}",
                                "model": MUSE_ASR_MODEL, "audio_s": secs, "usd": round(secs / 3600 * MUSE_ASR_USD_PER_HOUR, 6)}) + "\n")
        for turn in j.get("turns", []):
            text = (turn.get("transcript") or "").strip()
            if text:
                cues.append((t0 + turn["startMs"] / 1000, t0 + turn["endMs"] / 1000, text))
        say("download", info=f"Muse Voice Transcribe: part {k + 1} of {parts}, {len(cues)} turns so far")
    return cues


def embed(texts: list[str]) -> np.ndarray:
    """Document embeddings from the query encoder (no instruction: queries carry it, documents do not)."""
    r = requests.post(f"{ENCODER}/embed", json={"texts": texts}, timeout=1800)
    r.raise_for_status()
    j = r.json()
    if "error" in j:
        raise RuntimeError(j["error"])
    return np.stack([np.frombuffer(base64.b64decode(v), dtype="<f4") for v in j["vectors_b64"]]).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cid")
    ap.add_argument("url", nargs="?", default="")
    ap.add_argument("--file", default="", help="an uploaded video instead of a YouTube link")
    ap.add_argument("--captions", default="", help="the upload's captions (.vtt or .srt), optional")
    ap.add_argument("--title", default="")
    ap.add_argument("--max-minutes", type=float, default=30)
    ap.add_argument("--transcriber", choices=["youtube", "muse"], default="youtube")
    a = ap.parse_args()
    d = COLL / a.cid
    (d / "src").mkdir(parents=True, exist_ok=True)
    say = Progress(d)
    try:
        if a.file:
            src, cues, vid, title, dur, url = upload(a, say)
        else:
            src, cues, vid, title, dur, url = youtube(a, d, say)
        finish(a, d, say, src, cues, vid, title, dur, url)
    except Exception as e:
        msg = (e.stderr[-400:] if isinstance(e, subprocess.CalledProcessError) and e.stderr else f"{type(e).__name__}: {e}")
        if "403" in str(msg):
            msg = ("YouTube refused to let this video be downloaded (HTTP 403). Download it yourself and use "
                   "\"Upload a file\" instead (with its captions as .vtt or .srt if you have them).")
        say("error", "error", info=str(msg)[:500])
        sys.exit(1)


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, timeout=60)
    return float(r.stdout.strip() or 0)


def upload(a, say):
    """An uploaded file: its own 11-character id (the tools expect YouTube-style ids), captions if given."""
    import hashlib
    src = Path(a.file)
    h = hashlib.sha1()
    with open(src, "rb") as f:
        h.update(f.read(1 << 20))
    h.update(str(src.stat().st_size).encode())
    vid = base64.urlsafe_b64encode(h.digest()).decode()[:11]
    dur = duration(src)
    if dur <= 0:
        raise ValueError("this file is not a readable video")
    if dur > a.max_minutes * 60:
        raise ValueError(f"the video is {dur / 60:.0f} minutes; the limit is {a.max_minutes:.0f}")
    title = a.title.strip() or src.stem
    if a.transcriber == "muse":
        cues = muse_cues(src, dur, vid, a.cid, say)
    else:
        cues = vtt_cues(Path(a.captions)) if a.captions else []
    say("download", "done", info=f"uploaded file, {dur / 60:.1f} min · " + (f"{len(cues)} {'transcribed turns' if a.transcriber == 'muse' else 'caption cues'}" if cues else "no captions: transcripts stay empty"))
    return src, cues, vid, title, dur, ""


def youtube(a, d: Path, say):
    """A YouTube link: the video and its English captions through yt-dlp."""
    m = VID.search(a.url) or re.fullmatch(r"([A-Za-z0-9_-]{11})", a.url.strip())
    if not m:
        raise ValueError("not a YouTube video link")
    vid = m.group(1)
    if a.transcriber == "muse":
        from judge import meta_lock
        meta_lock.check("https://api.meta.ai")       # refused while META_DEV_KEY is locked
        raise RuntimeError("Muse Voice Transcribe is not wired yet; use YouTube captions")
    # 1. video + captions
    say("download", info=f"video {vid}")
    base = ["--js-runtimes", f"node:{NODE}", "--no-playlist", "--quiet", "--no-warnings"]
    if COOKIES.exists():
        base += ["--cookies", str(COOKIES)]
    meta = json.loads(subprocess.run([PY, "-m", "yt_dlp", *base, "-J", f"https://www.youtube.com/watch?v={vid}"],
                                     capture_output=True, text=True, timeout=180, check=True).stdout)
    dur = float(meta.get("duration") or 0)
    title = meta.get("title") or vid
    if dur > a.max_minutes * 60:
        raise ValueError(f"the video is {dur / 60:.0f} minutes; the limit is {a.max_minutes:.0f}")
    say("download", info=f"{title} ({dur / 60:.1f} min)")
    subprocess.run([PY, "-m", "yt_dlp", *base, "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]/b",
                    "--merge-output-format", "mp4", "-o", str(d / "src" / "video.%(ext)s"),
                    f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=1800, check=True)
    # captions separately, English tracks only ("en.*" also matches dozens of auto-translations and trips YouTube's
    # rate limit), retried once; a video without them still gets indexed, with empty transcripts
    for attempt in range(2):
        r = subprocess.run([PY, "-m", "yt_dlp", *base, "--skip-download", "--write-subs", "--write-auto-subs",
                            "--sub-langs", "en,en-orig,en-US,en-GB", "--sub-format", "vtt",
                            "-o", str(d / "src" / "video.%(ext)s"), f"https://www.youtube.com/watch?v={vid}"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0 or list((d / "src").glob("video*.vtt")):
            break
        time.sleep(8)
    src = next((p for p in (d / "src").glob("video.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if not src:
        raise RuntimeError("download produced no video file")
    subs = sorted((d / "src").glob("video*.vtt"), key=lambda p: (".en.vtt" not in p.name, len(p.name)))
    cues = vtt_cues(subs[0]) if subs else []
    say("download", "done", info=f"{len(cues)} caption cues" if cues else "no English captions: transcripts stay empty")
    return src, cues, vid, title, dur, f"https://www.youtube.com/watch?v={vid}"


def finish(a, d: Path, say, src: Path, cues: list, vid: str, title: str, dur: float, url: str):
    """Clips, transcripts, embeddings and the collection files, the same for both sources."""
    # 2. exact 30-second clips
    say("clips")
    clips = d / "clips"
    clips.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-an", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-force_key_frames", "expr:gte(t,n_forced*30)", "-f", "segment", "-segment_time", "30",
                    "-reset_timestamps", "1", str(clips / "c%04d.mp4")], check=True, timeout=3600)
    files = sorted(clips.glob("c*.mp4"))
    if dur:                                          # the segmenter can emit a near-empty tail clip: set it aside
        keep = [f for i, f in enumerate(files) if 30 * i < dur - 0.5]
        for f in files[len(keep):]:
            (clips / "dropped").mkdir(exist_ok=True)
            f.rename(clips / "dropped" / f.name)
        files = keep
    segs = []
    for i, f in enumerate(files):
        start, end = 30 * i, min(30 * (i + 1), int(dur) if dur else 30 * (i + 1))
        stem = f"{vid}-{i}-{start}-{end}"
        f.rename(clips / f"{stem}.mp4")
        text = " ".join(t for s, e, t in cues if s < end and e > start)
        (clips / f"{stem}.txt").write_text(text, encoding="utf-8")
        segs.append({"stem": stem, "vid": vid, "seg": i, "start": start, "end": end, "dir": str(clips)})
    say("clips", "done", info=f"{len(segs)} clips of 30 s")
    # 3. embeddings (documents: title + transcript)
    say("index", info=f"embedding {len(segs)} clips on the query encoder")
    docs = [f"{title}. " + ((clips / f"{s['stem']}.txt").read_text(encoding="utf-8") or "(no speech)")[:3000] for s in segs]
    vecs = [embed(docs[i:i + 8]) for i in range(0, len(docs), 8)]
    E = np.concatenate(vecs)
    from safetensors.numpy import save_file
    save_file({"embeddings": E}, str(d / "index.safetensors"))
    playlist = f"yt_{vid}_{re.sub(r'[^A-Za-z0-9]+', '_', title)[:60]}"
    (d / "index.json").write_text(json.dumps({"playlist": playlist, "model": "Qwen/Qwen3-VL-Embedding-8B (text, box CPU)",
                                              "n": len(segs), "segments": segs}, ensure_ascii=False), encoding="utf-8")
    hhmmss = time.strftime("%H:%M:%S", time.gmtime(dur))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(min(5.0, dur / 2)), "-i", str(src), "-frames:v", "1",
                    "-vf", "scale=480:-2", str(d / "thumb.jpg")], timeout=60)
    (d / "collection.json").write_text(json.dumps({
        "id": a.cid, "vid": vid, "url": url, "source": "upload" if a.file else "youtube", "title": title, "duration": dur,
        "duration_formatted": hhmmss, "playlist": playlist, "domain": f"Your video: {title[:48]}", "clips": len(segs),
        "captions": bool(cues), "transcriber": "Muse Voice Transcribe" if a.transcriber == "muse" else "file captions" if a.file else a.transcriber, "created": time.time()},
        ensure_ascii=False), encoding="utf-8")
    say("index", "done", info=f"{len(segs)} clips indexed")
    say("ready", "done")


if __name__ == "__main__":
    main()
