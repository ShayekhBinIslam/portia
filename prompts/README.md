# Portia: prompts and tools

Everything the judge model reads comes from files in `prompts/` and `tools/`. The code only fills in variables
(`judge/prompting.py` loads the files). Tool *outputs* (search results, zoom captions and so on) are formatted by
the tool code in `judge/tools.py`, not here.

## Layout

```
prompts/
  system.md            system prompt for toolset v1
  system_v2.md         toolset v2
  system_v3.md         toolsets v3 and v4 (the tuned Muse agent)
  system_v4look.md     toolsets v3 and v4 with --look-first
  system_v5.md         toolset v5
  agent/*.j2           every message the agent loop writes (Jinja2 templates)
  inspect/             the independent look (--inspect): Jinja2 prompts + JSON schemas
  oracle.j2            analysis/oracle_evidence.py (judge given the ground-truth frames)
tools/
  <tool>.yaml          one tool each: name, description, parameters (exactly what the model reads)
  toolsets.yaml        which tools each toolset offers, in order, plus description variants
```

## What a run uses

| toolset | option | system prompt | tools (tools/toolsets.yaml) |
|---|---|---|---|
| v1 | | system.md | v1 |
| v2 | | system_v2.md | v2 |
| v3, v4 | | system_v3.md | v2 |
| v3, v4 | `--look-first` | system_v4look.md | v2 |
| v5 | | system_v5.md | v5 (zoom uses the `v5` description) |
| v1 to v4 | `--zoom-side` other than 1024 | (unchanged) | zoom uses the `hires` description |
| any | `--inspect` (local server) | + inspect/note.j2 | (unchanged) |

To see the exact system prompt and tool list for a combination of options:

```
python -m judge.prompting --toolset v4 --look-first
python -m judge.prompting --toolset v5 --inspect
```

## Agent messages (`prompts/agent/`)

| file | when it is sent | variables |
|---|---|---|
| first_message.j2 | first user message | question, answer_a, answer_b, diff (v2+, else none), n_playlists, grounded (v4, v5), init, max_steps, parallel (v2+) |
| overview.j2 | v3+: the first message plus the overview of the 64 best segments | first, grounded, transcripts, n_sheets |
| turn_note.j2 | after each tool turn (`--budget-note`, `--look-first`) | budget_note, look_first, left, n_text, n_look, text_streak |
| images_message.j2 | the images the tools returned, as one user message | v2, labels, note |
| budget_final.j2 | the forced final turn | |
| budget_extend.j2 | `--extend`: more turns granted at the limit | max_steps, extend |
| nudge_use_tool.j2 | the model replied with text but no verdict | |
| answer_result.j2 | the tool result of `answer` | recorded |
| image_dropped.j2 | stands in for an older image dropped from the context | |
| fallback_answer_only.j2 | verdict fallback 1: `answer` is the only tool | |
| fallback_tool_closed.j2 | verdict fallback 2: the result of calls made after the tools closed | |
| fallback_choice.j2 | verdict fallback 2: the constrained A/B choice | |

## Independent look (`prompts/inspect/`, `--inspect`)

| file | role | variables |
|---|---|---|
| questions.j2 | once per contest: neutral questions from the answer diff | question, diff |
| questions.schema.json | the JSON shape asked for (the reply may also be a plain list) | |
| system.j2 | system prompt of each inspect call (it sees only the image) | |
| ask.j2 | the inspect call's text after the image | questions |
| answers.schema.json | the JSON shape of its answers | |
| result.j2 | appended to the result of every tool that returns images (zoom, burst, view_frames, contact_sheet) | lines |
| note.j2 | appended to the agent's system prompt when inspect runs | |

## Changing a prompt or a tool

1. Prefer adding a new file or variant over editing one that a finished run used (as `system_v4look.md` was added
   next to `system_v3.md`). Old runs then still replay from the response cache, and comparisons stay clean.
2. `python tests/golden_requests.py --check tests/golden_requests.json` shows whether any request changed. It drives
   the real agent loop with a scripted model for 12 option combinations on 20 contests (1,840 requests). After a
   deliberate change, record a new snapshot with `--write`.
