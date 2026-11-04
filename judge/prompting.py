"""portia/judge/prompting.py: the judge's prompts and tool definitions live in files, not in code.

    prompts/system*.md            system prompts (which one a run uses: prompts/README.md)
    prompts/agent/*.j2            every message the agent loop writes (Jinja2 templates)
    prompts/inspect/*             the independent look: its prompts (Jinja2) and JSON schemas
    prompts/oracle.j2             analysis/oracle_evidence.py
    tools/<name>.yaml             one tool definition each (name, description, parameters)
    tools/toolsets.yaml           which tools each toolset offers, in order, plus description variants

Templates render with StrictUndefined (a missing variable is an error) and no autoescaping; Jinja drops the one
trailing newline of each file. tests/golden_requests.py checks that the requests built from these files are
byte-identical to the ones the code used to build.

    python -m judge.prompting --toolset v4 [--zoom-side 1792] [--look-first] [--inspect]
        prints the system prompt and the tool list a run with those options sends
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"
TOOLS_DIR = ROOT / "tools"
ENV = Environment(loader=FileSystemLoader(str(PROMPTS)), undefined=StrictUndefined, autoescape=False,
                  keep_trailing_newline=False)


def render(name: str, **variables) -> str:
    """A template under prompts/, e.g. render("agent/budget_final.j2")."""
    return ENV.get_template(name).render(**variables)


@lru_cache(maxsize=None)
def system(name: str) -> str:
    """A system prompt file under prompts/, verbatim."""
    return (PROMPTS / name).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def schema(name: str) -> dict:
    """A JSON schema under prompts/inspect/."""
    return json.loads((PROMPTS / "inspect" / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _toolsets() -> dict:
    return yaml.safe_load((TOOLS_DIR / "toolsets.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _tool(name: str) -> str:
    fn = yaml.safe_load((TOOLS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return json.dumps(fn, ensure_ascii=False)          # cached as text: callers always get a fresh copy


def tool(name: str, variant: str | None = None) -> dict:
    """One tool in OpenAI function form; `variant` swaps in an alternative description from tools/toolsets.yaml."""
    fn = json.loads(_tool(name))
    if variant:
        fn = {**fn, "description": _toolsets()["variants"][name][variant]}
    return {"type": "function", "function": fn}


def toolset(name: str, variants: dict | None = None) -> list:
    """The tool list of toolset v1, v2 or v5, in order; variants maps tool name -> description variant."""
    variants = variants or {}
    return [tool(n, variants.get(n)) for n in _toolsets()["toolsets"][name]]


def main():
    from judge.agent import judge_setup                 # late import: agent imports this module
    ap = argparse.ArgumentParser(description="print the system prompt and tool list a run sends")
    ap.add_argument("--toolset", default="v4", choices=["v1", "v2", "v3", "v4", "v5"])
    ap.add_argument("--zoom-side", type=int, default=1024)
    ap.add_argument("--look-first", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()
    system_prompt, tools = judge_setup(a.toolset, zoom_side=a.zoom_side, look_first=a.look_first, inspect=a.inspect)
    print("=" * 30, "SYSTEM PROMPT", "=" * 30)
    print(system_prompt)
    print("=" * 30, f"TOOLS ({len(tools)})", "=" * 30)
    print(yaml.safe_dump([t["function"] for t in tools], sort_keys=False, allow_unicode=True, width=110))


if __name__ == "__main__":
    main()
