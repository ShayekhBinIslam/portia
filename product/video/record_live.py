"""The "How Portia works" chapter (S04_How) as footage: a NEW question run live, sped up to fit its narration (plan
018 revision). Library cases replay from the response cache, so the run is a question no cache holds, asked on
the live app (port 5250) like any user would: the New case form, "Convene the jury", Muse Spark 1.3 checking the verdict.

    python record_live.py record [--url http://127.0.0.1:5250/]
    python record_live.py cut

record: fills the form off-camera, flashes the sync frame, clicks "Convene the jury" on the word "sends", then follows
the run in real time (the investigators' turns, the vote, the adjudicator, the verdict), logging when each first shows
on screen (build/footage/raw/S04_How/log.json). cut: maps the narration onto the recording with anchors (the click on
"sends", the board on "Glimmer", the first turn on "investigate", the Spark 1.3 card on "Spark", the verdict on "rules"); each stretch plays at the
constant speed that lands it on its word, labelled with that speed, and the beats are mixed in. Writes
build/footage/S04_How.mp4 and build/cues/S04_How.json, like record_narrated.py's chapters.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from record_narrated import AUDIO, CSS, CUES, FOOT, GAP, RAW, TIMING, Take, flash_time, word_time  # noqa: E402

NAME = "S04_How"
LOG = RAW / NAME / "log.json"
PUBLIC = HERE.parent / "public.env"              # the live app's access code (never printed)
FONT = Path.home() / ".fonts" / "portia" / "Inter.ttf"
DOMAIN = "Documentary"
QUESTION = "Which number is painted on the island of the museum aircraft carrier that is moored by a long bridge?"   # new wording: no cached responses, a real live run
ANSWER_A = "The number 16 is painted on the carrier's island."
ANSWER_B = "The number 18 is painted on the carrier's island."
GAP2, TAIL = 0.5, 1.4

STATE = """() => {
  const v = document.querySelector('#verdict');
  return { hash: location.hash, agents: document.querySelectorAll('#board .agent').length,
    turns: [...document.querySelectorAll('#board .turn')].filter((t) => !t.querySelector('.skeleton')).length,
    calls: document.querySelectorAll('#board .call[data-name]').length,
    vote: !!document.querySelector('#vote .vote'), adj: !!document.querySelector('#adj .agent'),
    adjTurns: [...document.querySelectorAll('#tu-adj .turn')].filter((t) => !t.querySelector('.skeleton')).length,
    final: !!(v && v.textContent.trim()), err: !!document.querySelector('#banners .err') };
}"""
FOLLOW = """(where) => {             // keep the newest thing in view, moving as little as possible
  const last = (sel) => [...document.querySelectorAll(sel)].map((t) => t.lastElementChild).filter(Boolean);
  let el = null;
  if (where === 'board') el = last('#board .turns').sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0];
  if (where === 'adj') el = last('#tu-adj')[0] || document.querySelector('#adj');
  if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}"""


def access_code() -> str:
    if not PUBLIC.exists():
        return ""
    for line in PUBLIC.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("PORTIA_ACCESS_CODE="):
            return line.split("=", 1)[1].strip()
    return ""


def narration():
    """Scene times (seconds from the chapter's start) of the beats and the anchor words."""
    d1, d2 = TIMING["s04_1"]["duration"], TIMING["s04_2"]["duration"]
    t1 = GAP
    t2 = t1 + d1 + GAP2
    return {"t1": t1, "t2": t2, "sends": t1 + word_time("s04_1", "sends"), "glimmer": t1 + word_time("s04_1", "Glimmer"),
            "investigate": t1 + word_time("s04_1", "investigate"),
            "spark": t2 + word_time("s04_2", "Spark"), "rules": t2 + word_time("s04_2", "rules"), "end": t2 + d2 + TAIL}


def record(url: str):
    code, n = access_code(), narration()
    with sync_playwright() as p:
        b = p.chromium.launch()
        t = Take(b, url, NAME)
        # 1.25, not the other chapters' 1.5: the whole form (question to button) and the three-agent board fit the frame
        t.ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { document.documentElement.style.zoom = '1.25'; });")
        if code:
            t.ctx.add_init_script(f"try {{ localStorage.setItem('portia-code', {json.dumps(code)}); }} catch (e) {{}}")
        t.goto("#/new", "#nq")
        t.pg.select_option("#dom", DOMAIN)
        t.pg.click("#nmode button[data-m=two]")
        t.pg.fill("#nq", QUESTION)
        t.pg.fill("#na", ANSWER_A)
        t.pg.fill("#nb", ANSWER_B)
        t.pg.click('#opts button[data-v="spark13all"]')
        t.pg.click('#opts .seg[data-k="agents"] button[data-v="3"]')
        t.pg.click('#opts .seg[data-k="quick"] button[data-v="0"]')
        t.scroll("label[for=nq]", 130, 10)              # after the clicks above, which scroll the page
        t.pg.wait_for_timeout(500)
        go = t.pg.query_selector("#go").bounding_box()
        t.pg.mouse.move(go["x"] + go["width"] + 260, go["y"] + go["height"] * 0.6)
        t.mouse = (go["x"] + go["width"] + 260, go["y"] + go["height"] * 0.6)
        t.pg.wait_for_timeout(700)
        t.begin()
        t.until(t.start + n["sends"] - 0.5)
        t.click("#go", 450)
        log = {"flash": t.flash, "start": t.start, "click": t.clock(), "events": []}
        t.pg.wait_for_function("location.hash.startsWith('#/job/')", timeout=30000)
        log["job"] = t.pg.evaluate("location.hash").split("/")[2].split("?")[0]
        t.pg.add_style_tag(content=CSS)
        t.glide(1890, 1060, 600)                          # the pointer steps out of the way
        seen, last_follow, final_at = {}, 0.0, None
        while t.clock() - log["click"] < 1500:
            s, now = t.pg.evaluate(STATE), t.clock()
            for key, hit in (("board", s["agents"] >= 3), ("turn", s["turns"] > 0), ("vote", s["vote"]), ("adj", s["adj"]),
                             ("adj_turn", s["adjTurns"] > 0), ("final", s["final"]), ("error", s["err"])):
                if hit and key not in seen:
                    seen[key] = now
                    log["events"].append({"t": round(now, 3), "kind": key, "turns": s["turns"], "calls": s["calls"]})
                    print(f"{now - log['click']:7.1f}s {key} (turns {s['turns']}, calls {s['calls']})", flush=True)
                    if key == "board":
                        t.scroll("#board", 120, 900)
                    if key == "vote":
                        t.scroll("#vote", 260, 900)
                    if key == "adj":
                        t.scroll("#adj", 110, 900)
                    if key == "final":
                        final_at = now
                        t.scroll("#verdict", 110, 900)
            if s["err"]:
                print("the run reported an error; stopping", flush=True)
                break
            if final_at is None and now - last_follow > 2.0 and "board" in seen:
                t.pg.evaluate(FOLLOW, "adj" if s["adj"] else "board")
                last_follow = now
            if final_at is not None and now - final_at > 4.0:
                break
            t.pg.wait_for_timeout(250)
        log["end"] = t.clock()
        log["video"] = t.pg.video.path()
        t.ctx.close()
        b.close()
    LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"recorded job {log['job']}: {log['end'] - log['click']:.0f} s after the click -> {LOG}")


