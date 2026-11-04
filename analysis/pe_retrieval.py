#!/usr/bin/env python3
"""portia/analysis/pe_retrieval.py: plan 015: Meta's Perception Encoder (PE-Core) as Portia's retriever, against the
Qwen3-VL-Embedding-8B index, on development shards 3-4 (offline; no agent runs).

    retriever env:  python analysis/pe_retrieval.py prep          # eval set, candidate subset, Qwen baseline ranks
    retriever env:  python analysis/pe_retrieval.py rewrite       # Muse Glimmer writes short scene queries (local GPUs)
    .venv-pe:       python analysis/pe_retrieval.py index         # PE-Core frame vectors for every candidate (GPU)
    .venv-pe:       python analysis/pe_retrieval.py drama         # Meta's DRAMA-1B text retriever on transcripts (GPU)
    .venv-pe:       python analysis/pe_retrieval.py score         # metrics for every retriever variant

The task is the agents' overview search: rank the segments of a contest's whole domain by the v4 retrieval query
(question + the answers' shared text), and score against the dataset's ground-truth evidence clips:
  hit@8          an evidence segment in the top 8
  any@64         an evidence segment in the top 64
  clip_rec@64    share of the evidence clips with a segment in the top 64 (the overview pack)
  mrr            mean reciprocal rank of the first evidence segment
Candidates: every evidence segment of the dev contests plus a random 25% of each domain's other segments (seed 0), so
the first index reads ~130 GB instead of the corpus's 525 GB. Every retriever ranks the SAME candidates; numbers are
higher than on the full domain, and only the comparison counts.
Variants (score):
  qwen            the current index (16 frames + transcript per segment) and its query vectors
  pe:frames       PE-Core text tower on the query (first 32 tokens) vs mean of 8 keyframe vectors
  pe:frames-max   ... vs the best of the 8 keyframes
  pe:frames-win   query cut into 20-word windows; a segment keeps its best window score (no truncation)
  pe:text         PE-Core text tower on transcripts (20-word windows, best window) vs query windows (user's idea)
  bm25            BM25 on transcripts (no model)
  pe:glimmer      Muse Glimmer rewrites the question into 4 short scene descriptions; best description per segment
  drama           Meta's DRAMA-1B dense text retriever (CC-BY-NC-4.0: evaluation only) on transcripts vs the query
  rrf(...)        reciprocal-rank fusion of a visual and a transcript ranking
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "pe_retrieval"
SHARDS = ["shard3_15pct", "shard4_20pct"]
MODEL = "hf-hub:timm/PE-Core-L-14-336"
NFRAMES = 8


# ------------------------------------------------------------------ prep (retriever env: corpus + Qwen query cache)
def prep():
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "analysis"))
    from judge import corpus
    from judge.answer_diff import retrieval_text
    from judge.contests import DATASET, load_contests
    from judge.embed_client import QueryEncoder
    from retrieval_queries import clips

    recs = {json.loads(l)["id"]: json.loads(l) for l in open(DATASET, encoding="utf-8")}
    contests = load_contests(SHARDS)
    doms = sorted({c.domain for c in contests})
    corpus.register(sorted({p for d in doms for p in corpus.domain_playlists(d)}))
    evset, positives = [], set()
    for c in contests:
        cl = clips(recs[c.qid])
        if cl:
            evset.append({"key": c.key, "domain": c.domain, "query": retrieval_text(c.question, c.answer_a, c.answer_b),
                          "question": c.question, "clips": [sorted(h) for h in cl]})
            positives |= set().union(*cl)
    rng = random.Random(0)
    cands, segpath, qwen_emb = {}, {}, {}
    for d in doms:
        segs = [s for pl in corpus.domain_playlists(d) for s in corpus.index(pl)["segs"]]
        E = np.concatenate([corpus.index(pl)["emb"] for pl in corpus.domain_playlists(d)])
        keep = [i for i, s in enumerate(segs) if s["handle"] in positives or rng.random() < 0.25]
        cands[d] = [segs[i]["handle"] for i in keep]
        qwen_emb[d] = E[keep] / (np.linalg.norm(E[keep], axis=1, keepdims=True) + 1e-12)
        for i in keep:
            segpath[segs[i]["handle"]] = [segs[i]["dir"], segs[i]["stem"]]
    enc = QueryEncoder(log=lambda *m: None)
    qv = enc.encode([e["query"] for e in evset])
    for e, v in zip(evset, qv):
        H, E = cands[e["domain"]], qwen_emb[e["domain"]]
        order = np.argsort(-(E @ (v / (np.linalg.norm(v) + 1e-12))))
        e["qwen_rank"] = [H[i] for i in order[:400]]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eval.json").write_text(json.dumps({"contests": evset, "candidates": cands, "segpath": segpath}), encoding="utf-8")
    n = sum(len(v) for v in cands.values())
    print(f"[prep] {len(evset)} dev contests with evidence clips; {n} candidate segments "
          f"({len(positives)} evidence segments); {OUT / 'eval.json'}")


# ------------------------------------------------------------------ rewrite (retriever env: the local Glimmer servers)
REWRITE = """You will search a large video library with an image search that reads only about 20 words per query.
Below is a two-hop question about the videos and the text that two candidate answers share.
Write 4 short visual descriptions, at most 15 words each, of the scenes they describe: what the camera shows
(people, objects, actions, setting, on-screen text). One per line, no numbering, nothing else.

