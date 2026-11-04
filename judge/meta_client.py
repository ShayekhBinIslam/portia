"""portia/judge/meta_client.py: Muse Spark 1.3 Contributor on the Meta Model API, with LocalClient's chat() interface.

User: "please unlock cap $2", then "it's fine, they may train; my call, try both 1 and 2, it's cheap!!".
judge/meta_lock.py hands over only META_DEV_KEY and only for this model (api.meta.ai); the key goes in the Authorization
header and nowhere else. The contributor tier may train on what is sent; the user accepted that for plan 013.

The API is OpenAI-compatible (chat completions); it accepts only tool_choice "auto", so a forced tool is emulated by
offering only that tool. As judge/baseten_client.py: the structured A/B choice becomes a
JSON-schema response_format, every response is cached by request hash (.cache/llm_meta/), and each request's cost
(exact usage x the contributor prices) is appended to runs/meta_spend.jsonl. A request is refused once the logged
spend under this client's tag reaches budget_usd, or the total reaches the user's cap (meta_lock.META_DEV_CAP_USD).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

import requests

from judge import meta_lock
from judge.config import load as config

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "llm_meta"
SPEND = ROOT / "runs" / "meta_spend.jsonl"
PRICE = dict(config("models")["muse_spark_13"]["price"])       # muse-spark-1.3-contributor (dev.meta.ai pricing)


class BudgetExceeded(RuntimeError):
    pass


def spent(tag: str | None = None) -> float:
    if not SPEND.exists():
        return 0.0
    rows = []
    for line in SPEND.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line)) if line.strip() else None
        except ValueError:                                  # a half-written line (power cut)
            pass
    return sum(r.get("usd", 0.0) for r in rows if tag is None or r.get("tag") == tag)


class MetaClient:
    def __init__(self, log=print, strength: str = "high", salt: int = 0, budget_usd: float = 1.0, tag: str = "",
                 timeout: int = 900, run: str = "", reasoning_effort: bool = True):
        self.url = meta_lock.META_API_URL + "/chat/completions"
        meta_lock.check(self.url)
        self._key = meta_lock.dev_key()                   # never logged
        self.model = meta_lock.META_DEV_MODEL
        self.log, self.timeout, self.strength, self.salt = log, timeout, strength, salt
        self.budget, self.tag, self.run = budget_usd, tag, run or tag
        self.reasoning_effort = reasoning_effort          # set False if the API rejects the field
        self.supports_choice = True
        self.muse = True
        self.keys, self.sent, self.cached = [], 0, 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        self._lock = threading.Lock()
        CACHE.mkdir(parents=True, exist_ok=True)

    def used_today(self) -> int:
        return 0

    def cap_today(self) -> int:
        return 0

    def chat(self, messages: list, tools: list | None = None, tool_choice=None, cache_only: bool = False, **params) -> dict:
        reasoning = params.pop("reasoning", None)
        choice = (params.pop("structured_outputs", None) or {}).get("choice")
        params.pop("stream", None)
        params.pop("temperature", None)
        body = {"model": self.model, "messages": messages, "max_tokens": int(params.pop("max_tokens", 16384)),
                "temperature": 1.0, "top_p": 0.95}
        if self.reasoning_effort:
            body["reasoning_effort"] = "low" if (reasoning and reasoning.get("effort") == "low") else self.strength
        if tools:
            body["tools"] = tools
        if isinstance(tool_choice, dict):
            # the API accepts only tool_choice "auto" (a named choice is a 400): forcing one tool = offering only it
            name = (tool_choice.get("function") or {}).get("name")
            body["tools"] = [x for x in (tools or []) if (x.get("function") or {}).get("name") == name] or tools
            body["tool_choice"] = "auto"
        elif tool_choice is not None:
            body["tool_choice"] = tool_choice
        if choice:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
                "type": "object", "properties": {"choice": {"type": "string", "enum": list(choice)}},
                "required": ["choice"], "additionalProperties": False}}}
        seed_src = json.dumps(body, sort_keys=True, ensure_ascii=False) + (f"#salt{self.salt}" if self.salt else "")
        body["seed"] = int(hashlib.sha1(seed_src.encode()).hexdigest()[:8], 16) % 2 ** 31
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
            raise RuntimeError(f"no cached Meta API response {ck[:12]}")
        with self._lock:
            if spent() >= meta_lock.META_DEV_CAP_USD:
                raise BudgetExceeded(f"Meta API cap reached: ${spent():.4f} >= ${meta_lock.META_DEV_CAP_USD:.2f}")
            if spent(self.tag or None) >= self.budget:
                raise BudgetExceeded(f"Meta API budget reached: ${spent(self.tag or None):.4f} >= ${self.budget:.2f} (tag {self.tag or 'all'})")
        last = None
        for attempt in range(6):
            t = time.time()
            try:
                r = requests.post(self.url, json=body, timeout=self.timeout,
                                  headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
            except requests.RequestException as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code != 200:
                last = f"HTTP {r.status_code}: {r.text[:400]}"
                if r.status_code in (400, 401, 403, 404, 422):
                    break
                time.sleep(10 * (attempt + 1))                     # 429 (150 requests/min) and 5xx: back off
                continue
            j = r.json()
            for ch in j.get("choices") or []:
                m = ch.get("message") or {}
                if m.get("reasoning_content") and not m.get("reasoning"):
                    m["reasoning"] = m["reasoning_content"]
                if choice and m.get("content"):
                    try:
                        v = json.loads(m["content"]).get("choice")
                        if v in choice:
                            m["content"] = v
                    except (json.JSONDecodeError, AttributeError):
                        pass
            j["_latency_s"] = round(time.time() - t, 2)
            u = j.get("usage") or {}
            pt = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
            ct = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
            cached_t = int(((u.get("prompt_tokens_details") or u.get("input_tokens_details") or {}).get("cached_tokens")) or 0)
            usd = (pt - cached_t) * PRICE["in"] + cached_t * PRICE["cached"] + ct * PRICE["out"]
            with self._lock:
                self.sent += 1
                self.usage["prompt_tokens"] += pt
                self.usage["completion_tokens"] += ct
                with open(SPEND, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": self.tag, "run": self.run, "model": self.model,
                                        "prompt": pt, "cached": cached_t, "completion": ct, "usd": round(usd, 8)}) + "\n")
            tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")         # atomic: a power cut never leaves half a file
            tmp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
            return j
        raise RuntimeError(f"Meta API call failed: {last}")


def report() -> str:
    import collections
    rows = [json.loads(l) for l in SPEND.read_text(encoding="utf-8").splitlines() if l.strip()] if SPEND.exists() else []
    by = collections.defaultdict(lambda: [0, 0.0])
    for r in rows:
        b = by[f"{r.get('tag') or '-'} / {r.get('run') or '-'}"]
        b[0] += 1
        b[1] += r["usd"]
    out = [f"Meta API spend (tracked locally): ${sum(r['usd'] for r in rows):.4f} of the ${meta_lock.META_DEV_CAP_USD:.2f} cap"]
    out += [f"  {k:40s} {n:5d} requests  ${v:.4f}" for k, (n, v) in sorted(by.items(), key=lambda kv: -kv[1][1])]
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
