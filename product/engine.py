"""portia/product/engine.py: Portia's pipeline: three Muse Glimmer investigators, then an adjudicator on disagreement.

The research code runs unchanged (judge.agent.judge, judge.adjudicate.adjudicate). Two thin layers record what the UI
shows: TracedClient logs each model turn (reasoning, text, tool calls, tokens, latency) and TracedToolbox saves every
image a tool returns. Both find their job through a context variable set at the start of each worker thread.

Library cases are the 220 development contests (shards 3-4; held-out shards are never offered). They run with the exact
settings of the logged tuned-v4 runs (seeds 0-2) and of the evidence-only adjudications (plans 004 and 006), so their
requests are byte-identical and replay from the response caches: a demo is fast and costs nothing.
"""
from __future__ import annotations

import base64
import contextvars
import hashlib
import difflib
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "analysis"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from judge import adjudicate as ADJ                   # noqa: E402
from judge import agent as AG                         # noqa: E402
from judge import corpus, meta_lock                   # noqa: E402
from judge import tools as TOOLS                      # noqa: E402
from judge.contests import Contest, load_contests     # noqa: E402
from judge.embed_client import QueryEncoder           # noqa: E402
from judge.local_client import LocalClient            # noqa: E402
from judge.config import load as config               # noqa: E402

HERE = Path(__file__).resolve().parent
JOBS = HERE / "jobs"
BATCHES = HERE / "batches"                     # plan 016: batch audits (one job per item, see start_batch)
# settings: configs/models.yaml, budgets.yaml, agent.yaml, product.yaml and proof.yaml (the environment overrides some)
_M, _B, _A, _P = config("models"), config("budgets"), config("agent"), config("product")
MODEL = os.environ.get("PORTIA_GLIMMER_MODEL", _M["muse_glimmer"]["served_name"])   # "mg30" on our vLLM + DFlash servers
# the investigators' Muse Glimmer servers: (OpenAI-compatible URL, the label the app shows). Default: the two servers on
# our own GPUs (scripts/serve_muse.sh). A hosted deployment (Modal Endpoint or Fireworks, its key in PORTIA_GLIMMER_KEY):
# PORTIA_GLIMMER_SERVERS='[["<endpoint URL>/v1", "Modal"]]'
SERVERS = [tuple(x) for x in (json.loads(os.environ["PORTIA_GLIMMER_SERVERS"]) if os.environ.get("PORTIA_GLIMMER_SERVERS")
                              else _M["muse_glimmer"]["servers"])]
LIBRARY_SHARDS = list(_P["library_shards"])          # development shards only
AGENT_KW = dict(_A["investigator"])                  # the tuned agent (configs/agent.yaml)
QUICK = dict(_A["quick"])                            # the "Quick" effort; TRACK_QUICK must match it
SPARK_BUDGET = float(os.environ.get("PORTIA_SPARK_BUDGET_USD", _B["baseten"]["product_budget_usd"]))   # Baseten spend in total
PRICE = dict(_M["muse_spark_open"]["price"])         # Baseten, USD per token
PRICE_META = dict(_M["muse_spark_13"]["price"])      # Muse Spark 1.3 Contributor, Meta Model API
META_BUDGET = float(os.environ.get("PORTIA_META_BUDGET_USD", _B["meta_api"]["product_budget_usd"]))   # the product's share
# How often each kind of verdict was right on the development shards (220 contests x 5 investigator triples; plans
# 004-006; analysis/spark_qualitative.py). Shown as the verdict's track record, not as a probability for this case.
TRACK = {"single": (72.9, "one tuned Muse Glimmer agent, mean of 11 seeds"),
         "unanimous": (79.6, "the three investigators agreed (818 dev cases)"),
         "vote": (57.8, "split decided by the majority (282 dev cases)"),
         "glimmer": (62.6, "split decided by the Muse Glimmer adjudicator (282 dev cases)"),
         "spark": (83.0, "split decided by the Muse Spark Open adjudicator (282 dev cases)"),
         "spark13": (76.6, "split decided by the Muse Spark 1.3 Contributor adjudicator, Meta Model API (282 dev cases)"),
         # plan 014: Spark 1.3 also re-checks agreed verdicts (4 investigator triples, 647 unanimous dev cases)
         "s13_confirm": (86.9, "the three investigators agreed and Muse Spark 1.3 confirmed it (559 dev cases)"),
         "s13_overturn": (67.0, "the three investigators agreed but Muse Spark 1.3 overturned them (88 dev cases)")}
# "Quick" = 4 turns per investigator (plan 009 E4): about 40% less compute, measured on the development set:
# one agent 70.9% (3 seeds per shard); the 4-turn jury (seeds 0-2): unanimous 77.8%, splits 59.7% (vote) and 62.9%
# (Glimmer adjudicator). Spark Open has not been measured over 4-turn investigators: its number is the 8-turn one.
# Quick = 6 turns, medium reasoning: 3 investigator triples, 2 Glimmer samples where done (analysis/mode_track.py)
TRACK_QUICK = {"single": (71.2, "one Quick Muse Glimmer agent (6 turns, medium reasoning), 9 seeds on the dev set"),
               "unanimous": (78.3, "three Quick investigators agreed (dev set)"),
               "vote": (52.9, "split of Quick investigators decided by the majority (dev set)"),
               "glimmer": (58.7, "split of Quick investigators decided by the Muse Glimmer adjudicator (dev set)"),
               "spark": (83.0, "split decided by Muse Spark Open (measured with 8-turn investigators)"),
               "spark13": (76.6, "split decided by Muse Spark 1.3 (measured with 8-turn investigators)"),
               "s13_confirm": (86.9, "agreed and confirmed by Muse Spark 1.3 (measured with 8-turn investigators)"),
               "s13_overturn": (67.0, "agreed but overturned by Muse Spark 1.3 (measured with 8-turn investigators)")}
SHOWCASE = list(_P["showcase"])                # runs of new questions the gallery and the demo footage show
# an uploaded film, Blender's Tears of Steel (CC BY 3.0), transcribed by Muse Voice Transcribe; its frames may be shown
UPLOAD_DEMO_JOB = _P["upload_demo_job"]
DEMO_JOB = _P["demo_job"]                      # the home page's "Watch a case": case 038, three agents read the wrong
                                               # notebook page ("ears"); Spark 1.3 checked the page before it (cubes)
                                               # from another video, Spark 1.3 re-checks and overturns them (right)
FEATURED = list(_P["featured"])

_CTX: contextvars.ContextVar = contextvars.ContextVar("portia", default=None)      # (job, role) of this worker thread
MAX_JOBS = int(os.environ.get("PORTIA_MAX_JOBS", _P["limits"]["max_jobs"]))     # live jobs at once


# ------------------------------------------------------------------ your own videos (product/ingest.py)
COLLECTIONS = HERE / "collections"
_ORIG: dict = {}


