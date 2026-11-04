"""Screen footage for the narrated demo's footage chapters, driven by the narration (plan 018).

    python record_narrated.py [--url http://127.0.0.1:5260/] [--only S05_Catch,...]

For each footage scene of script.py: the page is prepared off-camera, then the scene's beats play in real time. Each
beat lasts its clip (audio/timing.json) plus a gap, and every action (a scroll, a click, an overlay) waits for the
spoken word that names it (audio/words.json). A magenta flash before the first beat syncs the browser's recording to
the clock. The recording is cut into build/footage/<Scene>.mp4 (1920x1080, 30 fps) with the beats mixed in at their
marks, and build/cues/<Scene>.json gets the cue log slide_base.py writes for manim scenes, so portia_build.py captions
and joins both kinds alike. The page is the static gallery (no GPU): python build_static.py, served on port 5260.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import AUDIO, BUILD, script  # noqa: E402

S = script()
TIMING = json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))
WORDS = json.loads((AUDIO / "words.json").read_text(encoding="utf-8")) if (AUDIO / "words.json").exists() else {}
FOOT, RAW, CUES = BUILD / "footage", BUILD / "footage" / "raw", BUILD / "cues"
JOB = "1102-120834-5a94"             # case 038, Spark 1.3 checking every verdict: three agents said "ears"; it is cubes
BATCH = "b1102-000400-9e31"          # a finished batch audit, Spark 1.3 checking every verdict
NEW_JOB = "1030-064048-0741"         # a new question over the Documentary collection, run live
CASE = "shard3_15pct_038"            # case 038 itself (the Problem chapter shows its two answers)
GAP, LEAD = 0.4, 0.15
MAGENTA = (255, 0, 255)

CSS = """
.demo-ov { position: fixed; z-index: 9999; left: 50%; transform: translate(-50%, 14px); opacity: 0; transition: opacity .35s, transform .35s;
  background: var(--surface); border: 1px solid var(--line-2); border-radius: 16px; box-shadow: var(--shadow-lg); padding: 14px 22px;
  font: 600 19px/1.4 var(--sans); color: var(--ink); display: flex; align-items: center; gap: 14px; white-space: nowrap; }
