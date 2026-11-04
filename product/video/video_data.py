"""The numbers and pictures the demo video's cards show, read from Portia's own files (nothing typed in by hand).

    python video_data.py      # -> build/data.json, build/assets/*

  proof        product/site/data/proof.json (check_all, trust tiers): what the Proof page shows
  unanimous    runs/plan014_report.md, the "All" row of analysis/spark13_unanimous_report.py
  footage      product/site/data/footage/<domain>.json: the demo case's searchable collection
  case 038     its answers' sentences, the verdict's cited moments as native-resolution frames, the job's numbers
  logo         product/brand/svg (Qwen-Image-2512 wordmark and monogram, traced): build/assets/wordmark.svg, monogram.svg
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
ROOT = PRODUCT.parent
sys.path.insert(0, str(ROOT))
BUILD = HERE / "build"
ASSETS = BUILD / "assets"
JOB, CASE = "1102-120834-5a94", "shard3_15pct_038"          # the demo case: three agents read the wrong notebook page
CITED = [("ARcH3epJjF4", 1255, "cubes"), ("ARcH3epJjF4", 1265, "flowcharts")]    # the verdict's two moments
PHRASES = ("sketches of human ears", "isometric sketches of cubes")


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    site = PRODUCT / "site" / "data"
    proof = json.loads((site / "proof.json").read_text(encoding="utf-8"))
    ca = proof["check_all"]
    modes = proof["trust"]["modes"]["spark13all"]
    levels = proof["trust"]["levels"]
    tiers = {"accept": [], "spot": [], "review": []}
    for p in modes["paths"]:
        lvl = "accept" if p["pct"] >= levels["accept"] else "spot" if p["pct"] >= levels["spot"] else "review"
        tiers[lvl].append(p)
    tier = {k: {"share": round(sum(p["share"] for p in v), 1), "pct_lo": min(p["pct"] for p in v),
                "pct_hi": max(p["pct"] for p in v)} for k, v in tiers.items()}
    rep = (ROOT / "runs" / "plan014_report.md").read_text(encoding="utf-8")
    m = re.search(r"\| \*\*All\*\* \| \| (\d+) \((\d+)\) \| (\d+) / (\d+)", rep)
    unanimous, unanimous_wrong, fixed, broken = map(int, m.groups())
    case = json.loads((site / "case" / f"{CASE}.json").read_text(encoding="utf-8"))
    foot = json.loads((site / "footage" / f"{case['domain']}.json").read_text(encoding="utf-8"))
    pat = "|".join(re.escape(x) for x in PHRASES)
    sent = {k: re.search(rf"[^.]*({pat})[^.]*\.", case[k]).group(0).strip() for k in ("answer_a", "answer_b")}
    final = next(json.loads(l) for l in (PRODUCT / "jobs" / JOB / "events.jsonl").open(encoding="utf-8")
                 if '"type": "final"' in l)
    data = {"runs": ca["n"], "vote": ca["vote"], "check_all": ca["pct"], "usd_per_case": ca["usd_per_case"],
            "unanimous": unanimous, "unanimous_wrong": unanimous_wrong, "fixed": fixed, "broken": broken,
            "tier": tier, "hours": foot["hours"], "videos": len(foot["videos"]), "domain": foot["domain"],
            "case": {"id": CASE, "job": JOB, "question": case["question"], "a": sent["answer_a"], "b": sent["answer_b"],
                     "phrases": PHRASES,
                     "disputed": case["disputed"][0], "verdicts": final["verdicts"], "verdict": final["verdict"],
                     "how": final["how"], "track": final["track"]["pct"]},
            "cited": [{"vid": v, "t": t, "file": f"assets/{name}.jpg"} for v, t, name in CITED]}
    (BUILD / "data.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    from judge import corpus
    for vid, t, name in CITED:
        corpus.segment(f"{vid}@{t // 30 * 30}")                     # registers the video's playlist
        im, at = corpus.frame_at(vid, t)
        im.convert("RGB").save(ASSETS / f"{name}.jpg", quality=92)
        print(f"frame {vid} @ {at:.1f}s -> {name}.jpg {im.size}")
    svg = re.search(r'<a class="logo".*?(<svg.*?</svg>)', (PRODUCT / "static" / "index.html").read_text(encoding="utf-8"), re.S).group(1)
    svg = svg.replace('style="fill:var(--brand)"', 'fill="#5B47D6"').replace('aria-hidden="true"', 'xmlns="http://www.w3.org/2000/svg"')
    (ASSETS / "logo.svg").write_text(svg, encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "case"}, indent=1))


if __name__ == "__main__":
    main()