def install_collections() -> list[dict]:
    """Register every ready ingested video with the corpus, so the unchanged tools search it as its own collection
    (domain "Your video: <title>"). Safe to call again after a new ingestion finishes."""
    cols = []
    for f in sorted(COLLECTIONS.glob("*/collection.json")):
        try:
            cols.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    if not _ORIG:
        _ORIG.update(database=corpus.database, index=corpus.index)
    by_pl = {c["playlist"]: c for c in cols}

    def database() -> dict:
        db = dict(_ORIG["database"]())
        for c in cols:
            db[c["domain"]] = {c["playlist"]: [{"id": c["vid"], "title": c["title"], "duration_formatted": c["duration_formatted"],
                                                "chunk_index": 0, "chunk_start": 0, "chunk_end": int(c["duration"]), "link": c["url"]}]}
        return db

    @lru_cache(maxsize=64)
    def index(playlist: str) -> dict:
        c = by_pl.get(playlist)
        if not c:
            return _ORIG["index"](playlist)
        from safetensors.numpy import load_file
        d = COLLECTIONS / c["id"]
        segs = json.loads((d / "index.json").read_text(encoding="utf-8"))["segments"]
        for i, s in enumerate(segs):
            s["playlist"], s["row"], s["handle"] = playlist, i, f"{s['vid']}@{int(s['start'])}"
        return {"emb": load_file(str(d / "index.safetensors"))["embeddings"].astype(np.float32), "segs": segs}

    corpus.database, corpus.index = database, index
    corpus.titles.cache_clear()
    corpus_stats.cache_clear()
    return cols


# ------------------------------------------------------------------ cases
@lru_cache(maxsize=1)
def library() -> dict:
    """case id -> Contest, for the development shards (ids as in the trace explorer: shard_position)."""
    out = {}
    for sh in LIBRARY_SHARDS:
        for i, c in enumerate(load_contests([sh])):
            out[f"{sh}_{i:03d}"] = c
    return out


def _playlist_title(pl: str) -> str:
    """'PLJkFQFIbKqtgUJ3ZN-OZ8TtrAOpJ37tWm_Wonders of the World' -> 'Wonders of the World' (YouTube ids are 34 chars)."""
    m = re.match(r"^PL[A-Za-z0-9_-]{32}_(.+)$", pl)
    return (m.group(1) if m else pl.split("_", 1)[-1]).strip()


@lru_cache(maxsize=1)
def corpus_stats() -> dict:
    """Per domain: playlists, distinct videos and hours of footage the agents can search (the segment index the tools
    search, which holds some videos the QA database does not list)."""
    out = {}
    for dom, pls in corpus.database().items():
        f = footage(dom) or {"videos": [], "hours": 0.0}
        out[dom] = {"playlists": [(pls[pl][0].get("title") if pl.startswith("yt_") and pls[pl] else _playlist_title(pl)) for pl in sorted(pls)],
                    "videos": len(f["videos"]), "hours": f["hours"]}
    return out


_FOOTAGE: dict = {}


def footage(domain: str) -> dict | None:
    """A domain's searchable footage, for the search map (plan 017): every indexed video in playlist order with its
    length in seconds, read from the segment lists (not the vectors)."""
    if domain in _FOOTAGE:
        return _FOOTAGE[domain]
    pls = corpus.domain_playlists(domain)
    if not pls:
        return None
    own = {}                                             # an ingested video keeps its segment list in its collection
    for f in COLLECTIONS.glob("*/collection.json"):
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
            own[c["playlist"]] = COLLECTIONS / c["id"] / "index.json"
        except (OSError, json.JSONDecodeError, KeyError):
            continue
    titles, vids = corpus.titles(), {}
    for p, pl in enumerate(pls):
        try:
            segs = json.loads((own.get(pl) or corpus.INDEX / f"{corpus._key(pl)}.json").read_text(encoding="utf-8"))["segments"]
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        for s in segs:
            v = vids.setdefault(s["vid"], {"id": s["vid"], "title": titles.get(s["vid"], ("",))[0], "pl": p, "dur": 0})
            v["dur"] = max(v["dur"], int(s["end"]))
    if not vids:
        return None
    out = {"domain": domain, "seg": 30, "playlists": [_playlist_title(pl) for pl in pls], "videos": list(vids.values()),
           "hours": round(sum(v["dur"] for v in vids.values()) / 3600, 1)}
    _FOOTAGE[domain] = out
    return out


def diff_spans(a: str, b: str) -> tuple[list, list]:
    """Word-level differences between the answers: [[text, changed, factual], ...] for each side. A changed span is
    factual when the edit touches content (numbers, colours, names, objects: _fact_score >= 2); rewording of filler
    words is marked as changed but not factual, so the page can mark it lightly."""
    wa, wb = a.split(), b.split()
    sa, sb = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        fact = op != "equal" and _fact_score(wa[i1:i2]) + _fact_score(wb[j1:j2]) >= 2
        if i2 > i1:
            sa.append([" ".join(wa[i1:i2]), op != "equal", fact])
        if j2 > j1:
            sb.append([" ".join(wb[j1:j2]), op != "equal", fact])
    return sa, sb


def truth(c: Contest) -> dict:
    """The dataset's ground truth: which answer is the better one, and what was changed in the worse one."""
    from tool_failures import differing_details
    better, worse = c.pair.split("_vs_")
    label = {better: c.good_side, worse: "B" if c.good_side == "A" else "A"}
    changes = [{"answer": label.get(d["side"], "?"), "worse": d["side"] == worse, "what": d.get("element") or "",
                "kind": d.get("attribute") or ""} for d in differing_details(c.rec, c.pair)]
    kind = "original vs edited" if better == "gold" else "two edited versions (fewer vs more changes)"
    return {"better": c.good_side, "pair": kind, "changes": changes}


_STOP = set("""a an the and or but plus of to in on at by for with from into onto over under as is are was were be been being
this that these those it its their his her they them he she which who whom whose while where when then than also both each
very more most less least such only just even still so too do does did done has have had not no nor can could may might
will would should shall must about across after before during through between among within without upon toward towards
delves explores examines discusses describes shows highlights notes says states presents depicts offers focuses""".split())
_COLOURS = set("red blue green white black yellow orange purple pink brown grey gray silver gold golden beige teal navy".split())


def _fact_score(ws: list) -> int:
    """How much a span of words says about facts: content words count 1, numbers and colours 2 more, names 1 more."""
    s = 0
    for w in ws:
        k = re.sub(r"[^\w]+", "", w.lower())
        if not k or k in _STOP:
            continue
        s += 1 + 2 * any(ch.isdigit() for ch in k) + 2 * (k in _COLOURS) + (w[:1].isupper() and len(k) > 2)
    return s