.demo-ov.on { opacity: 1; transform: translate(-50%, 0); }
.demo-ov.top { top: 84px; } .demo-ov.bottom { bottom: 40px; }
.demo-ov .sq { width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; color: #fff; font: 700 15px var(--sans); }
.demo-ov .bad { color: var(--bad); } .demo-ov .ok { color: var(--ok); } .demo-ov .muted { color: var(--muted); font-weight: 500; }
.demo-hl { outline: 3px solid var(--brand) !important; outline-offset: 4px; border-radius: 10px; transition: outline-color .3s; }
#demo-flash { position: fixed; inset: 0; z-index: 10000; background: rgb(255, 0, 255); }
.demo-ov .grp { display: inline-flex; gap: 4px; padding: 6px; border: 2px solid var(--line-2); border-radius: 10px; }
.demo-ov .grp .sq { width: 16px; height: 16px; border-radius: 4px; }
.demo-ov .grp.badg { border-color: var(--bad); background: rgba(209, 53, 43, .10); }
"""

# Headless Chromium records no cursor, so the page draws one: a macOS-style arrow (dark fill, white outline, soft
# shadow) that follows the real mouse events Playwright sends, presses on mousedown and leaves a violet ripple.
POINTER = """
(() => {
  const css = `#demo-ptr { position: fixed; left: 0; top: 0; z-index: 10001; pointer-events: none; width: 24px; height: 24px;
      transform: translate(-100px, -100px); filter: drop-shadow(0 2px 3px rgba(0,0,0,.35)); }
    #demo-ptr svg { width: 24px; height: 24px; transform-origin: 5px 3px; transition: transform .09s ease-out; }
    #demo-ptr.down svg { transform: scale(.86); }
    .demo-ripple { position: fixed; z-index: 10000; pointer-events: none; width: 10px; height: 10px; margin: -5px 0 0 -5px;
      border-radius: 50%; border: 3px solid #5b47d6; background: rgba(91, 71, 214, .14); animation: demo-rip .55s ease-out forwards; }
    @keyframes demo-rip { from { transform: scale(.4); opacity: 1; } to { transform: scale(5.2); opacity: 0; } }`;
  const add = () => {
    if (document.getElementById('demo-ptr')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const p = document.createElement('div'); p.id = 'demo-ptr';
    p.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 3 L5 19.6 L9.1 15.9 L11.9 22 L14.9 20.7 L12.2 14.7 L17.6 14.7 Z" fill="#16171b" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    document.body.appendChild(p);
    // mouse positions come in viewport pixels; the page is drawn at CSS zoom 1.5, which scales fixed positions too
    const z = () => parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
    const at = (e) => { p.style.transform = `translate(${e.clientX / z() - 5}px, ${e.clientY / z() - 3}px)`; };
    addEventListener('mousemove', at, true);
    addEventListener('mousedown', (e) => { at(e); p.classList.add('down');
      const r = document.createElement('div'); r.className = 'demo-ripple'; r.style.left = `${e.clientX / z()}px`; r.style.top = `${e.clientY / z()}px`;
      document.body.appendChild(r); setTimeout(() => r.remove(), 700); }, true);
    addEventListener('mouseup', () => p.classList.remove('down'), true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
"""


def word_time(bid: str, word: str, nth: int = 1) -> float:
    """When a word of a beat is spoken (aligned words; else its share of the spoken characters), as slide_base does."""
    key = "".join(c for c in word.lower() if c.isalnum())
    hits = [w["s"] for w in WORDS.get(bid, []) if "".join(c for c in w["w"].lower() if c.isalnum()).startswith(key)]
    if len(hits) >= nth:
        return hits[nth - 1]
    print(f"   miss {bid}:{word}:{nth}")
    text, at = TIMING[bid]["spoken"].lower(), -1
    for _ in range(nth):
        at = text.find(word.lower(), at + 1)
    return TIMING[bid]["duration"] * max(at, 0) / max(1, len(text))


class Take:
    """One scene's recording: a fresh browser context, its own clock, beat marks and actions on words."""

    def __init__(self, browser, url: str, name: str):
        self.url, self.name = url, name
        RAW.mkdir(parents=True, exist_ok=True)
        self.ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(RAW / name),
                                       record_video_size={"width": 1920, "height": 1080}, color_scheme="light")
        self.ctx.add_init_script("try { localStorage.setItem('portia-theme', 'light'); } catch (e) {}"
                                 "document.addEventListener('DOMContentLoaded', () => { document.documentElement.style.zoom = '1.5'; });")
        self.ctx.add_init_script(POINTER)
        self.pg = self.ctx.new_page()
        self.mouse = (1500.0, 820.0)
        self.t0 = time.time()
        self.cues, self.start, self.flash, self.late = [], None, None, []

    def clock(self) -> float:
        return time.time() - self.t0

    def until(self, t: float):
        ms = (t - self.clock()) * 1000
        if ms > 15:
            self.pg.wait_for_timeout(ms)

    def goto(self, route: str, wait: str):
        self.pg.goto(self.url + route)
        self.pg.wait_for_selector(wait, timeout=30000)
        self.pg.add_style_tag(content=CSS)

    def scroll(self, selector: str, offset: int = 90, ms: int = 1100):
        self.pg.evaluate("""([sel, off, ms]) => new Promise((done) => {
            const el = document.querySelector(sel); if (!el) return done();
            const y1 = el.getBoundingClientRect().top + window.scrollY - off, y0 = window.scrollY, t0 = performance.now();
            const step = (t) => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
              window.scrollTo(0, y0 + (y1 - y0) * e); k < 1 ? requestAnimationFrame(step) : done(); };
            requestAnimationFrame(step); })""", [selector, offset, ms])

    def glide(self, x: float, y: float, ms: int = 700):
        """Move the pointer to (x, y) in viewport pixels along an eased path, at about 60 steps a second."""
        x0, y0 = self.mouse
        n = max(8, ms // 16)
        for k in range(1, n + 1):
            e = k / n
            e = 4 * e ** 3 if e < .5 else 1 - (-2 * e + 2) ** 3 / 2
            self.pg.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            self.pg.wait_for_timeout(14)
        self.mouse = (x, y)

    def point(self, selector: str, ms: int = 700, dx: float = 0.5, dy: float = 0.5):
        """Glide to an element (a fraction dx, dy across it)."""
        b = self.pg.query_selector(selector).bounding_box()
        self.glide(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy, ms)

    def click(self, selector: str = None, ms: int = 700, xy=None):
        """Glide to an element (or a point) and click it with the real mouse, so the pointer shows the press."""
        if xy:
            self.glide(*xy, ms)
        elif selector:
            self.point(selector, ms)
        self.pg.mouse.down()
        self.pg.wait_for_timeout(90)
        self.pg.mouse.up()

    def overlay(self, html: str, pos: str = "top", oid: str = "demo-ov"):
        self.pg.evaluate("""([html, pos, oid]) => { let d = document.getElementById(oid);
            if (!d) { d = document.createElement('div'); d.id = oid; document.body.appendChild(d); }
            d.className = 'demo-ov ' + pos; d.innerHTML = html; requestAnimationFrame(() => requestAnimationFrame(() => d.classList.add('on'))); }""",
                         [html, pos, oid])

    def hide_overlay(self, oid: str = "demo-ov"):
        self.pg.evaluate("(oid) => { const d = document.getElementById(oid); if (d) d.classList.remove('on'); }", oid)

    def veil(self, on: bool, ms: int = 350):
        """Fade a paper-coloured veil over the page (on) or away (off): hides a route change inside a scene."""
        self.pg.evaluate("""([on, ms]) => new Promise((done) => { let v = document.getElementById('demo-veil');
            if (!v) { v = document.createElement('div'); v.id = 'demo-veil';
              v.style.cssText = 'position:fixed;inset:0;z-index:9998;background:#f6f5f1;opacity:0;pointer-events:none';
              document.body.appendChild(v); }
            v.style.transition = `opacity ${ms}ms ease`; requestAnimationFrame(() => { v.style.opacity = on ? '1' : '0'; });
            setTimeout(done, ms + 30); })""", [on, ms])

    def highlight(self, selector: str, on: bool = True):
        self.pg.evaluate("([s, on]) => { const el = document.querySelector(s); if (el) el.classList.toggle('demo-hl', on); }",
                         [selector, on])

    def begin(self):
        """The sync flash, then the scene starts (its first beat follows the gap)."""
        self.pg.evaluate("() => { const d = document.createElement('div'); d.id = 'demo-flash'; document.body.appendChild(d); }")
        self.pg.wait_for_timeout(120)
        self.flash = self.clock()
        self.pg.evaluate("() => document.getElementById('demo-flash').remove()")
        self.pg.wait_for_timeout(250)
        self.start = self.clock()

    def beat(self, bid: str, actions=(), gap: float = GAP):
        """Play one beat: it starts after `gap`; actions are (word, nth, fn) run when the word is spoken."""
        b0 = max(self.clock(), (self.cues[-1]["end"] if self.cues else self.start)) + gap
        self.until(b0)
        dur = TIMING[bid]["duration"]
        self.cues.append({"beat": bid, "start": round(b0 - self.start, 3), "duration": dur, "end": b0 + dur})
        for word, nth, fn in actions:
            at = b0 + (word_time(bid, word, nth) if word else 0.0) - LEAD
            if self.clock() - at > 0.8:
                self.late.append(f"{bid}:{word} {self.clock() - at:.1f}s")
            self.until(at)
            fn()

    def finish(self, tail: float = 0.8):
        self.until(self.cues[-1]["end"] + tail)
        end = self.clock()
        video = self.pg.video.path()
        self.ctx.close()
        cut(self, Path(video), end)


def flash_time(raw: Path) -> float:
    """When the magenta flash shows in the recording: frames at 60 fps, 16x9, the first mostly magenta one."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(raw), "-vf", "fps=60,scale=16:9", "-f", "rawvideo", "-pix_fmt",
                          "rgb24", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(out, np.uint8).reshape(-1, 9, 16, 3).astype(int)
    d = np.abs(frames - np.array(MAGENTA)).sum(axis=3)
    hit = np.where((d < 90).mean(axis=(1, 2)) > 0.8)[0]
    if not len(hit):
        raise SystemExit(f"{raw}: no sync flash found")
    return hit[0] / 60


def cut(take: Take, raw: Path, end_clock: float):
    """Cut the scene out of the recording (clock -> video time by the flash) and mix its beats in at their marks."""
    FOOT.mkdir(parents=True, exist_ok=True)
    CUES.mkdir(parents=True, exist_ok=True)
    shift = flash_time(raw) - take.flash                       # video time = clock + shift
    v0, dur = take.start + shift, end_clock - take.start
    ins, chains, labels = ["-ss", f"{v0:.3f}", "-t", f"{dur:.3f}", "-i", str(raw)], [], []
    for k, c in enumerate(take.cues, 1):
        ins += ["-i", str(AUDIO / TIMING[c["beat"]]["file"])]
        ms = int(round(c["start"] * 1000))
        chains.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{k}]")
        labels.append(f"[a{k}]")
    graph = ";".join(chains) + f";{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,apad,atrim=0:{dur:.3f}[a];" \
            "[0:v]fps=50,scale=1920:1080,setsar=1[v]"
    out = FOOT / f"{take.name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                    "-t", f"{dur:.3f}", str(out)], check=True)
    (CUES / f"{take.name}.json").write_text(json.dumps({
        "scene": take.name, "duration": round(dur, 3), "misses": [], "late": take.late,
        "cues": [{"beat": c["beat"], "start": c["start"], "duration": c["duration"]} for c in take.cues]}, indent=1), encoding="utf-8")
    print(f"{take.name}: {dur:.1f} s (sync shift {shift:+.2f} s) -> {out}{' late: ' + ', '.join(take.late) if take.late else ''}")


# ------------------------------------------------------------------ the footage scenes
def ballots(n_wrong: bool = False) -> str:
    sq = "".join(f'<span class="sq" style="background:var(--inv{j})">{j + 1}</span>' for j in range(3))
    tail = ('<span class="bad">&#10007; wrong: the notebook shows <b>cubes</b></span>' if n_wrong else
            '<span>All three: <b>sketches of human ears</b></span>')
    return sq + tail


def s01_cold_open(b, url):
    t = Take(b, url, "S01_ColdOpen")
    t.goto(f"#/job/{JOB}", "#smap-cv")
    t.pg.wait_for_timeout(1200)
    t.scroll("#smap", 70, 10)
    wrong = word_time("s01_1", "wrong")
    t.pg.evaluate(f"window.PORTIA_REPLAY_MS = {int((wrong + GAP - 0.25) * 1000)}")
    t.point("#smap-play", 10)                                  # the pointer rests on the button
    t.pg.wait_for_timeout(600)
    t.begin()
    t.click("#smap-play", 200)                                  # the search, replayed to end on "wrong"
    t.beat("s01_1", [("agreed", 1, lambda: t.overlay(ballots(), "bottom")),
                     ("wrong", 1, lambda: t.overlay(ballots(True), "bottom"))])
    t.finish(tail=1.2)


def unanimous(wrong: bool = False) -> str:
    """Five unanimous verdicts, three agents' squares each; the fifth one turns out wrong."""
    grp = lambda bad: (f'<span class="grp{" badg" if bad else ""}">'                              # noqa: E731
                       + "".join(f'<span class="sq" style="background:var(--inv{j})"></span>' for j in range(3)) + "</span>")
    tail = ('<span><b class="bad">1 in 5</b> unanimous verdicts were wrong</span><span class="muted">132 of 647, on 880 development runs</span>'
            if wrong else "<span>Three agents, one shared answer</span>")
    return "".join(grp(wrong and k == 4) for k in range(5)) + tail


def s03_problem(b, url):
    t = Take(b, url, "S03_Problem")
    t.goto(f"#/case/{CASE}", ".answer")
    t.pg.wait_for_timeout(1000)
    t.pg.evaluate("""() => {                 // the one detail the narration names, in each answer
        const pick = (s, w) => [...document.querySelectorAll(`#ans${s} mark`)].find((m) => m.textContent.includes(w));
        const a = pick('A', 'ears'), b = pick('B', 'cubes');
        if (a) a.id = 'demo-ears'; if (b) b.id = 'demo-cubes'; }""")
    t.point("h1.question", 10, 0.8, 0.4)
    t.pg.wait_for_timeout(400)
    t.begin()
    t.beat("s03_1", [("answers", 1, lambda: (t.scroll(".haystack", 110, 1000), t.point("#ansA .head", 600, 0.3, 0.5))),
                     ("ears", 1, lambda: (t.highlight("#demo-ears"), t.point("#demo-ears", 500, 0.5, 0.5))),
                     ("cubes", 1, lambda: (t.highlight("#demo-cubes"), t.point("#demo-cubes", 500, 0.3, 0.5)))])
    t.beat("s03_2", [("scrubbing", 1, lambda: (t.highlight("#demo-ears", False), t.highlight("#demo-cubes", False),
                                              t.highlight(".haystack"), t.point(".haystack", 400, 0.15, 0.5),
                                              t.point(".haystack", 1300, 0.95, 0.5))),
                     ("agreement", 1, lambda: (t.highlight(".haystack", False), t.overlay(unanimous(), "bottom"))),
                     ("wrong", 1, lambda: t.overlay(unanimous(True), "bottom"))])
    t.finish(tail=1.0)


TAG_RESULTS = """() => {                     // the How page's development table: a row for each setup the narration names
    const h = [...document.querySelectorAll('.h3')].find((x) => x.textContent.includes('Development results'));
    if (!h) return; h.id = 'demo-results';
    const rows = [...h.closest('.card').querySelectorAll('table.t tr')];
    const tag = (id, text) => { const r = rows.find((x) => x.textContent.includes(text)); if (!r) return;
        const c = r.querySelectorAll('td'); r.id = id; c[1].id = id + '-acc'; c[2].id = id + '-usd'; };
    tag('demo-vote', 'majority vote'); tag('demo-glim', 'Muse Glimmer adjudicator'); tag('demo-open', 'Muse Spark Open adjudicator');
    tag('demo-all', 'checks every verdict'); }"""


def s07_proof(b, url):                 # the development table, each setup lit as the narration names it
    t = Take(b, url, "S07_Proof")
    t.goto("#/how", "table.t")
    t.pg.wait_for_timeout(800)
    t.pg.evaluate(TAG_RESULTS)
    t.scroll("#demo-results", 110, 10)
    t.pg.wait_for_timeout(400)
    t.point("#demo-results", 10, 0.5, 0.5)
    t.begin()

    def row(on, off=None, ms=600):     # light one row, dim the one before, point at its accuracy
        if off:
            t.highlight(off, False)
        t.highlight(on)
        t.point(on + "-acc", ms, 0.5, 0.5)

    t.beat("s07_1", [("majority", 1, lambda: row("#demo-vote")),
                     ("Glimmer", 1, lambda: row("#demo-glim", "#demo-vote"))])
    t.beat("s07_2", [("Base", 1, lambda: row("#demo-open", "#demo-glim", 500)),
                     ("every", 1, lambda: row("#demo-all", "#demo-open", 500)),
                     ("half", 1, lambda: t.point("#demo-all-usd", 500, 0.5, 0.5))], gap=0.4)
    t.finish(tail=1.0)


def s05_catch(b, url):
    t = Take(b, url, "S05_Catch")
    t.goto(f"#/job/{JOB}", ".verdict")
    t.pg.wait_for_timeout(800)
    t.scroll("#vote", 260, 10)
    t.pg.wait_for_timeout(500)
    t.point("#vote .ballots", 10)
    t.begin()                    # ONE sync flash per take: a second one was cut into the chapter
    t.beat("s05_1", [("found", 1, lambda: (t.highlight("#vote .vote"), t.point("#vote .msg", 600, 0.3, 0.5))),
                     ("sketches", 1, lambda: (t.highlight("#vote .vote", False), t.scroll("#ft-inv0", 300, 1000),
                                              t.highlight("#ft-inv0 .why"), t.point("#ft-inv0 .why", 600, 0.6, 0.4)))])
    t.beat("s05_2", [("Spark", 1, lambda: (t.highlight("#ft-inv0 .why", False), t.scroll("#adj", 90, 900),
                                           t.point("#adj .agent-head", 500, 0.3, 0.5))),
                     ("cubes", 1, lambda: (t.highlight("#ft-adj .why"), t.point("#ft-adj .why", 600, 0.5, 0.5))),
                     ("overturned", 1, lambda: (t.highlight("#ft-adj .why", False), t.scroll("#verdict", 90, 1000),
                                                t.point("#verdict .trust", 600, 0.2, 0.5)))])
    t.beat("s05_3", [("", 1, lambda: t.click("#reveal", 650)),
                     ("agrees", 1, lambda: t.scroll("#truth", 160, 700))], gap=0.5)
    t.finish(tail=1.0)


def s06_moments(b, url):
    t = Take(b, url, "S06_Moments")
    t.goto(f"#/job/{JOB}", "#smap-cv")
    t.pg.wait_for_timeout(1500)
    t.scroll("#smap", 70, 10)
    t.pg.wait_for_timeout(2600)                               # the cited squares' first pulse plays off-camera
    cited = t.pg.get_attribute("#smap-cv", "data-cited").split()[0].split(",")
    box = t.pg.query_selector("#smap-cv").bounding_box()
    zoom = 1.5                                                 # bounding_box is in CSS px of the zoomed page
    cx, cy = box["x"] + float(cited[0]) * zoom, box["y"] + float(cited[1]) * zoom
    t.begin()
    t.glide(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.85, 10)
    t.begin()
    looks = [tuple(map(float, q.split(","))) for q in t.pg.get_attribute("#smap-cv", "data-looks").split()]
    look = lambda k: (box["x"] + looks[k][0] * zoom, box["y"] + looks[k][1] * zoom)    # squares viewed frame by frame
    t.beat("s06_1", [("thirty", 1, lambda: t.glide(*look(len(looks) // 3), 700)),
                     ("colored", 1, lambda: t.glide(*look(2 * len(looks) // 3), 600))])
    t.beat("s06_2", [("two", 1, lambda: t.glide(cx, cy, 800)),
                     ("Click", 1, lambda: t.click(xy=(cx, cy), ms=150)),
                     ("cubes", 1, lambda: t.pg.evaluate("() => { const v = document.querySelector('#clipdlg video'); if (v) { v.controls = false; v.currentTime = 2.6; } }")),
                     ("flowcharts", 1, lambda: t.pg.evaluate("() => { const v = document.querySelector('#clipdlg video'); if (v) { v.currentTime = 8.3; v.pause(); } }"))])
    t.finish(tail=2.6)


def s08_teams(b, url):
    t = Take(b, url, "S08_Teams")
    t.goto(f"#/batch/{BATCH}", "table")
    t.pg.wait_for_timeout(1500)
    t.begin()
    t.beat("s08_1", [("spreadsheet", 1, lambda: (t.scroll("table", 160, 1200), t.point("table tbody tr:nth-child(2)", 600, 0.3, 0.5))),
                     ("trust", 1, lambda: t.overlay('<span class="ok">Every case: verdict, trust level, cost</span>', "bottom"))])
    t.beat("s08_2", [("new", 1, lambda: (t.hide_overlay(), t.veil(True), t.pg.goto(url + f"#/job/{NEW_JOB}"),
                                         t.pg.add_style_tag(content=CSS), t.pg.wait_for_selector(".verdict", timeout=20000),
                                         t.scroll("#verdict", 90, 10), t.veil(False))),
                     ("live", 1, lambda: t.overlay('<span>A new question, run live</span><span class="muted">the agents read the number off the hull</span>', "bottom"))])
    t.finish(tail=1.4)


SCENES = {"S01_ColdOpen": s01_cold_open, "S03_Problem": s03_problem, "S05_Catch": s05_catch, "S06_Moments": s06_moments,
          "S07_Proof": s07_proof, "S08_Teams": s08_teams}     # S04_How is a live run: record_live.py


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5260/")
    ap.add_argument("--only")
    a = ap.parse_args()
    names = a.only.split(",") if a.only else list(SCENES)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for n in names:
            SCENES[n](b, a.url)
        b.close()


if __name__ == "__main__":
    main()