Question: {question}

Shared answer text: {shared}"""


def rewrite():
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0, str(ROOT))
    from judge.local_client import LocalClient
    ev = json.loads((OUT / "eval.json").read_text(encoding="utf-8"))
    urls = ["http://127.0.0.1:18660/v1", "http://127.0.0.1:18661/v1"]

    def one(i_e):
        i, e = i_e
        shared = e["query"][len(e["question"]):].strip()
        c = LocalClient("mg30", urls[i % 2], log=lambda *m: None, thinking=True, strength="high")
        r = c.chat([{"role": "user", "content": REWRITE.format(question=e["question"], shared=shared)}],
                   max_tokens=2048, reasoning={"effort": "low"})
        text = (r["choices"][0]["message"].get("content") or "").strip()
        lines = [re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s+", "", l).strip() for l in text.splitlines()]
        return e["key"], [l for l in lines if len(l.split()) >= 3][:4]

    with ThreadPoolExecutor(8) as pool:
        out = dict(pool.map(one, enumerate(ev["contests"])))
    (OUT / "rewrites.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[rewrite] {sum(bool(v) for v in out.values())}/{len(out)} contests got scene queries; e.g. {next(iter(out.values()))}")


# ------------------------------------------------------------------ index (.venv-pe, GPU)
def _keyframes(args):
    """Up to n keyframes of a clip, resized to 336x336 like PE-Core's own preprocessing (bilinear, no crop)."""
    path, n = args
    import av
    from PIL import Image
    try:
        with av.open(path) as c:
            s = c.streams.video[0]
            s.codec_context.skip_frame = "NONKEY"
            fr = [f.to_image() for f in c.decode(s)]
    except Exception:
        return np.zeros((0, 336, 336, 3), dtype=np.uint8)
    if len(fr) > n:
        fr = [fr[int((k + 0.5) / n * len(fr))] for k in range(n)]
    if not fr:
        return np.zeros((0, 336, 336, 3), dtype=np.uint8)
    return np.stack([np.asarray(im.convert("RGB").resize((336, 336), Image.BILINEAR)) for im in fr])


def index():
    import multiprocessing as mp
    ev = json.loads((OUT / "eval.json").read_text(encoding="utf-8"))
    handles = sorted(ev["segpath"])
    dst, part = OUT / "pe_l14_frames.npy", OUT / "pe_l14_partial.npz"
    if dst.exists():
        print(f"[index] {dst} exists; move it away to rebuild")
        return
    jobs = [(f"{ev['segpath'][h][0]}/{ev['segpath'][h][1]}.mp4", NFRAMES) for h in handles]
    # decoders first, as fresh processes: forking after CUDA is initialised killed every worker
    pool = mp.get_context("spawn").Pool(16)
    import torch
    import open_clip
    # it shares a GPU with a vLLM server: a hard cap keeps its own allocations out of vLLM's way
    torch.cuda.set_per_process_memory_fraction(3.5e9 / torch.cuda.get_device_properties(0).total_memory)
    model, _, _ = open_clip.create_model_and_transforms(MODEL)
    model = model.eval().half().cuda()
    V = np.zeros((len(handles), NFRAMES, 1024), dtype=np.float16)
    nf = np.zeros(len(handles), dtype=np.int8)
    done = 0
    if part.exists():
        z = np.load(part)
        V, nf, done = z["V"], z["nf"], int(z["done"])
        print(f"[index] resuming at {done}/{len(handles)}")
    t0 = time.time()

    def flush(batch, idx):
        x = torch.from_numpy(np.concatenate(batch)).cuda().permute(0, 3, 1, 2).half().div(255).sub(0.5).div(0.5)
        with torch.no_grad():
            f = torch.nn.functional.normalize(model.encode_image(x).float(), dim=-1).cpu().numpy().astype(np.float16)
        for (a, b), v in zip(idx, f):
            V[a, b] = v

    batch, idx, nb = [], [], 0
    for i, frames in enumerate(pool.imap(_keyframes, jobs[done:], chunksize=4), done):
        nf[i] = len(frames)
        if len(frames):
            batch.append(frames)
            idx += [(i, k) for k in range(len(frames))]
            nb += len(frames)
        if nb >= 32 or i == len(jobs) - 1:
            if batch:
                flush(batch, idx)
            batch, idx, nb = [], [], 0
        if (i + 1) % 1000 == 0:
            rate = (i + 1 - done) / (time.time() - t0)
            print(f"[index] {i + 1}/{len(handles)} segments, {rate:.1f}/s, about {(len(handles) - i - 1) / max(rate, 1e-9) / 60:.0f} min left", flush=True)
        if (i + 1) % 4000 == 0:
            np.savez(part, V=V, nf=nf, done=i + 1)
    pool.close()
    np.save(dst, V)
    np.save(OUT / "pe_l14_nframes.npy", nf)
    (OUT / "pe_l14_handles.json").write_text(json.dumps(handles), encoding="utf-8")
    print(f"[index] {len(handles)} segments in {(time.time() - t0) / 60:.1f} min; {int((nf == 0).sum())} without frames; {dst}")