def label_file(text: str) -> str:
    d = FOOT / "labels"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"label_{abs(hash(text)) % 10**8}.txt"
    f.write_text(text, encoding="utf-8")
    return str(f)


def cut():
    log, n = json.loads(LOG.read_text(encoding="utf-8")), narration()
    ev = {e["kind"]: e["t"] for e in log["events"]}
    for k in ("board", "adj", "final"):
        if k not in ev:
            raise SystemExit(f"the recording never showed '{k}'; record again")
    raw = Path(log["video"])
    shift = flash_time(raw) - log["flash"]                  # video time = clock + shift
    c0 = log["click"] - n["sends"]
    anchors = [(0.0, c0), (n["sends"], log["click"]), (n["glimmer"], ev["board"])]
    if "turn" in ev:                                        # the wait for the first turns goes fast; the turns slower
        anchors.append((n["investigate"], ev["turn"]))
    anchors += [(n["spark"], ev["adj"]), (n["rules"], ev["final"]), (n["end"], ev["final"] + (n["end"] - n["rules"]))]
    chains, labels, segs = [], [], []
    for k, ((ta, ca), (tb, cb)) in enumerate(zip(anchors, anchors[1:])):
        dt, dc = tb - ta, cb - ca
        v0, v1 = ca + shift, cb + shift
        if dc >= dt:                                        # sped up: a constant speed lands cb on tb
            speed = dc / dt
            chains.append(f"[s{k}]trim=start={v0:.3f}:end={v1:.3f},setpts=(PTS-STARTPTS)/{speed:.5f},fps=50,"
                          f"trim=duration={dt:.3f}[p{k}]")
        else:                                               # faster than the words: real time, then hold the frame
            speed = 1.0
            chains.append(f"[s{k}]trim=start={v0:.3f}:end={v1:.3f},setpts=PTS-STARTPTS,fps=50,"
                          f"tpad=stop_mode=clone:stop_duration={dt - dc + 0.1:.3f},trim=duration={dt:.3f}[p{k}]")
        segs.append((ta, tb, speed))
        labels.append(f"[p{k}]")
    nseg = len(labels)
    graph = f"[0:v]split={nseg}" + "".join(f"[s{k}]" for k in range(nseg)) + ";" + ";".join(chains) + ";"
    graph += "".join(labels) + f"concat=n={nseg}:v=1:a=0,scale=1920:1080,setsar=1"
    for ta, tb, speed in segs:                              # an honest speed label on every sped-up stretch
        if speed >= 1.5:
            txt = label_file(f"Live run  ·  {speed:.0f}× speed")
            graph += (f",drawtext=fontfile={FONT}:textfile={txt}:fontsize=30:fontcolor=white:box=1:boxcolor=0x16171B@0.82:"
                      f"boxborderw=16:x=w-tw-56:y=150:enable='between(t,{ta:.3f},{tb:.3f})'")
    graph += "[v]"
    dur = n["end"]
    ins = ["-i", str(raw)]
    amix = []
    for k, (bid, t0) in enumerate((("s04_1", n["t1"]), ("s04_2", n["t2"])), 1):
        ins += ["-i", str(AUDIO / TIMING[bid]["file"])]
        ms = int(round(t0 * 1000))
        amix.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{k}]")
    graph += ";" + ";".join(amix) + f";[a1][a2]amix=inputs=2:normalize=0:duration=longest,apad,atrim=0:{dur:.3f}[a]"
    FOOT.mkdir(parents=True, exist_ok=True)
    out = FOOT / f"{NAME}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                    "-t", f"{dur:.3f}", str(out)], check=True)
    CUES.mkdir(parents=True, exist_ok=True)
    (CUES / f"{NAME}.json").write_text(json.dumps({
        "scene": NAME, "duration": round(dur, 3), "misses": [], "late": [], "job": log["job"],
        "speeds": [{"from": round(a, 2), "to": round(b, 2), "speed": round(s, 1)} for a, b, s in segs],
        "cues": [{"beat": "s04_1", "start": round(n["t1"], 3), "duration": TIMING["s04_1"]["duration"]},
                 {"beat": "s04_2", "start": round(n["t2"], 3), "duration": TIMING["s04_2"]["duration"]}]}, indent=1),
        encoding="utf-8")
    print(f"{NAME}: {dur:.1f} s from job {log['job']}; speeds " + ", ".join(f"{s:.1f}x" for _, _, s in segs) + f" -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record", "cut"])
    ap.add_argument("--url", default="http://127.0.0.1:5250/")
    a = ap.parse_args()
    record(a.url) if a.cmd == "record" else cut()


if __name__ == "__main__":
    main()
