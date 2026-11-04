#!/usr/bin/env python3
"""portia/scripts/gpu_queue.py: a self-feeding GPU work queue for GPUs 0 and 3: Portia-default investigator seeds on
the development shards and their Glimmer evidence-only adjudications, so the GPUs never sit idle while nobody is around.

    python scripts/gpu_queue.py worker --port 18660      # one worker per vLLM server (GPU 3: 18660, GPU 0: 18661)
    python scripts/gpu_queue.py status                   # what is done, claimed and next

User: "auto-continue when back", "auto continue please" (the GPUs idled ~11 h overnight after a finite
queue ran out). Work is derived, not stored: triples of seeds (20,21,22), (23,24,25), ... up to seed MAX_SEED; per
triple, each seed on shards 3 and 4 (8 turns, reasoning high: Portia's default) and, once its six runs are done, the
Glimmer evidence-only adjudication with seed salts 0 and 1. A run is done when runs/<name>/summary.json exists; a
worker claims an item with mkdir runs/queue/claims/<item> (holding its pid and boot id; stale claims, from a dead pid
or an earlier boot, are taken over and the run resumes where it stopped). Each worker prefers the next seed run, and
takes an adjudication as soon as one is ready. It waits for its vLLM server before every item.
Stop: touch runs/queue/STOP (workers finish their current item and exit).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from judge.config import load as config  # noqa: E402  (configs/queue.yaml)

ROOT = Path(__file__).resolve().parents[1]
Q = ROOT / "runs" / "queue"
PY = os.environ.get("PORTIA_PY", sys.executable)          # the env the worker runs in
FIRST_SEED, MAX_SEED = int(config("queue")["first_seed"]), int(config("queue")["max_seed"])
SHARD = dict(config("queue")["shards"])


def boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def done(run: str) -> bool:
    return (ROOT / "runs" / run / "summary.json").exists()


def items():
    """Every work item in order: (id, kind, payload, dependencies)."""
    for a in range(FIRST_SEED, MAX_SEED + 1 - 2, 3):
        seeds = (a, a + 1, a + 2)
        runs = [f"mg_v4t_r{s}" for s in seeds]
        for s in seeds:
            for sh in ("s3", "s4"):
                yield f"seed-{s}-{sh}", "seed", {"seed": s, "shard": sh}, []
        deps = [f"{r}_{sh}" for r in runs for sh in ("s3", "s4")]
        for salt in (0, 1):
            name = f"mg_adjev_t{a}{a + 1}{a + 2}" + (f"_r{salt}" if salt else "")
            yield f"adj-{name}", "adj", {"name": name, "runs": runs, "salt": salt}, deps


def extras():
    """Priority items (plan 019): runs/queue/extra.jsonl, one JSON object per line: {"id", "deps": [run names],
    "steps": [{"name": run name, "argv": [...]}]}; "{url}" in argv becomes the worker's server. Workers take a ready
    extra before any seed run or adjudication."""
    f = Q / "extra.jsonl"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            yield f"x-{e['id']}", "cmd", e, e.get("deps", [])


def outputs(kind: str, p: dict) -> list[str]:
    if kind == "cmd":
        return [st["name"] for st in p["steps"]]
    if kind == "seed":
        return [f"mg_v4t_r{p['seed']}_{p['shard']}"]
    return [f"{p['name']}_s3", f"{p['name']}_s4"]


def claim(item: str) -> bool:
    d = Q / "claims" / item
    try:
        d.mkdir(parents=True)
    except FileExistsError:
        try:
            c = json.loads((d / "owner.json").read_text())
            alive = c.get("boot") == boot_id() and Path(f"/proc/{c.get('pid')}").exists()
        except (OSError, ValueError):
            alive = (time.time() - d.stat().st_mtime) < 30      # being written right now
        if alive:
            return False
        # stale claim (dead worker or an earlier boot): take it over
    (d / "owner.json").write_text(json.dumps({"pid": os.getpid(), "boot": boot_id(), "since": time.time()}))
    return json.loads((d / "owner.json").read_text()).get("pid") == os.getpid()


def server_up(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=5) as r:
            return r.status == 200
    except OSError:
        return False


def log(msg: str):
    t = time.strftime("%a %I:%M %p", time.gmtime(time.time() + 9 * 3600))
    print(f"[queue {t}] {msg}", flush=True)


def run_item(kind: str, p: dict, port: int):
    url = f"http://127.0.0.1:{port}/v1"
    if kind == "cmd":
        cmds = [(st["name"], [a.replace("{url}", url) for a in st["argv"]]) for st in p["steps"] if not done(st["name"])]
    elif kind == "seed":
        name = f"mg_v4t_r{p['seed']}_{p['shard']}"
        cmd = [PY, "judge/run.py", "--backend", "local", "--model", "mg30", "--local-thinking", "--reasoning-strength", "high",
               "--max-tokens", "16384", "--tools", "v4", "--keep-reasoning", "--budget-note", "--final-full-reasoning",
               "--seed-salt", str(p["seed"]), "--workers", "12", "--local-url", url, "--shard", SHARD[p["shard"]], "--name", name]
        cmds = [(name, cmd)]
    else:
        cmds = []
        for sh in ("s3", "s4"):
            name = f"{p['name']}_{sh}"
            if done(name):
                continue
            cmd = [PY, "judge/adjudicate.py", "--runs", ",".join(f"{r}_{sh}" for r in p["runs"]), "--shard", SHARD[sh],
                   "--name", name, "--variant", "evidence", "--seed-salt", str(p["salt"]), "--model", "mg30",
                   "--local-url", url, "--local-thinking", "--max-tokens", "16384", "--workers", "8"]
            cmds.append((name, cmd))
    for name, cmd in cmds:
        with open(ROOT / "logs" / f"{name}.log", "a") as f:
            subprocess.run(["nice", "-n", "10", *cmd], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
        log(f"{name}: {'done' if done(name) else 'ended without a summary'}")


def live_claim(item: str) -> bool:
    try:
        c = json.loads((Q / "claims" / item / "owner.json").read_text())
        return c.get("boot") == boot_id() and Path(f"/proc/{c.get('pid')}").exists()
    except (OSError, ValueError):
        return (Q / "claims" / item).exists()


def next_item(port: int):
    for item, kind, p, deps in extras():                       # plan 019: experiments first
        if not all(done(o) for o in outputs(kind, p)) and all(done(d) for d in deps) and not live_claim(item):
            return item, kind, p
    ready_adj, first_seed = None, None
    for item, kind, p, deps in items():
        if all(done(o) for o in outputs(kind, p)):
            continue
        if (Q / "claims" / item).exists():
            try:
                c = json.loads((Q / "claims" / item / "owner.json").read_text())
                if c.get("boot") == boot_id() and Path(f"/proc/{c.get('pid')}").exists():
                    continue                                   # another live worker has it
            except (OSError, ValueError):
                continue
        if kind == "adj":
            if ready_adj is None and all(done(d) for d in deps):
                ready_adj = (item, kind, p)
        elif first_seed is None:
            first_seed = (item, kind, p)
        if ready_adj and first_seed:
            break
    return ready_adj or first_seed                             # a ready adjudication first: it frees the triple


def worker(port: int):
    Q.mkdir(parents=True, exist_ok=True)
    log(f"worker for port {port} started (pid {os.getpid()})")
    while not (Q / "STOP").exists():
        if not server_up(port):
            log(f"waiting for the vLLM server on port {port}")
            while not server_up(port) and not (Q / "STOP").exists():
                time.sleep(30)
            continue
        nxt = next_item(port)
        if nxt is None:
            log("nothing left to run (seeds up to MAX_SEED done); exiting")
            return
        item, kind, p = nxt
        if not claim(item):
            time.sleep(2)
            continue
        log(f"port {port}: {item}")
        run_item(kind, p, port)
        if all(done(o) for o in outputs(kind, p)):
            (Q / "done").mkdir(exist_ok=True)
            (Q / "done" / item).touch()
        else:
            time.sleep(60)                                     # e.g. the server went down mid-run; retry later
    log("STOP file found; exiting")


def status():
    rows = []
    for item, kind, p, deps in items():
        st = "done" if all(done(o) for o in outputs(kind, p)) else ("claimed" if (Q / "claims" / item).exists() else
             ("ready" if kind == "seed" or all(done(d) for d in deps) else "waiting"))
        rows.append((item, st))
    shown = [r for r in rows if r[1] != "done"][:8]
    print(f"{sum(r[1] == 'done' for r in rows)} of {len(rows)} items done; next: " + ", ".join(f"{i} ({s})" for i, s in shown))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["worker", "status"])
    ap.add_argument("--port", type=int, default=18660)
    a = ap.parse_args()
    worker(a.port) if a.cmd == "worker" else status()