# ------------------------------------------------------------------ drama (.venv-pe, GPU)
def drama():
    import torch
    from transformers import AutoModel, AutoTokenizer
    ev = json.loads((OUT / "eval.json").read_text(encoding="utf-8"))
    handles = json.loads((OUT / "pe_l14_handles.json").read_text(encoding="utf-8"))
    torch.cuda.set_per_process_memory_fraction(3.5e9 / torch.cuda.get_device_properties(0).total_memory)
    tok = AutoTokenizer.from_pretrained("facebook/drama-1b")
    model = AutoModel.from_pretrained("facebook/drama-1b", trust_remote_code=True, torch_dtype=torch.bfloat16).cuda().eval()
    docs = []
    for h in handles:
        d, s = ev["segpath"][h]
        try:
            docs.append(Path(f"{d}/{s}.txt").read_text(encoding="utf-8", errors="ignore").strip() or "(no speech)")
        except OSError:
            docs.append("(no speech)")
    t0, D = time.time(), []
    with torch.no_grad():
        for i in range(0, len(docs), 32):
            D.append(model.encode_documents(tok, docs[i:i + 32]).float().cpu().numpy())
        Q = model.encode_queries(tok, [e["query"] for e in ev["contests"]]).float().cpu().numpy()
    D = np.concatenate(D)
    D /= np.linalg.norm(D, axis=1, keepdims=True) + 1e-12
    Q /= np.linalg.norm(Q, axis=1, keepdims=True) + 1e-12
    np.save(OUT / "drama_docs.npy", D.astype(np.float16))
    np.save(OUT / "drama_queries.npy", Q.astype(np.float16))
    print(f"[drama] {len(docs)} transcripts and {len(Q)} queries in {(time.time() - t0) / 60:.1f} min")


# ------------------------------------------------------------------ score (.venv-pe)
def _windows(text: str, w: int = 20) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + w]) for i in range(0, max(len(words), 1), w)] or [""]


