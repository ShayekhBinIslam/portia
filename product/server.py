#!/usr/bin/env python3
"""portia/product/server.py: Portia's web server (FastAPI): the UI, the case library, jobs and their live event stream.

    python product/server.py [--port 5250] [--host 127.0.0.1]

Binds to localhost; open it through an SSH tunnel. The Baseten key never reaches this process's responses: the optional
Spark Open adjudicator only reports whether it is available and what the product has spent.
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402
from judge.config import load as config  # noqa: E402  (engine put the repo root on sys.path)

HERE = Path(__file__).resolve().parent
JOB_ID = re.compile(r"^\d{4}-\d{6}-[0-9a-f]{4}$")
IMG = re.compile(r"^[a-z0-9_]+\.jpg$")
app = FastAPI(title="Portia", docs_url=None, redoc_url=None)
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=1024)  # Starlette leaves event streams (live runs) uncompressed
CACHED = ("/api/library", "/api/corpus", "/api/proof", "/api/footage/", "/api/titles/", "/api/case/", "/static/")


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """Short caching for the read-only JSON and the app's files (Fable's review: the first load over the tunnel)."""
    r = await call_next(request)
    if request.method == "GET" and r.status_code == 200 and request.url.path.startswith(CACHED) and "cache-control" not in r.headers:
        r.headers["Cache-Control"] = "public, max-age=300"
    return r
# Public mode (plan 016, the Cloudflare Tunnel for judges): with PORTIA_ACCESS_CODE set, anything that starts work
# (runs, batches, uploads, YouTube links) needs the code in an X-Portia-Code header; browsing stays open.
_PUBLIC = Path(__file__).resolve().parent / "public.env"     # KEY=VALUE lines; kept out of the repo
if _PUBLIC.exists():
    for _line in _PUBLIC.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
ACCESS_CODE = os.environ.get("PORTIA_ACCESS_CODE", "")
MAX_PENDING = int(os.environ.get("PORTIA_MAX_PENDING", config("product")["limits"]["max_pending"]))       # unfinished runs at once (each waits for a GPU slot)
MAX_BATCH = int(os.environ.get("PORTIA_MAX_BATCH", config("product")["limits"]["max_batch"]))
MAX_UPLOAD_MB = int(os.environ.get("PORTIA_MAX_UPLOAD_MB", config("product")["limits"]["max_upload_mb"]))


@app.middleware("http")
async def access_gate(request: Request, call_next):
    if ACCESS_CODE and request.method not in ("GET", "HEAD", "OPTIONS"):
        given = request.headers.get("x-portia-code", "")
        if not hmac.compare_digest(given.encode(), ACCESS_CODE.encode()):
            return JSONResponse({"detail": "access code required"}, status_code=401)
    return await call_next(request)


def _busy(extra: int = 1):
    pending = sum(1 for h in E.history(200) if h.get("running"))
    if pending + extra > MAX_PENDING:
        raise HTTPException(429, f"Portia is busy with {pending} runs; try again in a few minutes.")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Uvicorn runs at log level warning (no access log): log every write and every error response to server.log."""
    t0 = time.time()
    response = await call_next(request)
    if request.method != "GET" or response.status_code >= 400:
        print(f"[req] {time.strftime('%Y-%m-%d %H:%M:%S')} {request.method} {request.url.path} -> {response.status_code} "
              f"({1000 * (time.time() - t0):.0f} ms)", flush=True)
    return response
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