@lru_cache(maxsize=1024)
def disputed(a: str, b: str, n: int = 2, words: int = 7) -> list:
    """The most telling places where the two answers differ, as short [A phrase, B phrase] pairs: edits that change
    facts (numbers, colours, names, objects) rank first; punctuation-only and filler-word rewordings are skipped."""
    wa, wb = a.split(), b.split()
    norm = lambda s: re.sub(r"[^\w]+", "", s.lower())                                      # noqa: E731
    cut = lambda ws: (" ".join(ws[:words]).rstrip(".,;:") + (" …" if len(ws) > words else ""))   # noqa: E731
    score = _fact_score

    cands = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_opcodes():
        if op == "equal" or norm(" ".join(wa[i1:i2])) == norm(" ".join(wb[j1:j2])):
            continue
        sc = score(wa[i1:i2]) + score(wb[j1:j2])
        if sc >= 2 and (i2 - i1) + (j2 - j1) <= 40:              # long rewrites are paraphrase, not one disputed detail
            cands.append((sc, i1, [cut(wa[i1:i2]) or "(nothing)", cut(wb[j1:j2]) or "(nothing)"]))
    picked, seen = [], set()
    for c in sorted(cands, key=lambda x: -x[0]):                                    # the top n distinct pairs
        if tuple(c[2]) not in seen:
            seen.add(tuple(c[2]))
            picked.append(c)
        if len(picked) >= n:
            break
    return [p for _, _, p in picked]                                                 # the most telling first


# plan 019: what the answers dispute. On the development set the local jury reads quoted words and on-screen text, and
# positions, worst: when the investigators agree on their own they are right 58.3% (text, 11 contests) and 69.4%
# (positions, 6 contests) of the time, against 86.7-94.5% for counts, colours and objects (17 triples). Portia never
# calls such a verdict "safe to accept" (static/app.js trustFor).
_QUOTED = re.compile(r"(?:^|[\s(])['\"\u201c\u2018]([^'\"\u201d\u2019]{2,60})['\"\u201d\u2019]")
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_TEXTW = re.compile(r"\b(text labels?|labelled|labeled|sign reads|reads|written|caption|logo|lettering|inscription|"
                    r"handwritten|font|banner|title card|on-screen)\b", re.I)
_NUM = re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|single|pair|several|"
                  r"multiple|both)\b", re.I)
_COL = re.compile(r"\b(red|blue|green|yellow|orange|purple|pink|black|white|grey|gray|brown|golden|gold|silver|beige|maroon|"
                  r"navy|teal|cyan|violet|crimson|emerald|turquoise)\b", re.I)
_POS = re.compile(r"\b(left|right|above|below|behind|front|beside|top|bottom|upper|lower|center|centre|middle|corner|"
                  r"next to|adjacent|between)\b", re.I)


def dispute_kind(a: str, b: str) -> str:
    """text | count | colour | position | object: the kind of detail the two answers disagree on."""
    s = " ".join(x + " " + y for x, y in disputed(a, b, n=3))
    if _QUOTED.search(" " + s) or _CJK.search(s) or _TEXTW.search(s):
        return "text"
    for kind, rx in (("count", _NUM), ("colour", _COL), ("position", _POS)):
        if rx.search(s):
            return kind
    return "object"


def with_kind(meta: dict) -> dict:
    """A job's stored metadata with its case's dispute kind (runs recorded before plan 019 lack it)."""
    c = meta.get("case") or {}
    if "kind" not in c and c.get("answer_a") and c.get("answer_b"):
        meta = {**meta, "case": {**c, "kind": dispute_kind(c["answer_a"], c["answer_b"])}}
    return meta


@lru_cache(maxsize=1)
def glosses() -> dict:
    """case id -> the question shortened to one plain line by Muse Glimmer (product/gloss_questions.py)."""
    p = Path(__file__).resolve().parent / "glosses.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def case_json(cid: str, c: Contest, full: bool = True) -> dict:
    out = {"id": cid, "domain": c.domain, "question": c.question, "gloss": glosses().get(cid), "library": cid in library(),
           "featured": cid in FEATURED, "disputed": disputed(c.answer_a, c.answer_b),
           "kind": dispute_kind(c.answer_a, c.answer_b)}
    if full:
        da, db = diff_spans(c.answer_a, c.answer_b)
        out.update({"answer_a": c.answer_a, "answer_b": c.answer_b, "diff_a": da, "diff_b": db,
                    "haystack": corpus_stats().get(c.domain)})
    return out


def custom_case(domain: str, question: str, answer_a: str, answer_b: str) -> Contest:
    import hashlib
    h = hashlib.sha1(f"{domain}\n{question}\n{answer_a}\n{answer_b}".encode()).hexdigest()[:10]
    return Contest(qid=f"custom-{h}", pair="custom", occurrence=0, shard="custom", domain=domain, playlist="", gap=0,
                   question=question.strip(), answer_a=answer_a.strip(), answer_b=answer_b.strip(), good_side="?")


# ------------------------------------------------------------------ tracing
def _label(ts) -> str:
    return corpus.mmss(ts) if isinstance(ts, (int, float)) else str(ts or "")


class TracedToolbox(TOOLS.Toolbox):
    """The research Toolbox; every call it runs inside a job is also recorded with its images."""

    def run(self, name: str, args: dict):
        text, imgs = super().run(name, args)
        ctx = _CTX.get()
        if ctx:
            job, role = ctx
            job.tool(role, name, args, text, imgs)
        return text, imgs


AG.Toolbox = TracedToolbox                         # judge.agent and judge.adjudicate build their Toolbox by these names
ADJ.Toolbox = TracedToolbox


class TracedClient:
    """Delegates to the real client and records each turn."""

    def __init__(self, inner, job: "Job", role: str, first_look: bool = True):
        self.inner, self.job, self.role, self.first_look, self.n = inner, job, role, first_look, 0

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def chat(self, messages: list, tools=None, tool_choice=None, **params) -> dict:
        if self.n == 0 and self.first_look:
            self.job.first_images(self.role, messages)
        t = time.time()
        self.job.status(self.role, "thinking", self.n)
        resp = self.inner.chat(messages, tools=tools, tool_choice=tool_choice, **params)
        self.job.turn(self.role, self.n, resp, time.time() - t)
        self.n += 1
        return resp


