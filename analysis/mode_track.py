#!/usr/bin/env python3
"""portia/analysis/mode_track.py: Portia's track record for one investigator setting (plan 009 E4/E6 speed modes).

    python analysis/mode_track.py                    # every setting with a finished Glimmer adjudication
    python analysis/mode_track.py m6med              # one setting

For each setting (an investigator run prefix and its Glimmer evidence-only adjudications over triples of seeds), pooled
over development shards 3-4 and over its finished triples:
  * single: the mean accuracy of one investigator (every seed of the triples);
  * unanimous: right when all three investigators agree; split: the share of contests where they do not;
  * vote / glimmer on splits: right by the majority / by the Glimmer adjudicator on those splits;
  * jury: the whole pipeline's accuracy (unanimous verdict, else the adjudicator's);
  * cost: mean output tokens and turns of one investigator per contest.
These are the numbers behind product/engine.py's TRACK (8 turns, high) and TRACK_QUICK.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# setting -> (label, investigator prefix, [(seeds of a triple, [its Glimmer adjudication samples])]); the default's
# five triples and their samples are the ones Portia's Proof page pools (product/engine.py PROOF_TRIPLES)
SETTINGS = {
    "8t":    ("8 turns, high (default)", "mg_v4t", [
        ((0, 1, 2), ["mg_adjev", "mg_adjev_r1", "mg_adjev_r2", "mg_adjev_r3", "mg_adjev_r4"]),
        ((2, 3, 4), ["mg_adjev_t234", "mg_adjev_t234_r1", "mg_adjev_t234_r2"]),
        ((3, 4, 5), ["mg_adjev_t345", "mg_adjev_t345_r1", "mg_adjev_t345_r2"]),
        ((5, 6, 7), ["mg_adjev_t567", "mg_adjev_t567_r1", "mg_adjev_t567_r2"]),
        ((8, 9, 10), ["mg_adjev_t8910", "mg_adjev_t8910_r1", "mg_adjev_t8910_r2"])]),
    # second samples (--seed-salt 1, runs/adj_samples_lane.sh) count once they finish
    "med":   ("8 turns, medium", "mg_v4tmed", [((0, 1, 2), ["mg_adjev_med", "mg_adjev_med_r1"]),
                                               ((3, 4, 5), ["mg_adjev_medb", "mg_adjev_medb_r1"])]),
    "m6":    ("6 turns, high", "mg_v4t_m6", [((0, 1, 2), ["mg_adjev_m6", "mg_adjev_m6_r1"])]),
    "m6med": ("6 turns, medium", "mg_v4t_m6med", [((0, 1, 2), ["mg_adjev_m6med", "mg_adjev_m6med_r1"]),
                                                  ((3, 4, 5), ["mg_adjev_m6medb", "mg_adjev_m6medb_r1"]),
                                                  ((6, 7, 8), ["mg_adjev_m6medc", "mg_adjev_m6medc_r1"])]),
    "m4":    ("4 turns, high (Quick now)", "mg_v4t_m4", [((0, 1, 2), ["mg_adjev_m4", "mg_adjev_m4_r1"]),
                                                         ((3, 4, 5), ["mg_adjev_m4b", "mg_adjev_m4b_r1"])]),
}


def rows(run: str) -> list[dict]:
    p = ROOT / "runs" / run / "results.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def done(run: str) -> bool:
    return (ROOT / "runs" / run / "summary.json").exists()


def track(key: str) -> dict | None:
    label, pre, triples = SETTINGS[key]
    adj, used, seeds_used = [], [], set()            # adj: (weight, row); a triple's k samples weigh 1/k each
    for seeds, samples in triples:
        samples = [a for a in samples if all(done(f"{a}_{s}") for s in ("s3", "s4"))]
        if not samples:
            continue
        used.append(f"{{{','.join(map(str, seeds))}}}" + (f" x{len(samples)}" if len(samples) > 1 else ""))
        seeds_used |= set(seeds)
        for a in samples:
            adj += [(1 / len(samples), r) for s in ("s3", "s4") for r in rows(f"{a}_{s}")]
    if not adj:
        return None
    single, toks, steps = [], [], []
    for seed in sorted(seeds_used):
        for s in ("s3", "s4"):
            for x in rows(f"{pre}{'' if seed == 0 else f'_r{seed}'}_{s}"):
                single.append(x.get("verdict") == x["good_side"])
                toks.append((x.get("usage") or {}).get("completion_tokens") or 0)
                steps.append(x.get("steps") or 0)

    def pct(pairs):                                   # weighted share of True
        w = sum(wt for wt, _ in pairs)
        return round(100 * sum(wt for wt, ok in pairs if ok) / w, 1) if w else None

    split = [(w, a) for w, a in adj if a.get("contested")]
    agree = [(w, a) for w, a in adj if not a.get("contested")]
    right = lambda a: a["verdict"] == a["good_side"]                                                  # noqa: E731
    return {"setting": label, "triples": used, "single": round(100 * st.mean(single), 1) if single else None,
            "unanimous": pct([(w, right(a)) for w, a in agree]),
            "split_share": pct([(w, bool(a.get("contested"))) for w, a in adj]),
            "vote_on_splits": pct([(w, bool(a.get("vote_correct"))) for w, a in split]),
            "glimmer_on_splits": pct([(w, right(a)) for w, a in split]),
            "vote": pct([(w, bool(a.get("vote_correct"))) for w, a in adj]),
            "jury": pct([(w, right(a)) for w, a in adj]),
            "out_tokens": round(st.mean(toks)) if toks else None, "turns": round(st.mean(steps), 2) if steps else None}


def main():
    keys = sys.argv[1:] or list(SETTINGS)
    out = ["| Setting | Triples | Single | Vote | Jury | Unanimous right | Split share | Vote on splits | Glimmer on splits | Output tokens / turns |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for k in keys:
        t = track(k)
        if t:
            out.append(f"| {t['setting']} | {' '.join(t['triples'])} | {t['single']} | {t['vote']} | **{t['jury']}** | {t['unanimous']} | "
                       f"{t['split_share']}% | {t['vote_on_splits']} | {t['glimmer_on_splits']} | {t['out_tokens']} / {t['turns']} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