def score():
    import torch
    import open_clip
    import bm25s
    ev = json.loads((OUT / "eval.json").read_text(encoding="utf-8"))
    handles = json.loads((OUT / "pe_l14_handles.json").read_text(encoding="utf-8"))
    row = {h: i for i, h in enumerate(handles)}
    V = np.load(OUT / "pe_l14_frames.npy").astype(np.float32)
    nf = np.load(OUT / "pe_l14_nframes.npy")
    mask = (np.arange(NFRAMES)[None, :] < nf[:, None])
    Vmean = (V * mask[..., None]).sum(1) / np.maximum(nf[:, None], 1)
    Vmean /= np.linalg.norm(Vmean, axis=1, keepdims=True) + 1e-12
    model, _, _ = open_clip.create_model_and_transforms(MODEL)
    tok = open_clip.get_tokenizer(MODEL)
    model = model.eval().half().cuda()

    def etext(texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 512):
            with torch.no_grad():
                f = model.encode_text(tok(texts[i:i + 512]).cuda())
            out.append(torch.nn.functional.normalize(f.float(), dim=-1).cpu().numpy())
        return np.concatenate(out)

    # transcripts: 20-word windows through the PE text tower, and BM25 per domain
    trans = {}
    for h in handles:
        d, s = ev["segpath"][h]
        try:
            trans[h] = Path(f"{d}/{s}.txt").read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            trans[h] = ""
    win_h, win_t = [], []
    for h in handles:
        for w in _windows(trans[h]):
            win_h.append(row[h])
            win_t.append(w)
    print(f"[score] encoding {len(win_t)} transcript windows with the PE text tower", flush=True)
    W = etext(win_t)
    win_h = np.array(win_h)
    bm = {}
    for d, H in ev["candidates"].items():
        r = bm25s.BM25()
        r.index(bm25s.tokenize([trans[h] for h in H], stopwords="en", show_progress=False), show_progress=False)
        bm[d] = r

    def rank(scores: np.ndarray, H: list[str]) -> list[str]:
        return [H[i] for i in np.argsort(-scores)]

    def rrf(*ranks: list[str], k: int = 60) -> list[str]:
        s = {}
        for r in ranks:
            for i, h in enumerate(r[:400]):
                s[h] = s.get(h, 0.0) + 1.0 / (k + i)
        return sorted(s, key=lambda h: -s[h])

    rw = json.loads((OUT / "rewrites.json").read_text(encoding="utf-8")) if (OUT / "rewrites.json").exists() else {}
    dr = None
    if (OUT / "drama_docs.npy").exists():
        dr = (np.load(OUT / "drama_docs.npy").astype(np.float32), np.load(OUT / "drama_queries.npy").astype(np.float32))
    agg = {}
    for qi, e in enumerate(ev["contests"]):
        H = ev["candidates"][e["domain"]]
        rows = np.array([row[h] for h in H])
        qw = _windows(e["query"])
        Q = etext([e["query"]] + qw)
        q1, Qw = Q[0], Q[1:]
        frames = V[rows]
        m = mask[rows]
        r = {"qwen": e["qwen_rank"]}
        r["pe:frames"] = rank(Vmean[rows] @ q1, H)
        fm = np.where(m, frames @ q1, -9).max(1)
        r["pe:frames-max"] = rank(fm, H)
        r["pe:frames-win"] = rank((Vmean[rows] @ Qw.T).max(1), H)
        # transcript windows: best window of the segment against the best query window
        sel = np.isin(win_h, rows)
        ws = (W[sel] @ Qw.T).max(1)
        best = np.full(len(handles), -9.0)
        np.maximum.at(best, win_h[sel], ws)
        r["pe:text"] = rank(best[rows], H)
        res, sc = bm[e["domain"]].retrieve(bm25s.tokenize([e["query"]], stopwords="en", show_progress=False),
                                           k=min(400, len(H)), show_progress=False)
        r["bm25"] = [H[i] for i in res[0]]
        if e["key"] in rw and rw[e["key"]]:
            G = etext(rw[e["key"]])
            r["pe:glimmer"] = rank((Vmean[rows] @ G.T).max(1), H)
            r["pe:glimmer+win"] = rank((Vmean[rows] @ np.concatenate([G, Qw]).T).max(1), H)
            r["rrf(pe:glimmer, bm25)"] = rrf(r["pe:glimmer"], r["bm25"])
        if dr is not None:
            r["drama"] = rank(dr[0][rows] @ dr[1][qi], H)
            r["rrf(pe:frames-win, drama)"] = rrf(r["pe:frames-win"], r["drama"])
            r["rrf(pe:frames-win, drama, bm25)"] = rrf(r["pe:frames-win"], r["drama"], r["bm25"])
            if "pe:glimmer" in r:
                r["rrf(pe:glimmer, drama)"] = rrf(r["pe:glimmer"], r["drama"])
            r["rrf(qwen, drama)"] = rrf(r["qwen"], r["drama"])
        r["rrf(pe:frames-win, bm25)"] = rrf(r["pe:frames-win"], r["bm25"])
        r["rrf(pe:frames-win, pe:text)"] = rrf(r["pe:frames-win"], r["pe:text"])
        r["rrf(qwen, bm25)"] = rrf(r["qwen"], r["bm25"])
        cl = [set(c) for c in e["clips"]]
        evs = set().union(*cl)
        for name, rk in r.items():
            a = agg.setdefault(name, {"n": 0, "hit8": 0, "any64": 0, "clip_rec64": 0.0, "mrr": 0.0})
            top8, top64 = set(rk[:8]), set(rk[:64])
            a["n"] += 1
            a["hit8"] += bool(top8 & evs)
            a["any64"] += bool(top64 & evs)
            a["clip_rec64"] += sum(bool(top64 & c) for c in cl) / len(cl)
            first = next((i for i, h in enumerate(rk) if h in evs), None)
            a["mrr"] += 1.0 / (first + 1) if first is not None else 0.0
    lines = ["| Retriever | Contests | hit@8 | any@64 | clip recall@64 | MRR |", "|---|---|---|---|---|---|"]
    for name, a in agg.items():
        n = a["n"]
        lines.append(f"| {name} | {n} | {100 * a['hit8'] / n:.1f}% | {100 * a['any64'] / n:.1f}% | {100 * a['clip_rec64'] / n:.1f}% | {a['mrr'] / n:.3f} |")
    text = "\n".join(lines) + "\n"
    (OUT / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    {"prep": prep, "rewrite": rewrite, "index": index, "drama": drama, "score": score}[sys.argv[1]]()
