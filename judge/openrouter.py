"""portia/judge/openrouter.py: OpenRouter chat-completions client for the tool-using judge.

Built around the FREE tier's limits, which are the binding constraint of this project:
  * :free models: 20 requests/minute, and 50 requests/day while the account has bought < $10 of
    credits (1,000/day after). The key reports is_free_tier; check `python -m judge.openrouter`.
  * so every request is counted in a local per-UTC-day LEDGER (.cache/openrouter_ledger.json) and the
    client REFUSES to go past `daily_cap` instead of letting the provider 429 a half-finished contest;
  * requests are throttled to >= 60/20 s apart;
  * every response is cached by the sha1 of the request body (.cache/llm/), so re-running a trajectory
    that would send identical requests costs nothing and needs no quota.

The key is OPEN_ROUTER_API_KEY from the environment, else .env or the PORTIA_EXTRA_ENV file (never printed).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
from judge.config import load as _config  # noqa: E402
URL = _config("models")["openrouter"]["url"]
CACHE = ROOT / ".cache" / "llm"
LEDGER = ROOT / ".cache" / "openrouter_ledger.json"
from judge.paths import EXTRA_ENV  # noqa: E402
ENV_FILES = [ROOT / ".env"] + ([EXTRA_ENV] if EXTRA_ENV else [])


RESERVE = {v.strip() for v in os.environ.get("PORTIA_RESERVE_KEYS", "OPEN_ROUTER_API_KEY8").split(",") if v.strip()}


def api_keys() -> list[tuple[str, str]]:
    """Every OpenRouter key on offer: OPEN_ROUTER_API_KEY, OPEN_ROUTER_API_KEY2..N (separate accounts the user
    set up for rotation) from the environment, then .env, then the PORTIA_EXTRA_ENV file. Never printed."""
    found, seen = [], set()

    def add(name, v):
        v = (v or "").strip().strip('"').strip("'")
        if v and v not in seen:
            seen.add(v)
            found.append((name, v))
    for name in sorted(os.environ):
        if re.fullmatch(r"OPEN_?ROUTER_API_KEY\d*", name):
            add(name, os.environ[name])
    for f in ENV_FILES:
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"\s*(?:export\s+)?(OPEN_?ROUTER_API_KEY\d*)\s*=\s*(.*)$", line)
                if m:
                    add(m.group(1), m.group(2))
    if not found:
        raise SystemExit("no OPEN_ROUTER_API_KEY* found (env, .env, the PORTIA_EXTRA_ENV file)")
    return found


def key_id(key: str) -> str:
    """How a key appears in logs and the ledger: a short hash, never the key or its account name."""
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def key_info(key: str) -> dict:
    import urllib.request
    try:
        return json.load(urllib.request.urlopen(urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}), timeout=30))["data"]
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


class CacheMiss(RuntimeError):
    """chat(cache_only=True) found no cached response: nothing was sent."""


class QuotaExhausted(RuntimeError):
    pass


class Client:
    """Rotates across every key: each request goes to the key with the most daily quota left (ties: the
    least recently used), each key throttled to its own 20 requests/minute. A key that hits its
    per-day limit is retired until the next UTC day; QuotaExhausted only when all are."""

    def __init__(self, model: str, daily_cap: int | None = None, min_interval_s: float = 3.2, log=print):
        self.model, self.min_interval, self.log = model, min_interval_s, log
        CACHE.mkdir(parents=True, exist_ok=True)
        self.keys = []
        for var, k in api_keys():
            info = key_info(k)
            cap = daily_cap or (50 if info.get("is_free_tier", True) else 1000)   # OpenRouter :free rule
            if var in RESERVE:               # the reserve account is used carefully: our own daily cap (default 600)
                cap = min(cap, int(os.environ.get("PORTIA_RESERVE_CAP", "600")))
            self.keys.append({"key": k, "id": key_id(k), "cap": cap, "last": 0.0, "reserve": var in RESERVE,
                              "free_tier": info.get("is_free_tier"), "ok": "error" not in info})
        self.keys = [k for k in self.keys if k["ok"]] or self.keys
        if os.environ.get("PORTIA_NO_RESERVE") == "1":          # keep the reserve account out of this process
            self.keys = [k for k in self.keys if not k["reserve"]]
        self._lock = threading.Lock()
        self.sent = self.cached = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}
        log(f"[openrouter] {len(self.keys)} key(s): " + ", ".join(f"{k['id']} ({'free' if k['free_tier'] else 'credits'}{', RESERVE' if k['reserve'] else ''}, "
            f"{self.used(k['id'])}/{k['cap']} today)" for k in self.keys))

    # -------------------------------------------------------------- ledger
    @staticmethod
    def _day() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _ledger(self) -> dict:
        for _ in range(5):                       # writes are atomic (os.replace); retry a racing read anyway
            try:
                return json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(f"unreadable ledger {LEDGER}; not overwriting it")

    def used(self, kid: str) -> int:
        day = self._ledger().get(self._day(), {})
        return int(day.get(kid, 0)) if isinstance(day, dict) else 0

    def _count(self, kid: str, to: int | None = None):
        with open(f"{LEDGER}.lock", "w") as lk:     # several runs (tools + static arm) share the ledger
            fcntl.flock(lk, fcntl.LOCK_EX)
            d = self._ledger()
            day = d.get(self._day())
            if not isinstance(day, dict):
                day = {}
            day[kid] = to if to is not None else int(day.get(kid, 0)) + 1
            d[self._day()] = day
            tmp = LEDGER.with_name(LEDGER.name + ".tmp")
            tmp.write_text(json.dumps(d, indent=1))
            os.replace(tmp, LEDGER)

    def used_today(self) -> int:
        return sum(self.used(k["id"]) for k in self.keys)

    def cap_today(self) -> int:
        return sum(k["cap"] for k in self.keys)

    def _pick(self) -> dict:
        live = [k for k in self.keys if self.used(k["id"]) < k["cap"]]
        # reserve keys (PORTIA_RESERVE_KEYS, default OPEN_ROUTER_API_KEY8, an account the user asked to use
        # carefully) are touched only once every other key is spent for the day
        live = [k for k in live if not k["reserve"]] or live
        if not live:
            raise QuotaExhausted(f"all {len(self.keys)} key(s) at their daily cap for {self._day()} UTC")
        return max(live, key=lambda k: (k["cap"] - self.used(k["id"]), -k["last"]))

    # -------------------------------------------------------------- streaming
    def _stream(self, body: dict, k: dict) -> dict:
        """POST with stream=true and assemble the SSE deltas into the non-streaming response shape.

        Needed for very long generations: the provider closes a NON-streamed request that sends nothing for
        too long ("Upstream idle timeout exceeded", 504) while the model is still reasoning."""
        r = requests.post(URL, json=body, stream=True, timeout=(30, 900),
                          headers={"Authorization": f"Bearer {k['key']}", "X-Title": "Portia tool-using video judge"})
        if r.status_code != 200:
            raise requests.RequestException(f"HTTP {r.status_code}: {r.text[:300]}")
        content, reasoning, finish, usage = [], [], None, {}
        for raw in r.iter_lines():
            # split BYTES (on \n / \r only), then decode: decode_unicode=True splits with str.splitlines, which
            # also cuts at U+2028 / U+0085, which JSON leaves unescaped inside the model's text (seen in testing)
            raw = raw.decode("utf-8")
            if not raw or not raw.startswith("data:"):
                continue                                   # SSE comments (": OPENROUTER PROCESSING") keep-alive
            data = raw[5:].strip()
            if data == "[DONE]":
                break
            ch = json.loads(data)
            if ch.get("error"):
                raise requests.RequestException(str(ch["error"])[:300])
            for c in ch.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("content"):
                    content.append(d["content"])
                if d.get("reasoning"):
                    reasoning.append(d["reasoning"])
                finish = c.get("finish_reason") or finish
            usage = ch.get("usage") or usage
        for u in self.usage:
            self.usage[u] += int((usage or {}).get(u) or 0)
        return {"choices": [{"message": {"role": "assistant", "content": "".join(content),
                                         "reasoning": "".join(reasoning)}, "finish_reason": finish}],
                "usage": usage, "streamed": True}

    # -------------------------------------------------------------- call
    def chat(self, messages: list, tools: list | None = None, tool_choice=None, cache_only: bool = False,
             **params) -> dict:
        body = {"model": self.model, "messages": messages, **params}
        if tools:
            body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        ck = hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        p = CACHE / f"{ck}.json"
        if p.exists():
            self.cached += 1
            return json.loads(p.read_text(encoding="utf-8"))
        if cache_only:                                  # strict replay: a miss means the trajectory diverged
            raise CacheMiss(f"no cached response {ck[:12]}; the replayed request differs from the original run")
        last_err = None
        for attempt in range(8):
            with self._lock:
                k = self._pick()
                wait = self.min_interval - (time.time() - k["last"])
                if wait > 0:
                    time.sleep(wait)
                k["last"] = time.time()
                self._count(k["id"])                   # every request the provider receives counts
            t = time.time()
            try:
                if body.get("stream"):
                    j = self._stream(body, k)          # long generations: SSE keeps the connection alive
                    j["_latency_s"], j["_key_id"] = round(time.time() - t, 2), k["id"]
                    self.sent += 1
                    if (j["choices"][0].get("finish_reason")) != "error":
                        p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
                    return j
                r = requests.post(URL, json=body, timeout=300,
                                  headers={"Authorization": f"Bearer {k['key']}", "X-Title": "Portia tool-using video judge"})
            except requests.RequestException as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                j = r.json()
                if j.get("error"):
                    last_err = f"[{k['id']}] {str(j['error'])[:400]}"
                    time.sleep(5 * (attempt + 1))
                    continue
                j["_latency_s"] = round(time.time() - t, 2)
                j["_key_id"] = k["id"]
                for u in self.usage:
                    self.usage[u] += int((j.get("usage") or {}).get(u) or 0)
                self.sent += 1
                # a provider-side failure (HTTP 200 but finish_reason "error") is transient, not an answer:
                # never cache it, or every retry would replay the same failure from disk
                if ((j.get("choices") or [{}])[0].get("finish_reason")) != "error":
                    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
                return j
            last_err = f"[{k['id']}] HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code == 429:
                if "per-day" in r.text.lower() or "free-models-per-day" in r.text.lower():
                    with self._lock:
                        self._count(k["id"], to=k["cap"])     # retire this key for today, try another
                    self.log(f"[openrouter] key {k['id']} hit its daily limit; rotating")
                    continue
                time.sleep(min(float(r.headers.get("Retry-After") or 0) or 15 * (attempt + 1), 120))
                continue
            if r.status_code in (400, 401, 403, 404):
                break
            if r.status_code == 402:                          # this account cannot pay for the call
                with self._lock:
                    self._count(k["id"], to=k["cap"])
                continue
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"OpenRouter call failed: {last_err}")


if __name__ == "__main__":                          # python -m judge.openrouter -> per-key status (ids only)
    c = Client("x")
    print(f"total today: {c.used_today()}/{c.cap_today()} request(s) across {len(c.keys)} key(s)")
