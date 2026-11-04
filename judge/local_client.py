"""portia/judge/local_client.py: the judge's chat client for a LOCAL OpenAI-compatible server (vLLM, see
scripts/serve_local_judge.sh): the same chat() interface as judge.openrouter.Client, with no quota and no keys.

Requests are cached by the sha1 of the body in .cache/llm_local/ (a separate cache: a local model never answers
for Nemotron). OpenRouter-only parameters are translated: reasoning {"effort": "low"} (the forced final answer)
becomes Qwen's chat_template_kwargs enable_thinking=False; "stream" is dropped (no proxy timeouts locally).
The server's reasoning_content is exposed as message["reasoning"] so trajectories log it like OpenRouter's.
Muse Glimmer (Meta open weights, scripts/serve_muse.sh) gets its own request profile: reasoning strength instead of
enable_thinking, and its recommended seeded sampling instead of temperature 0.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import requests

from judge import meta_lock
from judge.config import load as config
from judge.openrouter import CacheMiss

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "llm_local"


class LocalClient:
    def __init__(self, model: str = "q38", base_url: str = "http://127.0.0.1:18650/v1", log=print, timeout: int = 1800,
                 thinking: bool = False, strength: str = "high", salt: int = 0):
        meta_lock.check(base_url)      # the Meta hackathon API credits stay locked (meta_hackathon/.meta_locked)
        self.model, self.url, self.log, self.timeout = model, base_url.rstrip("/") + "/chat/completions", log, timeout
        # Muse Glimmer (scripts/serve_muse.sh, served as "mg30"): always reasons, at a strength set in its chat template
        # (also "portia-glimmer", its name on the Modal Endpoint: same weights, same sampling and reasoning settings)
        self.muse = model.startswith("mg") or "muse" in model.lower() or "glimmer" in model.lower()
        self.strength = strength
        self.supports_choice = True    # vLLM structured outputs: the agent's last-resort A/B verdict
        self.salt = salt               # != 0: an independent sample (other seeds) of the same requests
        # "kube://<pod>:<port>/v1": a server on a Kubernetes pod, reached per request with kubectl exec + curl
        # (the same transport as the query encoder; no port-forward to keep alive)
        self.kube = None
        if base_url.startswith("kube://"):
            pod, port = base_url[len("kube://"):].split("/")[0].split(":")
            self.kube = (pod, port)
        self.thinking = thinking       # off by default: with thinking on, one image turn takes ~80 s and often truncates
        CACHE.mkdir(parents=True, exist_ok=True)
        self.keys, self.sent, self.cached = [], 0, 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self._lock = threading.Lock()

    def used_today(self) -> int:
        return 0

    def cap_today(self) -> int:
        return 0

    def chat(self, messages: list, tools: list | None = None, tool_choice=None, cache_only: bool = False, **params) -> dict:
        reasoning = params.pop("reasoning", None)
        params.pop("stream", None)
        body = {"model": self.model, "messages": messages, **params}
        if tools:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        if self.muse:
            # Reasoning strength low/medium/high/xhigh is a chat-template variable; the forced final answer runs at low.
            # Never greedy (model card, vLLM recipe): its recommended sampling, seeded from the request itself so a rerun
            # reproduces it and the response cache stays meaningful. The reasoning parser needs the special tokens.
            low = not self.thinking or (reasoning and reasoning.get("effort") == "low")
            body["chat_template_kwargs"] = {"reasoning_strength": "low" if low else self.strength}
            body.update(**config("models")["muse_glimmer"]["sampling"], skip_special_tokens=False)
            seed_src = json.dumps(body, sort_keys=True, ensure_ascii=False) + (f"#salt{self.salt}" if self.salt else "")
            body["seed"] = int(hashlib.sha1(seed_src.encode()).hexdigest()[:8], 16) % 2 ** 31
        elif not self.thinking or (reasoning and reasoning.get("effort") == "low"):
            body["chat_template_kwargs"] = {"enable_thinking": False}
        ck = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        p = CACHE / f"{ck}.json"
        if p.exists():
            try:
                hit = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):                 # a half-written file (power cut): a miss, rewritten below
                hit = None
            if hit is not None:
                with self._lock:
                    self.cached += 1
                return hit
        if cache_only:
            raise CacheMiss(f"no cached local response {ck[:12]}")
        last = None
        for attempt in range(6):
            t = time.time()
            try:
                code, text = self._post(body)
            except (requests.RequestException, subprocess.SubprocessError, OSError) as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(10 * (attempt + 1))
                continue
            if code != 200:
                last = f"HTTP {code}: {text[:400]}"
                if code in (400, 404, 422):          # a malformed request does not get better on retry
                    break
                time.sleep(10 * (attempt + 1))
                continue
            try:
                j = json.loads(text)
            except json.JSONDecodeError as e:
                last = f"bad JSON from the server: {e}: {text[:200]}"
                time.sleep(10 * (attempt + 1))
                continue
            for ch in j.get("choices") or []:
                m = ch.get("message") or {}
                if m.get("reasoning_content") and not m.get("reasoning"):
                    m["reasoning"] = m["reasoning_content"]
            j["_latency_s"] = round(time.time() - t, 2)
            with self._lock:
                self.sent += 1
                for u in self.usage:
                    self.usage[u] += int((j.get("usage") or {}).get(u) or 0)
            if ((j.get("choices") or [{}])[0].get("finish_reason")) != "error":
                tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")         # atomic: a power cut never leaves half a file
                tmp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, p)
            return j
        raise RuntimeError(f"local judge call failed: {last}")

    def _post(self, body: dict) -> tuple[int, str]:
        """(HTTP status, response text) from the server, directly or through kubectl exec on the pod."""
        if not self.kube:
            # a hosted Muse Glimmer (a Modal Endpoint or Fireworks) wants its key as a bearer token; local servers need none
            key = os.environ.get("PORTIA_GLIMMER_KEY", "")
            r = requests.post(self.url, json=body, timeout=self.timeout,
                              headers={"Authorization": f"Bearer {key}"} if key else None)
            return r.status_code, r.text
        pod, port = self.kube
        cmd = ["kubectl", "--kubeconfig", os.path.expanduser(os.environ.get("PORTIA_KUBECONFIG", "~/.kube/config")), "exec", "-i", pod, "--",
               "curl", "-s", "-m", str(self.timeout), "-w", "\n%{http_code}", "-X", "POST",
               "-H", "Content-Type: application/json", "--data-binary", "@-", f"127.0.0.1:{port}/v1/chat/completions"]
        r = subprocess.run(cmd, input=json.dumps(body).encode(), capture_output=True, timeout=self.timeout + 60,
                           env={**os.environ, "KUBECTL_REMOTE_COMMAND_WEBSOCKETS": "false"})
        out = r.stdout.decode(errors="replace")
        text, _, code = out.rpartition("\n")
        if r.returncode or not code.strip().isdigit():
            raise subprocess.SubprocessError(f"kubectl exec rc={r.returncode}: {r.stderr.decode(errors='replace')[:200]} {out[-200:]}")
        return int(code), text