# ------------------------------------------------------------------ jobs
@dataclass
class Job:
    id: str
    case_id: str
    contest: Contest
    config: dict
    events: list = field(default_factory=list)
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    n_img: int = 0
    usage: dict = field(default_factory=lambda: {"glimmer_in": 0, "glimmer_out": 0, "spark_usd": 0.0, "spark_cached": 0})

    @property
    def dir(self) -> Path:
        return JOBS / self.id

    def emit(self, ev: dict):
        with self.lock:
            ev = {"i": len(self.events), "t": round(time.time(), 2), **ev}
            self.events.append(ev)
            with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def save_img(self, im, role: str) -> str:
        with self.lock:
            self.n_img += 1
            name = f"{role}_{self.n_img:04d}.jpg"
        im = im.convert("RGB")
        im.thumbnail((1600, 1600))
        im.save(self.dir / "img" / name, quality=86)
        return f"/media/{self.id}/{name}"

    def status(self, role: str, state: str, step: int):
        self.emit({"type": "status", "role": role, "state": state, "step": step})

    def tool(self, role: str, name: str, args: dict, text: str, imgs: list):
        shots = [{"src": self.save_img(im, role), "label": _label(ts)} for im, ts in imgs]
        self.emit({"type": "tool", "role": role, "tool": name, "args": args, "text": (text or "")[:6000], "images": shots})

    def turn(self, role: str, step: int, resp: dict, dt: float):
        ch = (resp.get("choices") or [{}])[0]
        m = ch.get("message") or {}
        calls = []
        for c in m.get("tool_calls") or []:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"raw": fn.get("arguments")}
            calls.append({"name": fn.get("name"), "args": args})
        u = resp.get("usage") or {}
        pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
        cached_t = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
        api = role == "adj" and self.config.get("resolve") in ("spark", "spark13", "spark13all")   # all paid adjudicators
        price = PRICE_META if self.config.get("resolve") in ("spark13", "spark13all") else PRICE
        replay = dt < 0.75                                  # served from the response cache
        usd = 0.0
        with self.lock:
            if api:
                usd = 0.0 if replay else (pt - cached_t) * price["in"] + cached_t * price["cached"] + ct * price["out"]
                self.usage["spark_usd"] += usd
            else:
                self.usage["glimmer_in"] += pt
                self.usage["glimmer_out"] += ct
        self.emit({"type": "turn", "role": role, "step": step, "reasoning": (m.get("reasoning") or "")[:16000],
                   "content": (m.get("content") or "")[:6000], "calls": calls, "finish": ch.get("finish_reason"),
                   "tokens": {"in": pt, "out": ct}, "latency": round(dt, 1), "replay": replay, "usd": round(usd, 4)})

    def first_images(self, role: str, messages: list):
        """The images pinned in an agent's first message: its overview of the most relevant footage."""
        user = next((m for m in messages if m.get("role") == "user"), None)
        parts = (user or {}).get("content")
        if not isinstance(parts, list):
            return
        shots = []
        for p in parts:
            url = ((p.get("image_url") or {}).get("url") or "") if p.get("type") == "image_url" else ""
            if url.startswith("data:image"):
                try:
                    shots.append({"src": self.save_img(Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))), role),
                                  "label": f"overview {len(shots) + 1}"})
                except Exception:
                    pass
        if shots:
            self.emit({"type": "first_look", "role": role, "images": shots})

    def log(self, *m):
        with open(self.dir / "run.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in m) + "\n")


_ENC = None


def encoder() -> QueryEncoder:
    global _ENC
    if _ENC is None:
        _ENC = QueryEncoder(log=lambda *m: None)
    return _ENC


def spark_status() -> dict:
    """Whether the optional Muse Spark Open adjudicator can run; the key itself never leaves judge/meta_lock.py."""
    from judge.baseten_client import TOTAL_CAP_USD, spent
    unlocked = (not meta_lock.LOCK.exists()) or ("UNLOCKED: META_BASETEN_KEY" in meta_lock.LOCK.read_text(encoding="utf-8"))
    used = spent("product")
    return {"available": unlocked and meta_lock.has_key(("BASETEN_API_KEY", "META_BASETEN_KEY")) and used < SPARK_BUDGET
            and spent() < TOTAL_CAP_USD, "unlocked": unlocked,
            "product_spent_usd": round(used, 4), "product_budget_usd": SPARK_BUDGET, "per_adjudication_usd": 0.067}


def spark13_status() -> dict:
    """Whether the optional Muse Spark 1.3 Contributor adjudicator (Meta Model API) can run: the user's narrow unlock
    and the budget cap; the key never leaves judge/meta_lock.py."""
    from judge.meta_client import spent
    unlocked = meta_lock.LOCK.exists() and meta_lock.DEV_UNLOCK in meta_lock.LOCK.read_text(encoding="utf-8")
    used = spent("product_meta")
    return {"available": unlocked and meta_lock.has_key(("META_MODEL_API_KEY", "META_DEV_KEY")) and used < META_BUDGET
            and spent() < meta_lock.META_DEV_CAP_USD, "unlocked": unlocked,
            "product_spent_usd": round(used, 4), "product_budget_usd": META_BUDGET, "per_adjudication_usd": 0.0041,
            "trains_on_data": True}


def start(case_id: str, contest: Contest, config: dict) -> str:
    """Record the job and run it in its OWN process (python engine.py run <id>): the heavy work (frame decoding, image
    encoding, large requests) never holds the web server's interpreter, so the UI stays responsive."""
    import subprocess
    jid = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    d = JOBS / jid
    (d / "img").mkdir(parents=True, exist_ok=True)
    meta = {"id": jid, "case_id": case_id, "config": config, "created": time.time(), "case": case_json(case_id, contest)}
    if case_id not in library():
        meta["custom"] = {"domain": contest.domain, "question": contest.question, "answer_a": contest.answer_a,
                          "answer_b": contest.answer_b}
    (d / "job.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    with open(d / "worker.log", "a", encoding="utf-8") as log:
        pr = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", jid], cwd=str(ROOT), stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True)
    (d / "pid").write_text(str(pr.pid), encoding="utf-8")
    return jid


def _alive(jid: str) -> bool:
    try:
        os.kill(int((JOBS / jid / "pid").read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def _ended(jid: str) -> bool:
    p = JOBS / jid / "events.jsonl"
    if not p.exists():
        return False
    with open(p, "rb") as f:                          # the end event is the last line
        f.seek(max(0, p.stat().st_size - 300))
        return b'"type": "end"' in f.read()


def is_done(jid: str) -> bool:
    return _ended(jid) or not _alive(jid)


def _started(jid: str) -> bool:
    p = JOBS / jid / "events.jsonl"
    return p.exists() and b'"type": "start"' in p.read_bytes()[:4000]


def _live(jid: str) -> bool:
    return _alive(jid) and not _ended(jid)


def running_jobs() -> int:
    """Jobs whose pipeline has started and not ended (queued workers do not count)."""
    return sum(1 for d in JOBS.glob("*/pid") if _live(d.parent.name) and _started(d.parent.name))


def next_in_line() -> str | None:
    """The oldest queued job (job ids sort by creation time): the queue is first in, first out."""
    waiting = sorted(d.parent.name for d in JOBS.glob("*/pid") if _live(d.parent.name) and not _started(d.parent.name))
    return waiting[0] if waiting else None


VARIANT_PROMPT = """A model answered a question about a video. To test that answer against the footage, write a VARIANT of it
that is identical except for 2 or 3 specific details a viewer could check by looking at the video: a number or count,
a colour, an object, a piece of on-screen text, a position, or who did something. Change each to a plausible but
different value. Copy every other word exactly. Return JSON: {{"variant": "<the full variant answer>", "changes":
[{{"original": "<the words in the answer>", "variant": "<what you changed them to>"}}]}}.

Question: {question}

Answer: {answer}"""
VARIANT_SCHEMA = {"type": "object", "properties": {"variant": {"type": "string"}, "changes": {"type": "array", "items": {
    "type": "object", "properties": {"original": {"type": "string"}, "variant": {"type": "string"}}, "required": ["original", "variant"]}}},
    "required": ["variant", "changes"]}


CITE_RX = re.compile(r"([A-Za-z0-9_-]{11})(?:@|[\s,]+(?:(?:at|around|near|from|between|about|to)\s+){0,2})"
                     r"(\d{1,2}:\d{2}(?::\d{2})?|\d{1,5}(?:\.\d+)?)")
CLIP_FONT = _P["clip_font"]
ADJUDICATED = ("glimmer", "spark", "spark13", "spark13_confirm", "spark13_overturn")


def _secs(s: str) -> float:
    t = 0.0
    for p in s.split(":"):
        t = t * 60 + float(p)
    return t


def cited_moments(jid: str, k: int = 3) -> list:
    """The moments the deciding text cites (the ruling first, then the agents on the winning side), as
    (video, seconds, segment): only videos the agents actually looked at, one per 3-second bucket."""
    evs = [json.loads(l) for l in (JOBS / jid / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    final = next((e for e in reversed(evs) if e.get("type") == "final"), None)
    if not final or not final.get("verdict"):
        return []
    texts = [e.get("rationale") or "" for e in evs if e.get("type") == "adj_done"] if final.get("how") in ADJUDICATED else []
    texts += [e.get("rationale") or "" for e in evs if e.get("type") == "agent_done" and e.get("verdict") == final["verdict"]]
    known = set()
    for e in evs:
        if e.get("type") == "tool":
            a = e.get("args") or {}
            for v in (a.get("video"), str(a.get("handle") or "").split("@")[0]):
                if v:
                    known.add(v)
    out, seen = [], set()
    for text in texts:
        for m in CITE_RX.finditer(text):
            vid, t = m.group(1), _secs(m.group(2))
            if vid not in known or (vid, int(t // 3)) in seen:
                continue
            seg = corpus.segment(f"{vid}@{int(t // 30) * 30}")
            if not seg:
                continue
            seen.add((vid, int(t // 3)))
            out.append((vid, t, seg))
            if len(out) >= k:
                return out
    return out


def evidence_clip(jid: str) -> Path | None:
    """Plan 016: the cited moments as one short clip (about 6 s each, captioned with the time and the video's title),
    cut from the footage with ffmpeg; cached next to the job."""
    import subprocess
    import tempfile
    dst = JOBS / jid / "evidence.mp4"
    if dst.exists():
        return dst
    install_collections()
    moments = cited_moments(jid)
    if not moments:
        return None
    titles = corpus.titles()
    with tempfile.TemporaryDirectory(dir=JOBS / jid) as td:
        parts = []
        for i, (vid, t, seg) in enumerate(moments):
            # the caption font draws Latin script only: drop other scripts (Malayalam titles came out as boxes)
            title = re.sub(r"\s+", " ", re.sub(r"[^\u0020-\u024F\u2010-\u2027]", " ", (titles.get(vid) or ("",))[0] or vid)).strip(" |·-")[:70]
            (Path(td) / f"t{i}.txt").write_text(f"{corpus.mmss(t)}  ·  {title}", encoding="utf-8")
            (Path(td) / f"n{i}.txt").write_text(f"Cited moment {i + 1} of {len(moments)}", encoding="utf-8")
            vf = (f"scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                  f"drawtext=fontfile={CLIP_FONT}:textfile={td}/t{i}.txt:x=24:y=24:fontsize=26:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10,"
                  f"drawtext=fontfile={CLIP_FONT}:textfile={td}/n{i}.txt:x=24:y=h-58:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=8")
            part = Path(td) / f"p{i}.mp4"
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{max(0.0, t - seg['start'] - 2.5):.2f}",
                                "-i", f"{seg['dir']}/{seg['stem']}.mp4", "-t", "6", "-vf", vf, "-an", "-r", "25",
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(part)],
                               capture_output=True, text=True)
            if r.returncode == 0 and part.exists():
                parts.append(part)
        if not parts:
            return None
        (Path(td) / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        tmp = Path(td) / "out.mp4"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(Path(td) / "list.txt"),
                        "-c", "copy", "-movflags", "+faststart", str(tmp)], check=True)
        os.replace(tmp, dst)
    return dst


def make_variant(question: str, answer: str, log=print) -> dict:
    """Check one answer (plan 016): Muse Glimmer writes a copy of the answer with 2-3 checkable details changed; the jury
    then rules between the answer and its variant. Validated: mostly the same words, 1-6 changed places."""
    last = None
    for salt in range(3):
        client = LocalClient(MODEL, SERVERS[0][0], log=log, thinking=True, strength="medium", salt=salt)
        r = client.chat([{"role": "user", "content": VARIANT_PROMPT.format(question=question, answer=answer)}],
                        max_tokens=6144, structured_outputs={"json": VARIANT_SCHEMA})
        text = (r["choices"][0]["message"].get("content") or "").strip()
        try:
            d = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        except (AttributeError, json.JSONDecodeError):
            last = "not JSON"
            continue
        v = str(d.get("variant") or "").strip()
        wa, wv = answer.split(), v.split()
        ratio = difflib.SequenceMatcher(None, wa, wv, autojunk=False).ratio() if wv else 0.0
        changed = [p for p in disputed(answer, v, n=6)] if v else []
        if v and v != answer and ratio >= 0.75 and 1 <= len(changed) <= 6:
            return {"variant": v, "changes": changed, "ratio": round(ratio, 3)}
        last = f"overlap {ratio:.2f}, {len(changed)} changes"
    raise RuntimeError(f"could not write a usable variant of the answer ({last})")


def worker(jid: str):
    """The job's own process: rebuild the case, wait for a free slot, run the pipeline, write events to disk."""
    meta = json.loads((JOBS / jid / "job.json").read_text(encoding="utf-8"))
    install_collections()                             # a custom case may search an ingested video
    cu = meta.get("custom")
    single = None
    job = Job(jid, meta["case_id"], custom_case(**cu) if cu else library()[meta["case_id"]], meta["config"])
    if (meta.get("config") or {}).get("single") and cu:
        single = meta.get("single")
        if not single:                                    # check one answer: write the variant, place the answer at random
            job.emit({"type": "status", "message": "Muse Glimmer is writing a variant of the submitted answer to test it against"})
            try:
                var = make_variant(cu["question"], cu["answer_a"], log=lambda *m: None)
            except Exception as ex:
                job.emit({"type": "error", "message": f"{ex}"})
                job.emit({"type": "end"})
                return
            side = "A" if int(hashlib.sha1(jid.encode()).hexdigest(), 16) % 2 == 0 else "B"
            orig = cu["answer_a"]
            cu = {**cu, "answer_a": orig if side == "A" else var["variant"], "answer_b": var["variant"] if side == "A" else orig}
            single = {"original_side": side, "changes": var["changes"] if side == "A" else [[b, a] for a, b in var["changes"]]}
            meta.update({"custom": cu, "single": single, "case": case_json(meta["case_id"], custom_case(**cu))})
            (JOBS / jid / "job.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            job.emit({"type": "variant", **single, "case": meta["case"]})
            job.contest = custom_case(**cu)                # the investigators get the answer and its variant
    job.single = single
    queued = False
    while running_jobs() >= MAX_JOBS or next_in_line() != jid:
        if not queued:
            job.emit({"type": "queued"})
            queued = True
        time.sleep(1.5)
    _run(job)


def _run(job: Job):
    try:
        _pipeline(job)
    except Exception as e:
        job.emit({"type": "error", "message": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})
    finally:
        job.done = True
        job.emit({"type": "end"})


def _pipeline(job: Job):
    c, cfg = job.contest, job.config
    n = 1 if cfg.get("agents") == 1 else 3
    turns = QUICK["max_steps"] if cfg.get("quick") else AGENT_KW["max_steps"]
    strength = QUICK["strength"] if cfg.get("quick") else "high"
    T = TRACK_QUICK if cfg.get("quick") else TRACK
    roles = [f"inv{i}" for i in range(n)]
    plan = [{"role": r, "seed": i, "gpu": SERVERS[i % len(SERVERS)][1], "model": "Muse Glimmer 30B", "turns": turns} for i, r in enumerate(roles)]
    job.emit({"type": "start", "config": cfg, "plan": plan, "case": case_json(job.case_id, c)})
    t0 = time.time()
    enc = encoder()
    results: list = [None] * n

    def investigate(i: int):
        role = roles[i]
        _CTX.set((job, role))
        url = SERVERS[i % len(SERVERS)][0]
        client = LocalClient(MODEL, url, log=job.log, thinking=True, strength=strength, salt=i)
        job.emit({"type": "agent_start", "role": role})
        try:
            r = AG.judge(c, TracedClient(client, job, role), enc, log=job.log, **{**AGENT_KW, "max_steps": turns})
        except Exception as e:
            job.emit({"type": "agent_done", "role": role, "verdict": None, "how": "error",
                      "rationale": f"{type(e).__name__}: {e}", "steps": 0, "wall": 0})
            return
        results[i] = r
        job.emit({"type": "agent_done", "role": role, "verdict": r["verdict"], "how": r["how"],
                  "rationale": r["rationale"], "steps": r["steps"], "images": r["images_viewed"], "wall": r["wall_s"],
                  "errors": r["errors"][:2]})

    threads = [threading.Thread(target=investigate, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    verdicts = [(r or {}).get("verdict") for r in results]
    vote = ADJ.majority(verdicts)
    decided = [v for v in verdicts if v in ("A", "B")]
    contested = n > 1 and (len(set(decided)) != 1 or len(decided) < 2)
    job.emit({"type": "vote", "verdicts": verdicts, "vote": vote, "contested": contested})
    resolve = cfg.get("resolve", "glimmer")
    adj = None
    check_all = resolve == "spark13all" and n > 1
    if check_all and not spark13_status()["available"]:
        job.emit({"type": "notice", "message": "Muse Spark 1.3 is not available; the Muse Glimmer adjudicator decides splits."})
        check_all, resolve = False, "glimmer"
    if n == 1:
        final, how, track = verdicts[0], "single", T["single"]
    elif check_all and not contested:                  # plan 014: Spark 1.3 re-checks an agreed verdict on the evidence
        adj = _adjudicate(job, c, [r for r in results if r], "spark13")
        final = adj.get("verdict") or vote
        how = "spark13_confirm" if final == vote else "spark13_overturn"
        track = T["s13_confirm"] if final == vote else T["s13_overturn"]
    elif not contested:
        final, how, track = vote, "unanimous", T["unanimous"]
    elif resolve == "vote" and vote:
        final, how, track = vote, "vote", T["vote"]
    else:
        ok = {"spark": lambda: spark_status()["available"], "spark13": lambda: spark13_status()["available"]}
        resolve = "spark13" if resolve == "spark13all" else resolve
        model = resolve if resolve in ok and ok[resolve]() else "glimmer"
        if resolve in ok and model != resolve:
            name = "Muse Spark Open" if resolve == "spark" else "Muse Spark 1.3"
            job.emit({"type": "notice", "message": f"{name} is not available; the Muse Glimmer adjudicator decides."})
        adj = _adjudicate(job, c, [r for r in results if r], model)
        final = adj.get("verdict") or vote
        how, track = model, T[model]
    wall = round(time.time() - t0, 1)
    forced = sum(1 for r in results if r and r.get("how") == "forced")
    single = getattr(job, "single", None)
    summary = {"type": "final", "verdict": final, "how": how, "track": {"pct": track[0], "basis": track[1]}, "forced": forced,
               "verdicts": verdicts, "vote": vote, "contested": contested, "wall": wall, "usage": job.usage,
               "adjudicator": (adj or {}).get("model"),
               **({"single": {**single, "supported": final == single["original_side"]}} if single and final else {})}
    job.emit(summary)
    meta = json.loads((job.dir / "job.json").read_text(encoding="utf-8"))
    meta["final"] = {k: v for k, v in summary.items() if k != "type"}
    (job.dir / "job.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _adjudicate(job: Job, c: Contest, results: list, model: str) -> dict:
    """Plan 004's evidence-only adjudicator over the investigators' own looks (their verdicts are not shown)."""
    views = 2 if model == "spark" else 3            # Baseten takes at most 8 images per request (plan 006)
    order = ADJ.report_order(c.key, len(results), 0)
    job.emit({"type": "adj_start", "model": model, "order": order})
    _CTX.set((job, "evidence"))
    reports = []
    for j, i in enumerate(order):
        ir = results[i]
        calls = ADJ.pick_views(ir.get("tool_calls"), ir.get("rationale") or "", k=views)
        job.emit({"type": "evidence", "report": j, "from": f"inv{i}", "looks": calls})
        reports.append({"verdict": ir.get("verdict") or "?", "rationale": (ir.get("rationale") or "").strip(),
                        "views": ADJ.render_views(c, calls, log=job.log), "picked": calls})
    _CTX.set((job, "adj"))
    if model == "spark":
        from judge.baseten_client import BasetenClient
        client, max_req = BasetenClient(log=job.log, strength="high", salt=0, budget_usd=SPARK_BUDGET, tag="product",
                                        run=f"product_{job.id}"), 8
    elif model == "spark13":                         # the Meta Model API: no image cap, the plan-013 settings
        from judge.meta_client import MetaClient
        client, max_req = MetaClient(log=job.log, strength="high", salt=0, budget_usd=META_BUDGET, tag="product_meta",
                                     run=f"product_{job.id}"), None
    else:
        client, max_req = LocalClient(MODEL, SERVERS[0][0], log=job.log, thinking=True, strength="high", salt=0), None
    s = ADJ.adjudicate(c, reports, TracedClient(client, job, "adj", first_look=False), variant="evidence", max_steps=4,
                       max_tokens=16384, max_per_request=max_req, log=job.log)
    job.emit({"type": "adj_done", "model": model, "verdict": s.get("verdict"), "how": s.get("how"),
              "rationale": s.get("rationale"), "steps": s.get("steps"), "wall": s.get("wall_s")})
    return {"verdict": s.get("verdict"), "model": model}


# ------------------------------------------------------------------ proof: the track record on the library
PROOF_TRIPLES = {k: (list(v[0]), list(v[1])) for k, v in config("proof")["proof_triples"].items()}   # configs/proof.yaml


def _rows(name: str) -> dict:
    p = ROOT / "runs" / name / "results.jsonl"
    return {json.loads(l)["key"]: json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()} if p.exists() else {}


@lru_cache(maxsize=1)
def proof() -> dict:
    """Portia's development track record, pooled over the 5 investigator triples of plans 005-006 (220 library contests x
    5 = 1,100 contest-triples): one agent, the vote, Portia's default (Glimmer adjudicator on splits; mean over its
    samples) and Portia + Spark Open (one sample per triple). By domain and by how the verdict was reached."""
    shards = {"s3": "shard3_15pct", "s4": "shard4_20pct"}
    shipped = ROOT / "product" / "site" / "data" / "proof.json"     # a checkout without the development runs (97 MB,
    if shipped.exists() and not any((ROOT / "runs" / f"{r}_{s}" / "results.jsonl").exists()      # not redistributed)
                                    for inv, _ in PROOF_TRIPLES.values() for r in inv for s in shards):
        return json.loads(shipped.read_text(encoding="utf-8"))      # the gallery's copy of these numbers
    dom = {c.key: c.domain for c in library().values()}
    agents = {s: [_rows(f"mg_v4t_{s}")] + [_rows(f"mg_v4t_r{i}_{s}") for i in range(1, 11)] for s in shards}
    acc = {}                                         # (bucket, system) -> [sum of right, n]

    def add(bucket, system, right):
        a = acc.setdefault((bucket, system), [0.0, 0])
        a[0] += right
        a[1] += 1
    for tag, (inv, ev) in PROOF_TRIPLES.items():
        for s in shards:
            SP = _rows(f"mg_adjsp_{tag}_{s}")
            S13 = _rows(f"mg_adjs13_{tag}_{s}")
            G = [x for x in (_rows(f"{r}_{s}") for r in ev) if len(x) >= 90]
            for k, r in SP.items():
                good, d = r["good_side"], dom.get(k, "?")
                single = sum(a[k].get("verdict") == good for a in agents[s] if k in a) / max(1, sum(k in a for a in agents[s]))
                glim = (sum(g[k].get("verdict") == good for g in G if k in g) / max(1, sum(k in g for g in G))) if r.get("contested") \
                    else float(r.get("vote") == good)
                kind = "split" if r.get("contested") else "agree"
                for bucket in ("all", d, kind):
                    add(bucket, "single", single)
                    add(bucket, "vote", float(bool(r.get("vote_correct"))))
                    add(bucket, "jury", glim)
                    add(bucket, "spark", float(r.get("verdict") == good))
                    if k in S13:
                        add(bucket, "spark13", float(S13[k].get("verdict") == good))
    pct = lambda b, s: round(100 * acc[(b, s)][0] / acc[(b, s)][1], 1) if (b, s) in acc else None
    domains = sorted({d for (b, _) in acc for d in [b] if b not in ("all", "split", "agree")})
    systems = ["single", "vote", "jury", "spark13", "spark"]
    return {"n": acc[("all", "single")][1], "overall": {s: pct("all", s) for s in systems}, "check_all": check_all_stats(),
            "trust": trust_table(),
            # plan 019: accuracy by what the answers disagree about (analysis/dispute_kinds.py)
            "kinds": (json.loads((ROOT / "runs" / "dispute_kinds.json").read_text(encoding="utf-8"))
                      if (ROOT / "runs" / "dispute_kinds.json").exists() else None),
            # audit 021: the pre-registered held-out check (analysis/heldout_021.py)
            "heldout": (json.loads((ROOT / "runs" / "heldout_021.json").read_text(encoding="utf-8"))
                        if (ROOT / "runs" / "heldout_021.json").exists() else None),
            # audit 022: the Muse Spark 1.3 modes on the same held-out contests (analysis/heldout_022.py)
            "heldout_spark": (json.loads((ROOT / "runs" / "heldout_022.json").read_text(encoding="utf-8"))
                              if (ROOT / "runs" / "heldout_022.json").exists() else None),
            "by_domain": [{"domain": d, "n": acc[(d, "single")][1] // 5, **{s: pct(d, s) for s in systems}} for d in domains],
            "by_kind": {k: {"n": acc[(k, "single")][1], **{s: pct(k, s) for s in systems}} for k in ("agree", "split")},
            "cost": {"spark_usd_per_case": round(18.80 / 1100, 4), "spark_usd_per_split": 0.067, "spark_agent_usd_per_case": 0.185,
                     "spark13_usd_per_case": round(1.166 / 1100, 5), "spark13_usd_per_split": 0.0041,
                     "spark13_check_usd_per_case": 0.0038,
                     "glimmer_tokens_per_agent": 289000, "live_minutes_three_agents": 5.1},
            "labels": {"single": "One Muse Glimmer agent", "vote": "Three agents, majority vote",
                       "jury": "Portia (default): + Muse Glimmer adjudicator", "spark13": "Portia + Muse Spark 1.3 adjudicator (Meta API)",
                       "spark": "Portia + Muse Spark Open adjudicator"}}


CHECK_TRIPLES = {k: list(v) for k, v in config("proof")["check_triples"].items()}   # configs/proof.yaml


@lru_cache(maxsize=1)
def check_all_stats() -> dict:
    """Plan 014: Muse Spark 1.3 adjudicates every contest, agreed ones included (mg_adjs13all_*), against the vote and
    Spark 1.3 on splits only, on the same contest-triples."""
    n = right = vote = splits = fixed = broken = un = 0
    for tag in CHECK_TRIPLES:
        S = {**_rows(f"mg_adjs13all_{tag}_s3"), **_rows(f"mg_adjs13all_{tag}_s4")}
        for k, s in S.items():
            good = s["good_side"]
            n += 1
            right += s["verdict"] == good
            vote += s["vote"] == good
            splits += (s["verdict"] if s["contested"] else s["vote"]) == good
            if not s["contested"]:
                un += 1
                fixed += s["vote"] != good and s["verdict"] == good
                broken += s["vote"] == good and s["verdict"] != good
    pct = lambda x: round(100 * x / n, 1) if n else None                                            # noqa: E731
    return {"n": n, "triples": len(CHECK_TRIPLES), "pct": pct(right), "vote": pct(vote), "splits_only": pct(splits),
            "unanimous": un, "fixed": fixed, "broken": broken, "usd_per_case": 0.0038}


# ------------------------------------------------------------------ history (jobs survive restarts on disk)
def history(limit: int = 60) -> list:
    out = []
    for d in sorted(JOBS.glob("*/job.json"), reverse=True)[:limit]:
        if (d.parent / "archived").exists():             # test runs, hidden from History and the gallery (kept on disk)
            continue
        try:
            m = json.loads(d.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        case = m.get("case") or {}
        final = m.get("final")
        if final and "forced" not in final:
            final = {**final, "forced": _forced_from_events(m["id"])}
        out.append({"id": m["id"], "case_id": m.get("case_id"), "created": m.get("created"), "config": m.get("config"),
                    "domain": case.get("domain"), "question": (case.get("question") or "")[:200],
                    "kind": case.get("kind") or (dispute_kind(case["answer_a"], case["answer_b"])
                                                 if case.get("answer_a") and case.get("answer_b") else None),
                    "final": final, "running": not is_done(m["id"])})
    return out


def _forced_from_events(jid: str) -> int:
    p = JOBS / jid / "events.jsonl"
    n = 0
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if '"agent_done"' in line and '"forced"' in line:
                try:
                    e = json.loads(line)
                    n += e.get("type") == "agent_done" and e.get("how") == "forced"
                except json.JSONDecodeError:
                    pass
    return n


TRUST_PATH = {"unanimous": ("agreed_settled", "agreed_turnlimit"), "spark13_confirm": ("s13_confirm_settled", "s13_confirm_turnlimit"),
              "glimmer": "split_glimmer", "spark": "split_spark", "spark13": "split_spark13", "vote": "split_vote",
              "spark13_overturn": "s13_overturn", "single": "single"}


def trust_for(final: dict | None, quick: bool = False, kind: str | None = None) -> dict | None:
    """The trust tier of a verdict (the same rule as the UI's trustFor): the measured accuracy of its path, never
    "accept" when the answers dispute on-screen text or positions (plan 019: the jury's weakest kinds)."""
    if not final or not final.get("verdict"):
        return None
    T = trust_table()
    path = TRUST_PATH.get(final.get("how"))
    if isinstance(path, tuple):
        path = path[0] if (final.get("forced") is not None and final["forced"] <= 1) else path[1]
    p = T["paths"].get(path)
    pct = (final.get("track") or {}).get("pct") if (quick or not p) else p["pct"]
    if pct is None:
        return None
    L = T["levels"]
    level = "accept" if pct >= L["accept"] else "spot" if pct >= L["spot"] else "review"
    capped = kind in ("text", "position") and level == "accept"
    return {"level": "spot" if capped else level, "pct": pct, "path": path, **({"capped": kind} if capped else {})}


def start_batch(name: str, items: list, config: dict) -> str:
    """A batch audit: one Portia job per item (a library case id, or a collection + question + two answers); the jobs
    queue first come, first served with every other job."""
    bid = "b" + time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    jobs = []
    for it in items:
        if it.get("case_id"):
            jobs.append(start(it["case_id"], library()[it["case_id"]], config))
        else:
            c = custom_case(it["domain"], it["question"], it["answer_a"], it["answer_b"])
            jobs.append(start(c.qid, c, config))
    BATCHES.mkdir(exist_ok=True)
    meta = {"id": bid, "name": name or f"Batch of {len(items)}", "created": time.time(), "config": config, "jobs": jobs, "items": items}
    (BATCHES / f"{bid}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return bid


def batch_status(bid: str) -> dict | None:
    p = BATCHES / f"{bid}.json"
    if not p.exists():
        return None
    meta = json.loads(p.read_text(encoding="utf-8"))
    quick = bool((meta.get("config") or {}).get("quick"))
    rows = []
    for jid in meta["jobs"]:
        try:
            m = json.loads((JOBS / jid / "job.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rows.append({"job": jid, "status": "missing"})
            continue
        f = m.get("final")
        if f and "forced" not in f:
            f = {**f, "forced": _forced_from_events(jid)}
        case = m.get("case") or {}
        rows.append({"job": jid, "case_id": m.get("case_id"), "domain": case.get("domain"), "question": case.get("question"),
                     "answer_a": case.get("answer_a"), "answer_b": case.get("answer_b"),
                     "status": "done" if f else ("running" if _started(jid) and not is_done(jid) else ("failed" if is_done(jid) else "queued")),
                     "final": f, "trust": trust_for(f, quick, dispute_kind(case["answer_a"], case["answer_b"])
                                                    if case.get("answer_a") and case.get("answer_b") else None)})
    return {**{k: v for k, v in meta.items() if k != "items"}, "rows": rows}


def batches() -> list:
    out = []
    for p in sorted(BATCHES.glob("*.json"), reverse=True)[:30] if BATCHES.exists() else []:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"id": m["id"], "name": m.get("name"), "created": m.get("created"), "n": len(m.get("jobs", [])),
                    "done": sum((JOBS / j / "job.json").exists() and "final" in json.loads((JOBS / j / "job.json").read_text(encoding="utf-8"))
                                for j in m.get("jobs", []))})
    return out


def trust_table() -> dict:
    """Plan 016: each verdict path's measured development accuracy and share (analysis/trust_tiers.py ->
    runs/trust_tiers.json), for the trust tier shown with every verdict and the Proof page's coverage view."""
    p = ROOT / "runs" / "trust_tiers.json"
    shipped = ROOT / "product" / "site" / "data" / "proof.json"
    if not p.exists() and shipped.exists():                           # a checkout without the runs: the gallery's copy
        return json.loads(shipped.read_text(encoding="utf-8")).get("trust", {})
    T = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    paths = {}
    for mode in ("glimmer", "spark", "spark13", "spark13all"):              # 5-triple numbers first where both exist
        for x in T.get(mode, {}).get("paths", []):
            paths.setdefault(x["path"], {**x, "mode": mode})
    paths["split_vote"] = {"path": "split_vote", "label": "split, decided by the majority", "pct": TRACK["vote"][0], "n": 282}
    paths["single"] = {"path": "single", "label": "one investigator alone", "pct": TRACK["single"][0], "n": 1100}
    return {"paths": paths, "modes": T, "levels": {"accept": 85.0, "spot": 75.0}}


def events(jid: str, start: int = 0) -> tuple[list, bool]:
    """Events from `start` on (read from the job's log on disk; its worker process writes it), and whether it ended.
    A worker that died without an end event counts as ended."""
    done = is_done(jid)
    p = JOBS / jid / "events.jsonl"
    if not p.exists():
        return [], done
    lines = p.read_text(encoding="utf-8").splitlines()
    evs = []
    for l in lines[start:]:
        try:
            evs.append(json.loads(l))
        except json.JSONDecodeError:                  # a line the worker is still writing
            break
    return evs, done and start + len(evs) >= len(lines)


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "run":
    worker(sys.argv[2])