@app.get("/")
def index():
    # Cloudflare keeps /static/* for hours (its browser TTL is 4 h), so the page asks for app.js and style.css by version:
    # a changed file gets a new URL, and returning visitors never mix an old script with a new server
    html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        html = html.replace(f'"/static/{name}"', f'"/static/{name}?v={int((HERE / "static" / name).stat().st_mtime)}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ status
def _server_state(url: str) -> dict:
    base = url.rsplit("/v1", 1)[0]
    try:
        ok = requests.get(f"{url}/models", timeout=2).ok
    except requests.RequestException:
        return {"up": False}
    running = waiting = None
    try:
        for line in requests.get(f"{base}/metrics", timeout=2).text.splitlines():
            if line.startswith("vllm:num_requests_running"):
                running = int(float(line.rsplit(" ", 1)[1]))
            elif line.startswith("vllm:num_requests_waiting"):
                waiting = int(float(line.rsplit(" ", 1)[1]))
    except (requests.RequestException, ValueError):
        pass
    return {"up": ok, "running": running, "waiting": waiting}


@app.get("/api/health")
def health():
    servers = [{"gpu": gpu, "url": url.split("//")[1].split("/")[0], **_server_state(url)} for url, gpu in E.SERVERS]
    try:
        enc = requests.get("http://127.0.0.1:18531/health", timeout=2).ok
    except requests.RequestException:
        enc = False
    return {"servers": servers, "encoder": enc, "spark": E.spark_status(), "spark13": E.spark13_status(), "time": time.time(),
            "access": bool(ACCESS_CODE)}


# ------------------------------------------------------------------ cases
@app.get("/api/library")
def library_list():
    lib = E.library()
    return {"cases": [{**E.case_json(cid, c, full=False), "question": c.question[:260]} for cid, c in lib.items()],
            "featured": E.FEATURED, "domains": sorted({c.domain for c in lib.values()})}


@app.get("/api/case/{cid}")
def case(cid: str):
    c = E.library().get(cid)
    if not c:
        raise HTTPException(404, "no such case")
    return E.case_json(cid, c)


@app.get("/api/case/{cid}/truth")
def case_truth(cid: str):
    c = E.library().get(cid)
    if not c:
        raise HTTPException(404, "ground truth exists only for library cases")
    return E.truth(c)


@app.get("/api/demo")
def demo():
    """The latest finished run of a featured case (the home page's "Watch a case" replays it), else a featured case."""
    if (E.JOBS / E.DEMO_JOB / "job.json").exists():
        m = json.loads((E.JOBS / E.DEMO_JOB / "job.json").read_text(encoding="utf-8"))
        if m.get("final"):
            return {"job": E.DEMO_JOB, "case": m.get("case_id"), "upload_job": E.UPLOAD_DEMO_JOB}
    done = [h for h in E.history(200) if h.get("case_id") in E.FEATURED and h.get("final") and not h.get("running")]
    # the most telling replay: the agents split and an adjudicator decided (all three panels move)
    split = [h for h in done if (h["final"] or {}).get("contested") and (h["final"] or {}).get("how") in ("glimmer", "spark")]
    for h in split + done:
        return {"job": h["id"], "case": h["case_id"]}
    return {"job": None, "case": E.FEATURED[1]}


@app.get("/api/proof")
def proof():
    return E.proof()


@app.get("/api/corpus")
def corpus_stats():
    return E.corpus_stats()


# ------------------------------------------------------------------ your own videos (product/ingest.py)
YT = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})")


class VideoIn(BaseModel):
    url: str = Field(min_length=11, max_length=300)
    transcriber: str = "youtube"


