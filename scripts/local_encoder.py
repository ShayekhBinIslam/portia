#!/usr/bin/env python3
"""portia/scripts/local_encoder.py: the judge's QUERY encoder on the BOX CPU (no GPU, no pod).

Same model, revision and instruction as the segment index
(Qwen3-VL-Embedding-8B @418d038) and the same HTTP interface as pod/embed_server.py, so judge/embed_client.py talks
to it unchanged except for the address. Measured: about 2 s per query on 32 threads, cosine 0.9998 against the
GPU-encoded cache; loading takes about 6 min.

    python scripts/local_encoder.py          (127.0.0.1:18531)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""                  # CPU only, whatever the caller's environment says
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pod" / "vendor" / "qwen3vl_repo"))
sys.path.insert(0, str(ROOT / "pod" / "vendor"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18531)
ap.add_argument("--threads", type=int, default=32)
ap.add_argument("--model", default="Qwen/Qwen3-VL-Embedding-8B")
ap.add_argument("--revision", default="418d03899aeb9d954e776dfa762006616519a914")
a = ap.parse_args()
torch.set_num_threads(a.threads)

from huggingface_hub import snapshot_download  # noqa: E402
from src.models.qwen3_vl_embedding import Qwen3VLEmbedder  # noqa: E402

t0 = time.time()
model = Qwen3VLEmbedder(model_name_or_path=snapshot_download(a.model, revision=a.revision, local_files_only=True),
                        max_length=32_000, dtype=torch.float32)
LOCK = threading.Lock()
print(f"[embed] {a.model}@{a.revision[:7]} loaded on CPU in {time.time() - t0:.0f}s, port {a.port}", flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send({"ok": True, "model": a.model, "revision": a.revision, "device": "box CPU", "mem_gb": 0})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            texts, instr = list(req["texts"]), req.get("instruction")
            t = time.time()
            with LOCK:
                vs = model.process([{"text": x, **({"instruction": instr} if instr else {})} for x in texts])
            out = [base64.b64encode(np.asarray(v.float() if hasattr(v, "float") else v, dtype="<f4").tobytes()).decode() for v in vs]
            print(f"[embed] {len(texts)} text(s) in {time.time() - t:.1f}s", flush=True)
            self._send({"dim": len(np.frombuffer(base64.b64decode(out[0]), dtype="<f4")), "vectors_b64": out})
        except Exception as e:  # noqa: BLE001
            self._send({"error": f"{type(e).__name__}: {e}"}, 500)


ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
