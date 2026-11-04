"""portia/judge/baseten_client.py: Muse Spark Open on Baseten (the hackathon key), with LocalClient's chat() interface.

User: "let's unlock baseten key only (keep meta api locked)". judge/meta_lock.py hands over only
META_BASETEN_KEY and keeps refusing Meta's own API. The key is sent in the Authorization header and nowhere else.

Baseten speaks OpenAI Chat Completions (https://inference.baseten.co/v1, model meta-models/muse-spark-open-1026, the
only model the hackathon key works with). vLLM-only fields of the local client are translated or dropped:
  reasoning strength          -> reasoning_effort (Spark Open always reasons; Baseten's default is xhigh)
  structured_outputs choice   -> a JSON-schema response_format; the reply is turned back into the bare letter
  top_k, chat_template_kwargs, skip_special_tokens -> dropped
Responses come back with reasoning in reasoning_content; it is exposed as message["reasoning"] like the local client.
Every response is cached by request hash in .cache/llm_baseten/ (a rerun costs nothing), and its cost is appended to
runs/baseten_spend.jsonl (report: python -m judge.baseten_client). A request is refused when the spend logged under this
client's tag would exceed budget_usd, or when the total would exceed TOTAL_CAP_USD.
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
CACHE = ROOT / ".cache" / "llm_baseten"
SPEND = ROOT / "runs" / "baseten_spend.jsonl"
PRICE = dict(config("models")["muse_spark_open"]["price"])     # USD per token (Baseten Model API)
CREDIT_USD = float(config("budgets")["baseten"]["credit_usd"])          # Baseten's hackathon credits
TOTAL_CAP_USD = float(config("budgets")["baseten"]["total_cap_usd"])    # never spend past this across all runs
# The hackathon key cannot read Baseten's billing API (GET /v1/billing/usage_summary -> 403 PERMISSION_DENIED),
# so spend is tracked here: exact token counts from each response's usage x the listed prices.


class BudgetExceeded(RuntimeError):
    pass


def spent(tag: str | None = None) -> float:
    """USD logged so far, for one tag (a run name) or in total."""
    if not SPEND.exists():
        return 0.0
    tot = 0.0
    for line in SPEND.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except ValueError:                              # a half-written line (power cut)
                continue
            if tag is None or r.get("tag") == tag:
                tot += r.get("usd", 0.0)
    return tot


class BasetenClient:
    def __init__(self, log=print, strength: str = "high", salt: int = 0, budget_usd: float = 5.0, tag: str = "",
                 timeout: int = 900, run: str = ""):
        meta_lock.check(meta_lock.BASETEN_URL)
        self._key = meta_lock.baseten_key()              # never logged
        self.model, self.url = meta_lock.BASETEN_MODEL, meta_lock.BASETEN_URL + "/chat/completions"
        self.log, self.timeout, self.strength, self.salt = log, timeout, strength, salt
        self.budget, self.tag, self.run = budget_usd, tag, run or tag     # tag = budget group, run = run name
        self.supports_choice = True                      # through response_format (json_schema)
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
        params.pop("temperature", None)                  # Muse's recommended sampling instead (as the local client)
        body = {"model": self.model, "messages": messages, "max_tokens": int(params.pop("max_tokens", 16384)),
                "temperature": 1.0, "top_p": 0.95,
                "reasoning_effort": "low" if (reasoning and reasoning.get("effort") == "low") else self.strength}
        if tools:
            body["tools"] = tools
        if tool_choice is not None:
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
            raise RuntimeError(f"no cached Baseten response {ck[:12]}")
        with self._lock:
            if spent() >= TOTAL_CAP_USD:
                raise BudgetExceeded(f"Baseten total cap reached: ${spent():.2f} >= ${TOTAL_CAP_USD:.2f} of ${CREDIT_USD:.0f} credits")
            if spent(self.tag or None) >= self.budget:
                raise BudgetExceeded(f"Baseten budget reached: ${spent(self.tag or None):.2f} >= ${self.budget:.2f} "
                                     f"(tag {self.tag or 'all'})")
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
                    break                                # a bad request or key does not get better on retry
                time.sleep(10 * (attempt + 1))
                continue
            j = r.json()
            for ch in j.get("choices") or []:
                m = ch.get("message") or {}
                if m.get("reasoning_content") and not m.get("reasoning"):
                    m["reasoning"] = m["reasoning_content"]
                if choice and m.get("content"):          # back to the bare letter the caller's parser expects
                    try:
                        v = json.loads(m["content"]).get("choice")
                        if v in choice:
                            m["content"] = v
                    except (json.JSONDecodeError, AttributeError):
                        pass
            j["_latency_s"] = round(time.time() - t, 2)
            u = j.get("usage") or {}
            pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
            cached_t = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
            usd = (pt - cached_t) * PRICE["in"] + cached_t * PRICE["cached"] + ct * PRICE["out"]
            with self._lock:
                self.sent += 1
                self.usage["prompt_tokens"] += pt
                self.usage["completion_tokens"] += ct
                with open(SPEND, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": self.tag, "run": self.run, "model": self.model,
                                        "prompt": pt, "cached": cached_t, "completion": ct, "usd": round(usd, 6)}) + "\n")
            tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")         # atomic: a power cut never leaves half a file
            tmp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
            return j
        raise RuntimeError(f"Baseten call failed: {last}")


def report() -> str:
    """Spend so far: total, per run tag, per day, and what is left of the credits."""
    import collections
    rows = [json.loads(l) for l in SPEND.read_text(encoding="utf-8").splitlines() if l.strip()] if SPEND.exists() else []
    tot = sum(r["usd"] for r in rows)
    by_tag, by_day = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0]), collections.defaultdict(float)
    for r in rows:
        b = by_tag[f"{r.get('tag') or '(none)'} / {r.get('run') or r.get('tag') or '-'}"]
        b[0] += 1; b[1] += r["usd"]; b[2] += r["prompt"]; b[3] += r["cached"]; b[4] += r["completion"]
        by_day[r["ts"][:10]] += r["usd"]
    out = [f"Baseten spend (tracked locally; the hackathon key cannot read Baseten's billing API): ${tot:.4f} of "
           f"${CREDIT_USD:.0f} credits, ${CREDIT_USD - tot:.2f} left (hard cap ${TOTAL_CAP_USD:.0f})", "", "by budget group / run:"]
    for t, (n, usd, p_, c, o) in sorted(by_tag.items(), key=lambda kv: -kv[1][1]):
        out.append(f"  {t:28s} {n:5d} requests  ${usd:8.4f}  input {p_:,} (cached {c:,})  output {o:,}")
    out += ["", "by day (UTC):"] + [f"  {d}  ${v:.4f}" for d, v in sorted(by_day.items())]
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