def _collection(cid: str) -> dict:
    d = E.COLLECTIONS / cid
    steps = [json.loads(l) for l in (d / "progress.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (d / "progress.jsonl").exists() else []
    meta = json.loads((d / "collection.json").read_text(encoding="utf-8")) if (d / "collection.json").exists() else None
    status = "ready" if meta else ("error" if steps and steps[-1]["state"] == "error" else "running")
    return {"id": cid, "status": status, "steps": steps, "collection": meta}


@app.post("/api/collections")
def add_video(body: VideoIn):
    """Index a YouTube video (<= 30 min) as a new collection, in its own process; poll GET /api/collections/<id>.
    Off unless PORTIA_YOUTUBE_LINKS=1: it downloads with yt-dlp, which YouTube's terms do not allow and the
    hackathon disqualifies platform-policy breaches. Uploading a file (/api/collections/upload) stays."""
    import subprocess
    if os.environ.get("PORTIA_YOUTUBE_LINKS", "") != "1":
        raise HTTPException(403, "YouTube links are turned off on this site; upload the video file instead")
    m = YT.search(body.url) or re.fullmatch(r"\s*([A-Za-z0-9_-]{11})\s*", body.url)
    if not m:
        raise HTTPException(400, "paste a YouTube video link")
    if body.transcriber == "muse":
        raise HTTPException(409, "Muse Voice Transcribe needs the Meta Model API key, which is locked; use YouTube captions")
    cid = f"yt-{m.group(1)}"
    st = _collection(cid) if (E.COLLECTIONS / cid).exists() else None
    if st and st["status"] in ("ready", "running"):
        return st
    if st:                                               # a failed attempt: keep it aside, never delete
        import shutil
        dst = E.HERE / "zarxiv_collections" / f"{cid}-{int(time.time())}"
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(E.COLLECTIONS / cid), str(dst))
    (E.COLLECTIONS / cid).mkdir(parents=True, exist_ok=True)
    with open(E.COLLECTIONS / cid / "ingest.log", "a", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, str(HERE / "ingest.py"), cid, f"https://www.youtube.com/watch?v={m.group(1)}"],
                         cwd=str(E.ROOT), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return _collection(cid)


@app.post("/api/collections/upload")
async def upload_video(file: UploadFile = File(...), captions: UploadFile | None = File(None), title: str = Form("")):
    """An uploaded video (<= 30 min, <= 1.5 GB) with optional .vtt/.srt captions: the same pipeline as a YouTube link."""
    import hashlib
    import subprocess
    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
        raise HTTPException(400, "upload a video file (.mp4, .mov, .mkv, .webm)")
    cid = f"up-{time.strftime('%m%d%H%M%S')}-{hashlib.sha1((file.filename or '').encode()).hexdigest()[:4]}"
    src = E.COLLECTIONS / cid / "src"
    src.mkdir(parents=True, exist_ok=True)
    size, limit = 0, MAX_UPLOAD_MB << 20
    with open(src / f"upload{ext}", "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"the file is larger than {MAX_UPLOAD_MB} MB")
            f.write(chunk)
    args = [sys.executable, str(HERE / "ingest.py"), cid, "--file", str(src / f"upload{ext}"),
            "--title", (title or Path(file.filename or "video").stem)[:120]]
    if captions is not None and captions.filename:
        cext = Path(captions.filename).suffix.lower()
        if cext not in (".vtt", ".srt"):
            raise HTTPException(400, "captions must be .vtt or .srt")
        (src / f"captions{cext}").write_bytes(await captions.read())
        args += ["--captions", str(src / f"captions{cext}")]
    with open(E.COLLECTIONS / cid / "ingest.log", "a", encoding="utf-8") as log:
        subprocess.Popen(args, cwd=str(E.ROOT), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return _collection(cid)


@app.get("/api/collections/{cid}/thumb")
def collection_thumb(cid: str):
    p = E.COLLECTIONS / cid / "thumb.jpg"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", cid) or not p.exists():
        raise HTTPException(404, "no thumbnail")
    return FileResponse(p)


@app.get("/api/collections")
def collections():
    out = [_collection(d.name) for d in sorted(E.COLLECTIONS.glob("*")) if d.is_dir()]
    return {"collections": out, "muse_transcribe": False}


@app.get("/api/collections/{cid}")
def collection(cid: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", cid) or not (E.COLLECTIONS / cid).exists():
        raise HTTPException(404, "no such video")
    st = _collection(cid)
    if st["status"] == "ready" and st["collection"]["domain"] not in E.corpus_stats():
        E.install_collections()                          # a new video becomes searchable right away
    return st


@app.get("/api/footage/{domain}")
def footage(domain: str):
    """Every searchable video of one collection with its length, in playlist order: the search map's ground."""
    f = E.footage(domain)
    if not f:
        raise HTTPException(404, "no such collection")
    return f


@app.get("/api/titles/{domain}")
def titles(domain: str):
    """video id -> title for one collection (tool calls name videos by id)."""
    return {vid: t for vid, (t, _, dom) in E.corpus.titles().items() if dom == domain}


# ------------------------------------------------------------------ jobs
class Custom(BaseModel):
    domain: str
    question: str = Field(min_length=8, max_length=4000)
    answer_a: str = Field(min_length=8, max_length=8000)
    answer_b: str = Field(min_length=8, max_length=8000)


class Single(BaseModel):
    domain: str
    question: str = Field(min_length=8, max_length=4000)
    answer: str = Field(min_length=8, max_length=8000)


class JobIn(BaseModel):
    case_id: str | None = None
    custom: Custom | None = None
    single: Single | None = None                         # check one answer (plan 016): Portia writes the variant
    agents: int = 3
    resolve: str = "glimmer"
    quick: bool = False                                  # 4 turns per investigator instead of 8


@app.post("/api/jobs")
def create_job(body: JobIn):
    _busy()
    if body.agents not in (1, 3) or body.resolve not in ("glimmer", "spark", "spark13", "spark13all", "vote"):
        raise HTTPException(400, "agents must be 1 or 3; resolve must be glimmer, spark, spark13, spark13all or vote")
    if body.resolve == "spark" and not E.spark_status()["available"]:
        raise HTTPException(409, "Muse Spark Open is not available (locked key or budget reached)")
    if body.resolve in ("spark13", "spark13all") and not E.spark13_status()["available"]:
        raise HTTPException(409, "Muse Spark 1.3 (Meta Model API) is not available (locked key or budget reached)")
    if body.case_id:
        c = E.library().get(body.case_id)
        if not c:
            raise HTTPException(404, "no such case")
        cid = body.case_id
    elif body.custom:
        if body.custom.domain not in E.corpus_stats():
            raise HTTPException(400, "unknown domain")
        c = E.custom_case(body.custom.domain, body.custom.question, body.custom.answer_a, body.custom.answer_b)
        cid = c.qid
    elif body.single:
        if body.single.domain not in E.corpus_stats():
            raise HTTPException(400, "unknown domain")
        if body.agents != 3:
            raise HTTPException(400, "checking one answer needs three investigators")
        c = E.custom_case(body.single.domain, body.single.question, body.single.answer.strip(), "")
        cid = c.qid
        return {"id": E.start(cid, c, {"agents": 3, "resolve": body.resolve, "quick": body.quick, "single": True})}
    else:
        raise HTTPException(400, "give a case_id or a custom case")
    return {"id": E.start(cid, c, {"agents": body.agents, "resolve": body.resolve, "quick": body.quick})}


class BatchItem(BaseModel):
    case_id: str | None = None
    domain: str | None = None
    question: str | None = Field(default=None, max_length=4000)
    answer_a: str | None = Field(default=None, max_length=8000)
    answer_b: str | None = Field(default=None, max_length=8000)


class BatchIn(BaseModel):
    name: str = Field(default="", max_length=120)
    items: list[BatchItem]
    agents: int = 3
    resolve: str = "glimmer"
    quick: bool = False


@app.post("/api/batches")
def create_batch(body: BatchIn):
    """Plan 016: a batch audit, one job per item (at most 100)."""
    if not 1 <= len(body.items) <= MAX_BATCH:
        raise HTTPException(400, f"a batch takes 1 to {MAX_BATCH} items")
    _busy(len(body.items))
    if body.agents not in (1, 3) or body.resolve not in ("glimmer", "spark", "spark13", "spark13all", "vote"):
        raise HTTPException(400, "agents must be 1 or 3; resolve must be glimmer, spark, spark13, spark13all or vote")
    if body.resolve == "spark" and not E.spark_status()["available"]:
        raise HTTPException(409, "Muse Spark Open is not available (locked key or budget reached)")
    if body.resolve in ("spark13", "spark13all") and not E.spark13_status()["available"]:
        raise HTTPException(409, "Muse Spark 1.3 (Meta Model API) is not available (locked key or budget reached)")
    lib, domains = E.library(), E.corpus_stats()
    items = []
    for i, it in enumerate(body.items, 1):
        if it.case_id:
            if it.case_id not in lib:
                raise HTTPException(400, f"row {i}: no library case {it.case_id!r}")
            items.append({"case_id": it.case_id})
        else:
            if it.domain not in domains:
                raise HTTPException(400, f"row {i}: unknown collection {it.domain!r}")
            if min(len((it.question or "").strip()), len((it.answer_a or "").strip()), len((it.answer_b or "").strip())) < 8:
                raise HTTPException(400, f"row {i}: the question and both answers need at least 8 characters")
            items.append({"domain": it.domain, "question": it.question.strip(), "answer_a": it.answer_a.strip(), "answer_b": it.answer_b.strip()})
    return {"id": E.start_batch(body.name.strip(), items, {"agents": body.agents, "resolve": body.resolve, "quick": body.quick})}


@app.get("/api/batches")
def list_batches():
    return {"batches": E.batches()}


@app.get("/api/batches/{bid}")
def get_batch(bid: str):
    b = E.batch_status(bid)
    if not b:
        raise HTTPException(404, "no such batch")
    return b


@app.get("/api/batches/{bid}/export.csv")
def export_batch(bid: str):
    import csv
    import io
    from fastapi.responses import Response
    b = E.batch_status(bid)
    if not b:
        raise HTTPException(404, "no such batch")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["row", "status", "case_id", "collection", "question", "answer_a", "answer_b", "verdict", "how", "trust",
                "trust_dev_pct", "wall_s", "api_usd", "job"])
    for i, r in enumerate(b["rows"], 1):
        f, tr = r.get("final") or {}, r.get("trust") or {}
        w.writerow([i, r.get("status"), r.get("case_id"), r.get("domain"), r.get("question"), r.get("answer_a"), r.get("answer_b"),
                    f.get("verdict"), f.get("how"), tr.get("level"), tr.get("pct"), f.get("wall"),
                    round(((f.get("usage") or {}).get("spark_usd") or 0), 5), r.get("job")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="portia_{bid}.csv"'})


@app.get("/api/jobs")
def jobs():
    return {"jobs": E.history()}


@app.get("/api/jobs/{jid}")
def job(jid: str):
    if not JOB_ID.match(jid) or not (E.JOBS / jid / "job.json").exists():
        raise HTTPException(404, "no such job")
    meta = json.loads((E.JOBS / jid / "job.json").read_text(encoding="utf-8"))
    return {**E.with_kind(meta), "done": E.is_done(jid)}


@app.get("/api/jobs/{jid}/evidence.mp4")
def evidence_clip(jid: str):
    """The verdict's cited moments as one short clip (plan 016), cut on first request and cached."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{6}-[0-9a-f]{4}", jid) or not (E.JOBS / jid / "job.json").exists():
        raise HTTPException(404, "no such job")
    p = E.evidence_clip(jid)
    if not p:
        raise HTTPException(404, "this verdict cites no moments that can be cut")
    return FileResponse(p, media_type="video/mp4", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/jobs/{jid}/events.json")
def job_events_all(jid: str):
    """Every event of a job at once (the UI's paced replay of a recorded run)."""
    if not JOB_ID.match(jid) or not (E.JOBS / jid).exists():
        raise HTTPException(404, "no such job")
    evs, done = E.events(jid, 0)
    return {"events": evs, "done": done}


@app.get("/api/jobs/{jid}/events")
async def job_events(jid: str, request: Request, start: int = 0):
    if not JOB_ID.match(jid) or not (E.JOBS / jid).exists():
        raise HTTPException(404, "no such job")

    last = request.headers.get("last-event-id")
    if last and last.isdigit():                          # a reconnecting browser resumes after the last event it got
        start = int(last) + 1

    async def gen():
        i = max(0, start)
        while True:
            if await request.is_disconnected():
                return
            evs, done = E.events(jid, i)
            for ev in evs:
                yield {"id": str(ev["i"]), "data": json.dumps(ev, ensure_ascii=False)}
            i += len(evs)
            if done and not evs:
                return
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen(), ping=15)


@app.get("/media/{jid}/{name}")
def media(jid: str, name: str):
    p = E.JOBS / jid / "img" / name
    if not JOB_ID.match(jid) or not IMG.match(name) or not p.exists():
        raise HTTPException(404, "no such image")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.exception_handler(Exception)
async def oops(request: Request, exc: Exception):
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5250)
    a = ap.parse_args()
    E.JOBS.mkdir(parents=True, exist_ok=True)
    E.COLLECTIONS.mkdir(parents=True, exist_ok=True)
    E.library()                                      # load the cases before the first request
    E.install_collections()
    print(f"[portia] http://{a.host}:{a.port}", flush=True)
    # open event streams must not hold a restart: give them 3 s, then close
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning", timeout_graceful_shutdown=3)
