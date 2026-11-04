"""portia/judge/embed_client.py: encode the agents' search queries with the index's own model, on demand.

A query is embedded with Qwen3-VL-Embedding-8B at the revision the segment index was built with, and with the same
query instruction. By default the encoder is scripts/local_encoder.py on the host's CPU (PORTIA_ENCODER=local);
PORTIA_ENCODER=pod reaches pod/embed_server.py on a Kubernetes pod through `kubectl exec` instead. Every vector is
cached under .cache/query_emb/<model>/<sha1>.npy, so a query is encoded at most once.

On a cache miss in pod mode the client:
  1. asks the server for /health via `kubectl exec ... curl 127.0.0.1:<port>` (no port-forward);
  2. if it is down: pushes ONLY the pod files that changed (md5-compared) and runs pod/start_embed.sh, which picks
     the emptiest GPU;
  3. posts the batch and stores the vectors.
The server exits by itself after 30 idle minutes, so nothing squats on a shared GPU between runs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]                      # the repo root
from judge.config import load as _config                       # noqa: E402  (configs/models.yaml)
_Q = _config("models")["query_encoder"]
POD = _Q["pod"]["name"]
KUBECONFIG = os.path.expanduser(_Q["pod"]["kubeconfig"])
POD_ROOT = _Q["pod"]["root"]                                  # same path on the pod (/data2 link)
PORT = int(_Q["pod"]["port"])
MODEL = _Q["model"]
REVISION = _Q["revision"]
INSTRUCTION = ("Given a complex multi-hop web search query with a reference answer where the answer is "
               "dispersed in multiple passages, retrieve all relevant passages required to answer that query")
POD_FILES = ["pod/embed_server.py", "pod/start_embed.sh",
             "pod/vendor/qwen3vl_repo/src/models/qwen3_vl_embedding.py"]
CACHE = ROOT / ".cache" / "query_emb" / MODEL.replace("/", "--")
ENV = {**os.environ, "KUBECTL_REMOTE_COMMAND_WEBSOCKETS": "false"}   # SPDY exec: far fewer drops here
_START = threading.Lock()          # worker threads share one encoder: only one of them may start it
# The encoder runs on the host CPU by default (scripts/local_encoder.py); the pod path below is kept but only used
# with PORTIA_ENCODER=pod.
MODE = os.environ.get("PORTIA_ENCODER", "local")
LOCAL = "http://127.0.0.1:18531"


def _kube(args: list[str], stdin: bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ["kubectl", "--kubeconfig", KUBECONFIG, "exec"] + (["-i"] if stdin is not None else []) + [POD, "--", *args]
    return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout, env=ENV)


def _key(text: str, instruction: str) -> str:
    return hashlib.sha1("\x00".join((MODEL, REVISION, instruction, text)).encode()).hexdigest()


class QueryEncoder:
    def __init__(self, instruction: str = INSTRUCTION, log=print):
        self.instruction, self.log = instruction, log
        CACHE.mkdir(parents=True, exist_ok=True)
        self.pod_calls = 0

    # ------------------------------------------------------------------ server lifecycle
    def healthy(self) -> dict | None:
        if MODE == "local":
            try:
                import requests
                r = requests.get(f"{LOCAL}/health", timeout=5)
                return r.json() if r.ok else None
            except Exception:
                return None
        try:
            r = _kube(["curl", "-sf", "-m", "5", f"127.0.0.1:{PORT}/health"], timeout=60)
            return json.loads(r.stdout) if r.returncode == 0 and r.stdout else None
        except Exception:
            return None

    def _push_changed(self):
        """Copy only the pod files whose md5 differs from the local copy."""
        for rel in POD_FILES:
            local = ROOT / rel
            want = hashlib.md5(local.read_bytes()).hexdigest()
            r = _kube(["bash", "-c", f"md5sum {POD_ROOT}/{rel} 2>/dev/null | cut -d' ' -f1"], timeout=60)
            if r.stdout.decode().strip() == want:
                continue
            dst = f"{POD_ROOT}/{rel}"
            r = _kube(["bash", "-c", f"mkdir -p $(dirname {dst}) && cat > {dst}.tmp && mv {dst}.tmp {dst}"],
                      stdin=local.read_bytes(), timeout=120)
            if r.returncode:
                raise RuntimeError(f"push {rel} failed: {r.stderr.decode()[:300]}")
            self.log(f"[embed] pushed {rel} to the pod")

    def ensure(self, wait_s: int = 600) -> dict:
        h = self.healthy()
        if h:
            return h
        if MODE == "local":                      # never fall back to the pod
            raise RuntimeError("the local query encoder is not running: python scripts/local_encoder.py (about 6 min to load)")
        with _START:
            h = self.healthy()                   # another thread may have started it meanwhile
            if h:
                return h
            return self._start(wait_s)

    def _start(self, wait_s: int) -> dict:
        try:                                                            # the run-id tool of the author's box, if any
            sys.path.insert(0, os.path.join(os.environ["PORTIA_TITLE_TOOLS"], "scripts"))
            from runid import new_run_id
            rid = new_run_id("Portia query encoder (Qwen3-VL-Embedding-8B)", f"{POD_ROOT}/logs/<rid>.log")
        except (KeyError, ImportError):
            rid = uuid.uuid4().hex[:8]
        self._push_changed()
        r = _kube(["bash", "-c", f"RID={rid} bash {POD_ROOT}/pod/start_embed.sh {PORT}"], timeout=120)
        out = (r.stdout + r.stderr).decode().strip()
        self.log(f"[embed] start (shayekh-{rid}): {out}")
        if "NO_GPU" in out or r.returncode not in (0,):
            raise RuntimeError(f"encoder not started: {out}")
        t = time.time()
        while time.time() - t < wait_s:
            time.sleep(10)
            h = self.healthy()
            if h:
                self.log(f"[embed] up after {time.time() - t:.0f}s on {h['device']} ({h['mem_gb']} GB)")
                return h
        raise TimeoutError(f"encoder did not come up in {wait_s}s; see {POD_ROOT}/logs/{rid}.log on the pod")

    # ------------------------------------------------------------------ encoding
    def encode(self, texts: list[str]) -> np.ndarray:
        out: list = [None] * len(texts)
        miss = []
        for i, t in enumerate(texts):
            p = CACHE / f"{_key(t, self.instruction)}.npy"
            if p.exists():
                out[i] = np.load(p)
            else:
                miss.append(i)
        if miss:
            self.ensure()
            for s in range(0, len(miss), 32):
                idx = miss[s:s + 32]
                body = json.dumps({"texts": [texts[i] for i in idx], "instruction": self.instruction}).encode()
                for attempt in range(4):
                    if MODE == "local":
                        import requests
                        try:
                            rr = requests.post(f"{LOCAL}/embed", data=body, timeout=900,
                                               headers={"Content-Type": "application/json"})
                            r = subprocess.CompletedProcess([], 0, rr.content, b"")
                        except Exception as e:
                            r = subprocess.CompletedProcess([], 1, b"{}", str(e).encode())
                    else:
                        r = _kube(["curl", "-s", "-m", "300", "-X", "POST", "-H", "Content-Type: application/json",
                                   "--data-binary", "@-", f"127.0.0.1:{PORT}/embed"], stdin=body, timeout=360)
                    self.pod_calls += 1
                    try:
                        j = json.loads(r.stdout)
                        if "error" in j:
                            raise RuntimeError(j["error"])
                        break
                    except Exception as e:
                        if attempt == 3:
                            raise RuntimeError(f"encode failed: {e}; {r.stderr.decode()[:200]}")
                        time.sleep(5 * (attempt + 1))
                        self.ensure()
                for i, b in zip(idx, j["vectors_b64"]):
                    v = np.frombuffer(base64.b64decode(b), dtype="<f4").copy()
                    np.save(CACHE / f"{_key(texts[i], self.instruction)}.npy", v)
                    out[i] = v
        return np.stack(out)
