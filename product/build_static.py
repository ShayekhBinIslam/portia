#!/usr/bin/env python3
"""portia/product/build_static.py: Portia's static gallery for GitHub Pages: recorded investigations, no server needed.

    python product/build_static.py [--live https://...] [--out product/site]

The judges cannot reach our GPUs, so the gallery replays recorded runs in the browser (the same app in static mode,
window.PORTIA_STATIC). It exports:
  * the app (static/index.html with relative paths, app.js, style.css);
  * the library (220 development cases: questions, answers, answer keys), the proof numbers, corpus stats, titles;
  * for every library case with a finished run of the default setup (three agents, Glimmer adjudicator) or of
    "Spark 1.3 checks every verdict", its latest run: the job, its events and its images (re-encoded at 960 px, JPEG
    quality 78, to keep the site light).
An existing output folder is moved to product/zarxiv_site/<time>/ first (nothing is deleted).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", default="", help="the live app's public URL, shown as a link (optional)")
    ap.add_argument("--out", default=str(HERE / "site"))
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        dst = HERE / "zarxiv_site" / time.strftime("%m%d-%H%M%S")
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(out), str(dst))
    (out / "static").mkdir(parents=True)
    # the app, in static mode
    html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    cfg = json.dumps({"live": a.live})
    html = html.replace('<script src="static/app.js"></script>', f'<script>window.PORTIA_STATIC = {cfg};</script>\n  <script src="static/app.js"></script>')
    (out / "index.html").write_text(html, encoding="utf-8")
    for f in ("app.js", "style.css"):
        shutil.copy(HERE / "static" / f, out / "static" / f)
    shutil.copytree(HERE / "static" / "brand", out / "static" / "brand")      # the logo, favicon and share image
    (out / ".nojekyll").write_text("", encoding="utf-8")       # GitHub Pages: serve the files as they are
    # the library, proof and corpus
    lib = E.library()
    d = out / "data"
    write(d / "library.json", {"cases": [{**E.case_json(cid, c, full=False), "question": c.question[:260]} for cid, c in lib.items()],
                               "featured": E.FEATURED, "domains": sorted({c.domain for c in lib.values()})})
    stats = {k: v for k, v in E.corpus_stats().items() if not k.startswith("Your video:")}
    write(d / "corpus.json", stats)
    write(d / "proof.json", E.proof())
    write(d / "health.json", {"servers": [], "encoder": False, "spark": {"available": False}})
    write(d / "collections.json", {"collections": [], "muse_transcribe": False})
    titles = E.corpus.titles()
    for dom in stats:
        write(d / "titles" / f"{dom}.json", {vid: t for vid, (t, _, dm) in titles.items() if dm == dom})
        write(d / "footage" / f"{dom}.json", E.footage(dom))
    for cid, c in lib.items():
        write(d / "case" / f"{cid}.json", E.case_json(cid, c))
        write(d / "truth" / f"{cid}.json", E.truth(c))
    # recorded runs: the latest finished default-setup run of each library case
    latest = {}
    for h in E.history(10000):
        cfg_ = h.get("config") or {}
        if h["case_id"] in lib and h.get("final") and not h.get("running") and cfg_.get("agents") == 3 \
                and cfg_.get("resolve") in ("glimmer", "spark13all") and not cfg_.get("quick"):
            # the standard setup, or Spark 1.3 checking every verdict (plan 014); the newest run of a case wins
            latest.setdefault(h["case_id"], h)                  # history is newest first
    # finished batch audits of library cases (plan 016), and every run they link to
    batch_list, extra = [], {}
    for bm in E.batches():
        st = E.batch_status(bm["id"])
        if st and st["rows"] and all(r.get("status") == "done" and r.get("case_id") in lib for r in st["rows"]):
            write(d / "batch" / f"{bm['id']}.json", st)
            batch_list.append({**bm, "done": len(st["rows"])})
            for r in st["rows"]:
                extra.setdefault(r["job"], next((h for h in E.history(10000) if h["id"] == r["job"]), None))
    write(d / "batches.json", {"batches": batch_list[:4]})
    for h in E.history(10000):                          # the demo runs of new (non-library) questions, e.g. the demo's
        if h["id"] in E.SHOWCASE and h.get("final"):
            extra.setdefault(h["id"], h)
    runs = list(latest.values()) + [h for jid_, h in extra.items() if h and jid_ not in {x["id"] for x in latest.values()}]
    jobs, n_img, size = [], 0, 0
    for h in runs:
        jid = h["id"]
        evs, _ = E.events(jid, 0)
        write(d / "events" / f"{jid}.json", {"events": evs, "done": True})
        meta = json.loads((E.JOBS / jid / "job.json").read_text(encoding="utf-8"))
        clip = None
        if h.get("case_id") in E.FEATURED or jid == E.DEMO_JOB or jid in E.SHOWCASE:     # evidence clips, plan 016
            try:
                clip = E.evidence_clip(jid)
            except Exception as ex:                       # a clip is a bonus; never fail the build over it
                print(f"[gallery] no clip for {jid}: {ex}")
            if clip:
                (out / "media" / jid).mkdir(parents=True, exist_ok=True)
                shutil.copy(clip, out / "media" / jid / "evidence.mp4")
        write(d / "job" / f"{jid}.json", {**E.with_kind(meta), "done": True, "clip": bool(clip)})
        jobs.append(h)
        for img in sorted((E.JOBS / jid / "img").glob("*.jpg")):
            im = Image.open(img).convert("RGB")
            im.thumbnail((960, 960))
            dst = out / "media" / jid / img.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            im.save(dst, quality=78)
            n_img += 1
            size += dst.stat().st_size
    write(d / "jobs.json", {"jobs": [h for h in jobs if h["id"] in {x["id"] for x in latest.values()}]})
    split = [h for h in jobs if (h["final"] or {}).get("contested") and h["case_id"] in E.FEATURED]
    pinned = [h for h in jobs if h["id"] == E.DEMO_JOB]
    demo = (pinned or split or [h for h in jobs if h["case_id"] in E.FEATURED] or jobs or [None])[0]
    write(d / "demo.json", {"job": demo and demo["id"], "case": demo["case_id"] if demo else E.FEATURED[1], "upload_job": E.UPLOAD_DEMO_JOB})
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"[gallery] {out}: {len(lib)} cases, {len(jobs)} recorded runs ({len(batch_list)} batches), {n_img} images ({size / 1e6:.0f} MB), "
          f"{total / 1e6:.0f} MB in all{f'; live link {a.live}' if a.live else ''}")


if __name__ == "__main__":
    main()
