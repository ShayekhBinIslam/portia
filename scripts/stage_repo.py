#!/usr/bin/env python3
"""portia/scripts/stage_repo.py: copy Portia's public repo from an ALLOWLIST (audit 021): only hackathon code, docs and
text records; never keys, caches, runs, videos or frames. Then scan the copy for secrets.

    python scripts/stage_repo.py <dest>        # writes <dest>/ (refuses a non-empty dest unless --update)

Pre-existing material stays out (the rules: a fresh repo with only event work): the benchmark, its videos and
transcripts, and the segment index. The README says where they come from and how to point Portia at them.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = [
    "judge/*.py", "prompts/**/*", "tools/*", "analysis/*.py", "configs/*.yaml",
    "product/server.py", "product/engine.py", "product/ingest.py", "product/build_static.py",
    "product/README.md", "product/DEMO_SCRIPT.md", "product/static/**/*", "product/video/*.py",
    "product/gloss_questions.py", "product/glosses.json",        # Muse Glimmer's one-line versions of the questions
    "scripts/serve_muse.sh", "scripts/gpu_run.sh", "scripts/deploy_fireworks.py", "scripts/local_encoder.py", "scripts/static_server.py", "scripts/gpu_queue.py",
    "scripts/stage_repo.py", "audits/*.md", "meta_hackathon/NEW_WORK.md",
    # the static gallery for judges without a GPU: the app and its JSON records, never its media/ (frames, clips)
    "product/site/index.html", "product/site/static/**/*", "product/site/data/**/*",
]
# recorded runs shown in the video and the gallery: their text records only (job.json, events.jsonl), no frames
RUNS = ["1102-120834-5a94", "1030-064048-0741", "1103-034653-7b39", "1104-151224-a5ab"]
# the uploaded film (Blender's Tears of Steel, CC BY 3.0): its frames and clip may be shared with the credit
CC_MEDIA = ["product/site/media/1104-151224-a5ab/*"]
NEVER = re.compile(r"(\.env$|\.env\.|public\.env|meta_hack\.env|tunnel_token|\.meta_locked|paths\.local\.json|__pycache__|"
                   r"\.pyc$|\.jpg$|\.png$|\.mp4$|\.webm$|\.wav$|\.npy$|\.npz$)")
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{20,}|"
                    r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})")


def secret_values() -> list[str]:
    """Every value in the key files, to check the copy never contains one (values are never printed)."""
    vals = []
    for f in (ROOT / "meta_hackathon" / "meta_hack.env", ROOT / "product" / "public.env", ROOT / ".env",
              ROOT / "product" / ".tunnel_token", ROOT / "modal_endpoint.env", ROOT / "modal_glimmer_secret.env"):
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                v = line.split("=", 1)[1].strip().strip("'\"") if "=" in line else line.strip()
                if len(v) >= 8 and not line.lstrip().startswith("#"):
                    vals.append(v)
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args()
    dest = Path(a.dest).resolve()
    if dest.exists() and any(dest.iterdir()) and not a.update:
        raise SystemExit(f"{dest} is not empty (use --update)")
    files = sorted({p for pat in ALLOW for p in ROOT.glob(pat) if p.is_file() and not NEVER.search(str(p))}
                   | set((ROOT / "product" / "static" / "brand").glob("*.png"))      # Portia's own logo images
                   | {p for pat in CC_MEDIA for p in ROOT.glob(pat) if p.is_file()})
    for jid in RUNS:
        for name in ("job.json", "events.jsonl"):
            p = ROOT / "product" / "jobs" / jid / name
            if p.exists():
                files.append(p)
    # the repo's own top-level files (README, .env.example, .gitignore, requirements), kept in repo_root/
    tops = [p for p in (ROOT / "repo_root").iterdir() if p.is_file()]
    n = 0
    for p in files:
        dst = dest / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        n += 1
    for p in tops:                                          # after the tree exists
        shutil.copy2(p, dest / p.name)
        n += 1
    vals, hits = secret_values(), []
    for p in dest.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if SECRET.search(t) or any(v in t for v in vals):
            hits.append(str(p.relative_to(dest)))
    size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts)
    print(json.dumps({"files": n, "size_mb": round(size / 1e6, 1), "secret_hits": hits}, indent=1))
    if hits:
        sys.exit(1)


if __name__ == "__main__":
    main()
