"""Base scene and house style for narrated manim videos (manim Community 0.22, `video` env).

Slide is one chapter of the video, timed to its narration:
  say(beat)          start a narration clip (after a short gap) and remember where it ends
  cue(word, nth)     wait until that word of the current beat is spoken (0.15 s lead), from audio/words.json
  until(word)        seconds from now to that word, to stretch an animation up to it
  hold(gap)          wait out the current clip (+ gap)
  head()             kicker, title, rule and "n / N" at the top; clear() fades everything else; finish() fades all
  your_call(q)       amber question card with a 5-second countdown and tick sounds (quiz moments)
Each scene writes build/cues/<Scene>.json: beat start times (for captions), cue words not found ("misses") and cues
reached more than 0.8 s late ("late"). Check both after every re-voice.

Cue words match the SPOKEN text by prefix: cue("ninety"), not cue("90"); cue("word") also hits "words", so pass
nth. A visual cued on a beat's last word is gone before anyone reads it: cue earlier or lengthen the next gap.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from manim import *

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import AUDIO, BUILD, SOUNDS, script  # noqa: E402

SCENES = script().SCENES
TIMING = json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))
WORDS_PATH = AUDIO / "words.json"
WORDS = json.loads(WORDS_PATH.read_text(encoding="utf-8")) if WORDS_PATH.exists() else {}
CUES = BUILD / "cues"
SND = {k: str(SOUNDS / f"{k}.wav") for k in ("chime", "reveal", "tick", "tock")}  # python sounds.py writes them

# Portia's palette (product/static/style.css, light theme): page, card, ink, the brand violet, answers A (blue) and
# B (orange), the trust tiers (green, amber, red) and the three investigators (validated for colour-vision deficiency)
BG, GROUND, CARD, INK, INK2, MUTED = "#F6F5F1", "#F0EEE8", "#FFFFFF", "#16171B", "#3F424A", "#7A7D86"
RULE, RULE2, ACCENT, DEEP, SOFT, EDGE = "#E6E3DB", "#D9D5CA", "#5B47D6", "#3B2AA8", "#EEEBFD", "#CFC8F7"
A_C, A_BG, A_INK = "#2563EB", "#E8EFFD", "#1D4ED8"
B_C, B_BG, B_INK = "#E8590C", "#FDEEE4", "#C2410C"
OK, OK_BG, BAD, BAD_BG, WARN, WARN_BG = "#0F8A4F", "#E3F5EC", "#D1352B", "#FBE9E7", "#B7791F", "#FBF2DF"
INV = ["#4A3AA7", "#0F9B8E", "#C026D3"]
AMBER, AMBER_BG, AMBER_EDGE = "#B7791F", "#FBF2DF", "#EBD3A0"          # your_call() still uses these
ROSE, ROSE_BG, ROSE_EDGE = "#D1352B", "#FBE9E7", "#F1C4BF"
SKY, SKY_BG, SKY_EDGE = "#2563EB", "#E8EFFD", "#C5D6FA"
GOLD, EVGREY = "#B7791F", "#A3A6AE"
SANS, HEAD, MONO = "Inter", "Instrument Serif", "JetBrains Mono"   # the site's fonts (~/.fonts/portia)
config.background_color = BG
FW = config.frame_width


# ---------------------------------------------------------------- building blocks
def T(text, size=30, color=INK, weight=NORMAL, font=SANS, **kw):
    return Text(text, font=font, font_size=size, color=color, weight=weight, **kw)


def H(text, size=48, color=INK, **kw):
    return Text(text, font=HEAD, font_size=size, color=color, weight=NORMAL, **kw)   # Instrument Serif: one weight


def N(text, size=30, color=INK, **kw):
    return Text(text, font=MONO, font_size=size, color=color, weight=SEMIBOLD, **kw)


def card(w, h, fill=CARD, stroke=RULE, r=0.2, sw=2):
    return RoundedRectangle(width=w, height=h, corner_radius=r, fill_color=fill, fill_opacity=1, stroke_color=stroke,
                            stroke_width=sw)


def boxed(label, stroke=RULE, pad=0.3, fill=CARD, sw=2, min_w=0, r=0.2):
    box = card(max(min_w, label.width + 2 * pad), label.height + 1.3 * pad, fill=fill, stroke=stroke, sw=sw, r=r)
    return VGroup(box, label.move_to(box))


def chip(text, color=ACCENT, size=24, fill=None, pad=0.2, stroke=None, min_w=0):
    lab = T(text, size, color, weight=SEMIBOLD)
    return boxed(lab, stroke=stroke or color, pad=pad, fill=fill or CARD, sw=2.2, r=0.16, min_w=min_w)


def fit_width(mob, width):
    if mob.width > width:
        mob.scale_to_fit_width(width)
    return mob


def note(text, size=19):
    """Small italic label, e.g. "schematic" or "illustration" on anything not drawn from real data."""
    return T(text, size, MUTED, slant=ITALIC)


def chart(xr, yr, w, h, xticks, yticks, xlabel="", ylabel="", xfmt=None, yfmt=None, size=18):
    """Axes with light gridlines and our own tick labels; returns a VGroup with the Axes as .ax."""
    ax = Axes(x_range=list(xr), y_range=list(yr), x_length=w, y_length=h, tips=False,
              axis_config={"color": MUTED, "stroke_width": 2.2, "include_ticks": False})
    grid = VGroup(*[Line(ax.c2p(xr[0], y), ax.c2p(xr[1], y), color=RULE2, stroke_width=1.3) for y in yticks])
    labs = VGroup(*[T(xfmt(v) if xfmt else f"{v:g}", size, MUTED).next_to(ax.c2p(v, yr[0]), DOWN, buff=0.13)
                    for v in xticks],
                  *[T(yfmt(v) if yfmt else f"{v:g}", size, MUTED).next_to(ax.c2p(xr[0], v), LEFT, buff=0.13)
                    for v in yticks])
    g = VGroup(grid, ax, labs)
    if xlabel:
        g.add(T(xlabel, size + 2, INK2).next_to(ax.c2p((xr[0] + xr[1]) / 2, yr[0]), DOWN, buff=0.55))
    if ylabel:
        g.add(T(ylabel, size + 2, INK2).rotate(PI / 2).next_to(ax.c2p(xr[0], (yr[0] + yr[1]) / 2), LEFT, buff=0.7))
    g.ax = ax
    return g


def curve(ax, xs, ys, color, sw=4.5, smooth=True, dashed=False, dashes=45):
    m = VMobject(stroke_color=color, stroke_width=sw)
    pts = [ax.c2p(x, y) for x, y in zip(xs, ys)]
    if smooth:
        m.set_points_smoothly(pts)
    else:
        m.set_points_as_corners(pts)
    return DashedVMobject(m, num_dashes=dashes, dashed_ratio=0.55) if dashed else m


def legend(rows, size=19):
    """rows of (label, colour, style) where style is "line", "dash", "dot" or "box"."""
    out = VGroup()
    for lab, col, style in rows:
        if style == "box":
            key = Rectangle(width=0.3, height=0.2, fill_color=col, fill_opacity=1, stroke_width=0)
        elif style in ("dash", "dot"):
            key = DashedLine(LEFT * 0.24, RIGHT * 0.24, color=col, stroke_width=4,
                             dash_length=0.08 if style == "dash" else 0.03)
        else:
            key = Line(LEFT * 0.24, RIGHT * 0.24, color=col, stroke_width=4)
        out.add(VGroup(key, T(lab, size, INK2)).arrange(RIGHT, buff=0.15))
    return out.arrange(DOWN, buff=0.12, aligned_edge=LEFT)


def letters(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ---------------------------------------------------------------- the scene
class Slide(Scene):
    SID = None  # the scene id in script.SCENES
    KICKER, TITLE = "", ""

    def setup(self):
        self.s = next(s for s in SCENES if s["id"] == self.SID)
        self._end, self._start, self._bid, self._cues = 0.0, 0.0, None, []
        self._misses, self._late = [], []
        self.header = VGroup()

    @property
    def now(self):
        return self.renderer.time

    def say(self, bid, gap=0.4):
        self.hold(gap)
        clip = TIMING[bid]
        self.add_sound(str(AUDIO / clip["file"]))
        self._bid, self._start, self._end = bid, self.now, self.now + clip["duration"]
        self._cues.append({"beat": bid, "start": round(self.now, 3), "duration": clip["duration"]})
        return clip["duration"]

    def hold(self, gap=0.0):
        rest = self._end + gap - self.now
        if rest > 1 / 60:
            self.wait(rest)

    def word_time(self, word, nth=1):
        key = letters(word)
        hits = [w["s"] for w in WORDS.get(self._bid, []) if letters(w["w"]).startswith(key)]
        if len(hits) >= nth:
            return hits[nth - 1]
        self._misses.append(f"{self._bid}:{word}:{nth}")
        text, at = TIMING[self._bid]["spoken"].lower(), -1  # no alignment: place it by its share of the characters
        for _ in range(nth):
            at = text.find(word.lower(), at + 1)
        return TIMING[self._bid]["duration"] * max(at, 0) / max(1, len(text))

    def cue(self, word, nth=1, lead=0.15):
        target = self._start + self.word_time(word, nth) - lead
        if target > self.now + 1 / 60:
            self.wait(target - self.now)
        elif self.now - target > 0.8:
            self._late.append(f"{self._bid}:{word} {self.now - target:.1f}s")

    def until(self, word, nth=1, lead=0.15):
        """Seconds from now until a word (at least 0.3), to stretch an animation up to it."""
        return max(0.3, self._start + self.word_time(word, nth) - lead - self.now)

    def head(self, count=True):
        k = T(self.KICKER, 22, ACCENT, weight=BOLD)
        t = fit_width(H(self.TITLE, 46, INK), FW - 3.2)
        grp = VGroup(k, t).arrange(DOWN, buff=0.08, aligned_edge=LEFT).to_corner(UL, buff=0.4)
        y = grp.get_bottom()[1] - 0.16
        line = Line([-FW / 2 + 0.4, y, 0], [FW / 2 - 0.4, y, 0], color=RULE, stroke_width=2)
        anims, parts = [FadeIn(k, shift=RIGHT * 0.15), FadeIn(t, shift=RIGHT * 0.25), Create(line)], [grp, line]
        if count:                                        # the chapter counter ("10 / 10"); a cut on its own has none
            n = T(f"{self.s['n']} / {len(SCENES)}", 20, MUTED).to_corner(UR, buff=0.45)
            anims.append(FadeIn(n))
            parts.append(n)
        self.play(*anims, run_time=0.85, rate_func=smooth)
        self.header = VGroup(*parts)

    def body(self):
        """Everything on screen except the header. The header's text is a grandchild of self.header, so skip its
        whole family (else every clear() wipes the title). Never wrap self.mobjects in a VGroup: TypeError."""
        keep = {id(m) for m in self.header.get_family()}
        return [m for m in self.mobjects if id(m) not in keep]

    def clear(self, run_time=0.6, keep=()):
        out = [m for m in self.body() if m not in keep]
        if out:
            self.play(*[FadeOut(m, shift=UP * 0.08) for m in out], run_time=run_time, rate_func=smooth)

    def finish(self, tail=0.6):
        self.hold(tail)
        self.play(*[FadeOut(m) for m in self.mobjects], run_time=0.7, rate_func=smooth)
        self.wait(0.15)                                  # the dissolve into the next chapter starts on a clean page

    def your_call(self, question, secs=5, y=-2.45, width=10.6, label="YOUR CALL", size=30, keep=False, x=0.0):
        """Amber question card (shown at once), then a countdown with a tick a second, started when the narration
        ends. The viewer can pause to think longer. Place it where it covers nothing the question needs."""
        lab = T(label, 22, AMBER, weight=BOLD)
        q = fit_width(T(question, size, INK), width - 2.9)
        inner = VGroup(lab, q).arrange(DOWN, buff=0.1, aligned_edge=LEFT)
        box = card(width, inner.height + 0.5, fill=AMBER_BG, stroke=AMBER_EDGE, r=0.22).move_to([x, y, 0])
        inner.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.38)
        pos = box.get_right() + LEFT * 0.95
        ring_bg = Circle(radius=0.44, stroke_color=AMBER_EDGE, stroke_width=9).move_to(pos)
        arc = Arc(radius=0.44, start_angle=PI / 2, angle=-TAU, stroke_color=AMBER, stroke_width=9).move_arc_center_to(pos)
        num = H(str(secs), 38, AMBER).move_to(pos)
        hint = T("pause to think longer", 18, MUTED).next_to(box, DOWN, buff=0.1).align_to(box, RIGHT)
        self.play(FadeIn(box, shift=UP * 0.15), FadeIn(inner, shift=UP * 0.15), FadeIn(ring_bg), Create(arc),
                  FadeIn(num), FadeIn(hint), run_time=0.45)
        self.hold(0.15)
        for k in range(secs, 0, -1):
            self.add_sound(SND["tick"])
            num.become(H(str(k), 38, AMBER).move_to(pos))
            target = Arc(radius=0.44, start_angle=PI / 2, angle=-TAU * (k - 1) / secs - 1e-3, stroke_color=AMBER,
                         stroke_width=9).move_arc_center_to(pos)
            self.play(Transform(arc, target), run_time=1.0, rate_func=linear)
        self.add_sound(SND["tock"])
        self._end = self.now
        self.play(FadeOut(VGroup(ring_bg, arc, num, hint)), run_time=0.3)
        call = VGroup(box, inner)
        if not keep:
            self.play(FadeOut(call), run_time=0.3)
        return call

    def tear_down(self):
        CUES.mkdir(parents=True, exist_ok=True)
        (CUES / f"{type(self).__name__}.json").write_text(json.dumps({"scene": self.SID, "duration": round(self.now, 3), "cues": self._cues, "misses": self._misses,
                        "late": self._late}, indent=1), encoding="utf-8")
