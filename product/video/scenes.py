"""Portia's demo video: the animated chapters (manim, `video` env): S00 (what came before the hackathon), S02 (title)
and S09 (built on Meta's models). The screen-footage chapters (S01, S03, S05-S08) come from record_narrated.py, and
S04 is a new question run live on the live app, sped up (record_live.py). Every number is read from build/data.json
(video_data.py), every frame is a cited moment of case 038 at native resolution. Cue words match the spoken text
(script.py prints it).

    python build_video.py render --quality preview --only S02_Title,...      (or portia_build.py)
"""
import json

from slide_base import *  # noqa: F401,F403

DATA = json.loads((HERE / "build" / "data.json").read_text(encoding="utf-8"))
ASSETS = HERE / "build" / "assets"


def lines(text, width=40):
    """Break text into lines of at most `width` characters (manim's Text does not wrap)."""
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return "\n".join(out + [cur])


def phrase_glyphs(body, text, phrase):
    """The glyphs of `phrase` inside a Text: manim CE makes one submobject per non-space character."""
    flat, key = "".join(text.split()), "".join(phrase.split())
    i = flat.find(key)
    return body[i:i + len(key)] if i >= 0 else body


def letter(ch, color, size=0.62):
    sq = RoundedRectangle(width=size, height=size, corner_radius=0.14, fill_color=color, fill_opacity=1, stroke_width=0)
    return VGroup(sq, T(ch, 26, "#FFFFFF", weight=BOLD).move_to(sq))


def frame(path, h, label=None, size=17):
    im = ImageMobject(str(path)).scale_to_fit_height(h)
    border = Rectangle(width=im.width, height=im.height, stroke_color=RULE2, stroke_width=2).move_to(im)
    g = Group(im, border)
    if label:
        g = Group(g, T(label, size, MUTED)).arrange(DOWN, buff=0.12)
    return g


def credit():
    return T("Frames: public videos from the benchmark's collection, shown as evidence", 15, MUTED).to_corner(DR, buff=0.25)


class S00_Before(Slide):
    """The line the organizers ask a video to open with: what came before, what was built during the hackathon."""
    SID = "s00"

    def panel(self, title, text, color, fill, stroke):
        t = T(title, 28, color, weight=BOLD)
        body = T(lines(text, 30), 25, INK2, line_spacing=0.95)
        inner = VGroup(t, body).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        box = card(6.3, 3.5, fill=fill, stroke=stroke, sw=3)
        return VGroup(box, inner.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.45))

    def construct(self):
        before = self.panel("Before the hackathon", "A video database (videos, questions, answer keys) and its search index",
                            INK2, GROUND, RULE2)
        during = self.panel("Built during the hackathon", "Portia: the Muse agents and their video tools, the jury, the "
                            "Spark 1.3 checks, trust levels and the app", ACCENT, SOFT, ACCENT)
        fit_width(VGroup(before, during).arrange(RIGHT, buff=0.45), 12.8).move_to(ORIGIN)
        self.say("s00_1", gap=0.25)
        self.play(FadeIn(before, shift=UP * 0.12), run_time=0.6, rate_func=smooth)
        self.cue("Everything")
        self.play(FadeIn(during, shift=UP * 0.12), run_time=0.6, rate_func=smooth)
        self.finish(tail=0.35)


class S02_Title(Slide):
    SID = "s02"

    def construct(self):
        top = SVGMobject(str(ASSETS / "wordmark.svg")).scale_to_fit_height(1.75)
        tag = T("Every verdict turns on a detail", 34, INK2)
        Group(top, tag).arrange(DOWN, buff=0.38).move_to(UP * 1.95)
        self.play(FadeIn(top, scale=0.94, rate_func=smooth), run_time=1.0)
        self.say("s02_1", gap=0.2)
        self.play(FadeIn(tag, shift=UP * 0.15), run_time=0.6)
        self.cue("moments")
        thumbs = Group(*[frame(HERE / "build" / c["file"], 1.75, f"cited at {c['t'] // 60}:{c['t'] % 60:02d}") for c in DATA["cited"]])
        thumbs.arrange(RIGHT, buff=0.32).move_to(DOWN * 0.95)
        self.play(LaggedStart(*[FadeIn(t, shift=UP * 0.2) for t in thumbs], lag_ratio=0.18), run_time=0.9)
        self.cue("trust")
        chips = VGroup(chip("Safe to accept", OK, 22, OK_BG), chip("Spot-check", WARN, 22, WARN_BG),
                       chip("Needs review", BAD, 22, BAD_BG)).arrange(RIGHT, buff=0.3).move_to(DOWN * 3.0)
        self.play(LaggedStart(*[FadeIn(c, shift=UP * 0.15) for c in chips], lag_ratio=0.15), run_time=0.7)
        self.add(credit())
        self.finish()


class S03_Problem(Slide):
    SID = "s03"
    KICKER, TITLE = "THE PROBLEM", "Two answers, one detail apart"

    def answer(self, ch, color, soft, text, phrase):
        body = Text(lines(text, 34), font=SANS, font_size=24, color=INK2, line_spacing=0.9)
        phrase_glyphs(body, text, phrase).set_color(color)          # by glyph: a phrase may wrap across lines
        badge = letter(ch, color)
        head = VGroup(badge, T(f"Answer {ch}", 24, INK, weight=SEMIBOLD)).arrange(RIGHT, buff=0.2)
        inner = VGroup(head, body).arrange(DOWN, buff=0.28, aligned_edge=LEFT)
        box = card(inner.width + 0.7, inner.height + 0.6, stroke=RULE2)
        g = VGroup(box, inner.move_to(box))
        g.meta = {"phrase": phrase, "accent": color, "plain": text}     # not .color: manim reads that as a recolour
        g.body = body
        return g

    def construct(self):
        self.head()
        q = VGroup(T("The question, shortened:", 22, MUTED), T("What drawings are in the notebook?", 30, INK, weight=SEMIBOLD))
        q.arrange(RIGHT, buff=0.25).move_to(UP * 2.2)
        a = self.answer("A", A_C, A_BG, DATA["case"]["a"], DATA["case"]["phrases"][0])
        b = self.answer("B", B_C, B_BG, DATA["case"]["b"], DATA["case"]["phrases"][1])
        pair = fit_width(VGroup(a, b).arrange(RIGHT, buff=0.45), 12.8).next_to(q, DOWN, buff=0.4)
        self.play(FadeIn(q, shift=UP * 0.1), run_time=0.5)
        self.say("s03_1", gap=0.2)
        self.play(FadeIn(a, shift=RIGHT * 0.2), FadeIn(b, shift=LEFT * 0.2), run_time=0.8)
        for g, word in ((a, "ears"), (b, "cubes")):
            self.cue(word)
            m = g.meta
            hl = SurroundingRectangle(phrase_glyphs(g.body, m["plain"], m["phrase"]), color=m["accent"], buff=0.06,
                                      corner_radius=0.06, stroke_width=3)
            self.play(Create(hl), g[0].animate.set_stroke(m["accent"], width=3), run_time=0.5)
        self.say("s03_2", gap=0.6)
        self.clear(run_time=0.5)
        # scrubbing through the footage: one long strip, a playhead running across it
        hours = DATA["hours"]
        strip = RoundedRectangle(width=11.6, height=0.55, corner_radius=0.12, fill_color=GROUND, fill_opacity=1,
                                 stroke_color=RULE2, stroke_width=2).move_to(UP * 1.35)
        ticks = VGroup(*[Line(strip.get_left() + RIGHT * (11.6 * k / 24) + UP * 0.27, strip.get_left() + RIGHT * (11.6 * k / 24) + DOWN * 0.27,
                              color=RULE2, stroke_width=1.5) for k in range(1, 24)])
        lab = T(f"{hours:.0f} hours of footage, {DATA['videos']} videos", 24, INK2).next_to(strip, UP, buff=0.22)
        head = Line(strip.get_left() + UP * 0.42, strip.get_left() + DOWN * 0.42, color=BAD, stroke_width=5)
        self.play(FadeIn(strip), FadeIn(ticks), FadeIn(lab, shift=UP * 0.1), FadeIn(head), run_time=0.5)
        self.play(head.animate.move_to(strip.get_left() + RIGHT * 4.8), run_time=self.until("agreement"), rate_func=linear)
        # one unanimous verdict in five was wrong
        groups = VGroup()
        for k in range(5):
            dots = VGroup(*[Square(0.36, fill_color=INV[j], fill_opacity=1, stroke_width=0) for j in range(3)]).arrange(RIGHT, buff=0.08)
            ring = RoundedRectangle(width=dots.width + 0.34, height=0.7, corner_radius=0.14, stroke_color=RULE2, stroke_width=2,
                                    fill_color=CARD, fill_opacity=1)
            groups.add(VGroup(ring, dots.move_to(ring)))
        groups.arrange(RIGHT, buff=0.45).move_to(DOWN * 0.55)
        cap = T("three agents, one shared answer", 20, MUTED).next_to(groups, DOWN, buff=0.22)
        self.play(LaggedStart(*[FadeIn(g, shift=UP * 0.15) for g in groups], lag_ratio=0.12), FadeIn(cap), run_time=0.9)
        self.cue("wrong")
        bad = groups[4]
        cross = VGroup(Line(UL * 0.24, DR * 0.24), Line(UR * 0.24, DL * 0.24)).set_stroke(BAD, 6).next_to(bad, UP, buff=0.12)
        self.play(bad[0].animate.set_stroke(BAD, width=4).set_fill(BAD_BG), Create(cross), run_time=0.5)
        stat = VGroup(N(f"{DATA['unanimous_wrong']} of {DATA['unanimous']}", 34, BAD),
                      T("unanimous verdicts were wrong", 28, INK)).arrange(RIGHT, buff=0.25).move_to(DOWN * 2.35)
        note_ = note(f"development set: {DATA['runs']} runs with known answers").next_to(stat, DOWN, buff=0.15)
        self.play(FadeIn(stat, shift=UP * 0.15), FadeIn(note_), run_time=0.6)
        self.finish(tail=0.6)


class S04_How(Slide):
    SID = "s04"
    KICKER, TITLE = "HOW IT WORKS", "A jury of agents, then a check"

    def construct(self):
        self.head()
        agents = VGroup()
        for j in range(3):
            av = letter(str(j + 1), INV[j], 0.58)
            txt = VGroup(T(f"Investigator {j + 1}", 22, INK, weight=SEMIBOLD), T("Muse Glimmer 30B", 17, MUTED))
            txt.arrange(DOWN, buff=0.06, aligned_edge=LEFT)
            row = VGroup(av, txt).arrange(RIGHT, buff=0.22)
            box = card(row.width + 0.5, row.height + 0.36, stroke=RULE2)
            agents.add(VGroup(box, row.move_to(box)))
        agents.arrange(DOWN, buff=0.28)
        tools = VGroup(*[chip(t, ACCENT, 21, SOFT) for t in (f"Search {DATA['hours']:.0f} hours", "Read the transcripts", "Zoom into frames")])
        tools.arrange(DOWN, buff=0.34, aligned_edge=LEFT)
        spark = VGroup(T("Muse Spark 1.3", 26, INK, weight=SEMIBOLD), T("Meta Model API", 18, MUTED),
                       T("checks the agents' evidence", 18, INK2)).arrange(DOWN, buff=0.08)
        sbox = card(spark.width + 0.6, spark.height + 0.5, stroke=ACCENT, sw=3)
        sp = VGroup(sbox, spark.move_to(sbox))
        verdict = VGroup(T("Verdict", 24, INK, weight=SEMIBOLD), T("trust level", 18, INK2), T("cited moments", 18, INK2))
        verdict.arrange(DOWN, buff=0.08)
        vbox = card(verdict.width + 0.6, verdict.height + 0.5, fill=OK_BG, stroke=OK, sw=3)
        vd = VGroup(vbox, verdict.move_to(vbox))
        chain = VGroup(agents, tools, sp, vd).arrange(RIGHT, buff=0.75)
        fit_width(chain, 13.0).move_to(DOWN * 0.5)
        arrows = VGroup(*[Arrow(t.get_right(), sp.get_left(), buff=0.1, color=MUTED, stroke_width=3,
                                max_tip_length_to_length_ratio=0.12) for t in tools])
        links = VGroup(*[Line(a.get_right(), tools.get_left() + (a.get_center()[1] - tools.get_center()[1]) * UP * 0.0,
                              color=RULE2, stroke_width=2) for a in agents])
        arr = Arrow(sp.get_right(), vd.get_left(), buff=0.1, color=MUTED, stroke_width=3, max_tip_length_to_length_ratio=0.2)
        self.say("s04_1", gap=0.2)
        self.cue("Glimmer")
        self.play(LaggedStart(*[FadeIn(a, shift=RIGHT * 0.2) for a in agents], lag_ratio=0.15), run_time=0.8)
        for k, word in enumerate(("search", "transcripts", "zoom")):
            self.cue(word)
            self.play(FadeIn(tools[k], shift=RIGHT * 0.15), *([Create(links)] if k == 0 else []), run_time=0.4)
        self.say("s04_2", gap=0.35)
        self.cue("Spark")
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.1), FadeIn(sp, shift=LEFT * 0.2), run_time=0.8)
        self.cue("rules")
        self.play(GrowArrow(arr), FadeIn(vd, shift=LEFT * 0.15), run_time=0.6)
        self.finish(tail=0.5)


class S07_Proof(Slide):
    SID = "s07"
    KICKER, TITLE = "PROOF", f"Measured on {DATA['runs']} runs with known answers"
    FULL, X0 = 10.6, -5.9

    def bar(self, label, pct, color, y):
        lab = T(label, 23, INK2).move_to([self.X0, y + 0.55, 0], aligned_edge=LEFT)
        track = RoundedRectangle(width=self.FULL, height=0.6, corner_radius=0.1, fill_color=GROUND, fill_opacity=1, stroke_width=0)
        track.move_to([self.X0 + self.FULL / 2, y, 0])
        b = RoundedRectangle(width=self.FULL * pct / 100, height=0.6, corner_radius=0.1, fill_color=color, fill_opacity=1,
                             stroke_width=0).move_to([self.X0 + self.FULL * pct / 200, y, 0])
        val = N(f"{pct:.1f}%", 30, color).next_to(b, RIGHT, buff=0.2)
        return lab, track, b, val

    def construct(self):
        self.head()
        rows = [self.bar("Majority vote of three agents", DATA["vote"], EVGREY, 1.15),
                self.bar("Portia, with Spark 1.3 checking every verdict", DATA["check_all"], ACCENT, -0.35)]
        self.play(LaggedStart(*[FadeIn(VGroup(lab, track), shift=RIGHT * 0.15) for lab, track, _, _ in rows], lag_ratio=0.2),
                  run_time=0.8, rate_func=smooth)
        self.say("s07_1", gap=0.2)
        for (lab, track, b, val), (word, nth) in zip(rows, (("seventy", 1), ("eighty", 2))):   # 1: "eight hundred eighty"
            self.cue(word, nth, lead=0.5)
            self.play(GrowFromEdge(b, LEFT), FadeIn(val, shift=LEFT * 0.2), run_time=0.7)
        self.cue("half")
        cost = chip(f"${DATA['usd_per_case']:.4f} per case", INK2, 22).move_to([self.X0 + self.FULL - 1.4, -1.45, 0])
        self.play(FadeIn(cost, shift=UP * 0.1), run_time=0.4)
        foot = note(f"development set: {DATA['runs']} runs, 220 questions x 4 sets of three agents").to_edge(DOWN, buff=0.35)
        self.play(FadeIn(foot), run_time=0.3)
        self.say("s07_2", gap=0.5)
        self.clear(run_time=0.4, keep=[foot])
        t = DATA["tier"]
        total = 12.4
        segs, x = VGroup(), -total / 2
        spec = [("accept", OK, "Safe to accept", f"{t['accept']['pct_lo']:.0f}% right"),
                ("spot", WARN, "Spot-check", f"{t['spot']['pct_lo']:.0f}-{t['spot']['pct_hi']:.0f}% right"),
                ("review", BAD, "Needs review", f"{t['review']['pct_lo']:.0f}% right")]
        labels = VGroup()
        for k, (key, col, name, acc) in enumerate(spec):
            w = total * t[key]["share"] / 100
            seg = Rectangle(width=w - 0.05, height=0.9, fill_color=col, fill_opacity=0.9, stroke_width=0).move_to([x + w / 2, 0.7, 0])
            segs.add(seg)
            lab = VGroup(T(name, 22, col, weight=SEMIBOLD), T(f"{t[key]['share']:.0f}% of verdicts", 19, INK2), T(acc, 19, INK2))
            lab.arrange(DOWN, buff=0.05, aligned_edge=RIGHT if k == 2 else LEFT).next_to(seg, DOWN, buff=0.22)
            lab.align_to(seg, RIGHT if k == 2 else LEFT)
            labels.add(lab)
            x += w
        self.cue("trust", lead=0.3)
        self.play(LaggedStart(*[GrowFromEdge(sg, LEFT) for sg in segs], lag_ratio=0.25), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(lab, shift=UP * 0.1) for lab in labels], lag_ratio=0.2), run_time=0.7)
        self.cue("quarter")
        ring = SurroundingRectangle(segs[0], color=OK, buff=0.08, stroke_width=5, corner_radius=0.06)
        self.play(Create(ring), segs[1].animate.set_opacity(0.35), segs[2].animate.set_opacity(0.35), run_time=0.6)
        self.finish(tail=0.6)


class S09_Built(Slide):
    SID = "s09"
    KICKER, TITLE = "BUILT DURING THE HACKATHON", "On Meta's models"

    def model(self, name, lines_, color):
        txt = VGroup(T(name, 25, INK, weight=SEMIBOLD), *[T(l, 17, INK2) for l in lines_]).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        box = card(3.9, 1.75, stroke=color, sw=3)
        return VGroup(box, txt.move_to(box).align_to(box, LEFT).shift(RIGHT * 0.3))

    def cards(self):
        return VGroup(self.model("Muse Glimmer 30B", ["open weights", "deployed on Modal", "and Fireworks"], ACCENT),
                      self.model("Muse Spark 1.3", ["Meta Model API", "checks every verdict", "under half a cent a case"], A_C),
                      self.model("Muse Spark Open", ["open weights on Baseten", "an adjudicator option"], INV[1])
                      ).arrange(RIGHT, buff=0.35)

    def construct(self):
        self.head()
        cards = self.cards().move_to(UP * 0.85)
        new = VGroup(T("New in the hackathon:", 21, OK, weight=BOLD),
                     T("the long-video tools and the agents that use them turn by turn, the three-agent jury,", 21, INK2),
                     T("Spark 1.3 checks, trust levels, the search map, evidence clips, batch audits and the API", 21, INK2)).arrange(DOWN, buff=0.08)
        before = VGroup(T("From before:", 20, MUTED, weight=BOLD), T("the video database from our playlist-eval paper", 20, MUTED))
        before.arrange(RIGHT, buff=0.18)
        fit_width(VGroup(new, before).arrange(DOWN, buff=0.32), 12.6).move_to(DOWN * 1.85)
        self.say("s09_1", gap=0.2)
        self.play(FadeIn(new, shift=UP * 0.1), run_time=0.5)
        self.cue("hackathon")
        self.play(FadeIn(before, shift=UP * 0.1), run_time=0.4)
        for c, (word, nth) in zip(cards, (("Glimmer", 1), ("Spark", 1), ("Open", 1))):
            self.cue(word, nth)
            self.play(FadeIn(c, shift=UP * 0.15), run_time=0.45)
        self.hold(0.5)                                  # the end card is in place before its line starts
        self.clear(run_time=0.5)
        self.play(FadeOut(self.header), run_time=0.4, rate_func=smooth)
        self.header = VGroup()
        top = SVGMobject(str(ASSETS / "wordmark.svg")).scale_to_fit_height(1.6)
        tag = T("Every verdict turns on a detail", 34, INK2)
        url = T("portia.shayekh.tech", 30, ACCENT, weight=SEMIBOLD)
        Group(top, tag, url).arrange(DOWN, buff=0.38).move_to(UP * 0.3)
        self.play(FadeIn(top, scale=0.94, rate_func=smooth), run_time=0.9)
        self.say("s09_2", gap=0.15)
        self.cue("Every")
        self.play(FadeIn(tag, shift=UP * 0.15), run_time=0.5)
        self.play(FadeIn(url, shift=UP * 0.1), run_time=0.4)
        self.hold(1.6)
        self.wait(0.4)



class S09_XEnd(S09_Built):
    """The X cut's ending (portia_build.py XCUT), not a chapter of the full video: the Meta models stay on screen,
    then Portia joins them below on its closing line (s09_2), with the models still up."""

    def construct(self):
        self.head(count=False)
        cards = self.cards().scale(0.9).next_to(self.header, DOWN, buff=0.4)
        self.play(LaggedStart(*[FadeIn(c, shift=UP * 0.15) for c in cards], lag_ratio=0.35), run_time=1.3)
        self.wait(3.5)                                  # the models on their own, long enough to read
        mark = SVGMobject(str(ASSETS / "wordmark.svg")).scale_to_fit_height(1.1)
        tag = T("Every verdict turns on a detail", 30, INK2)
        url = T("portia.shayekh.tech", 27, ACCENT, weight=SEMIBOLD)
        Group(mark, tag, url).arrange(DOWN, buff=0.22).next_to(cards, DOWN, buff=0.5)   # clear of the burned captions
        self.play(FadeIn(mark, scale=0.94, rate_func=smooth), run_time=0.9)
        self.say("s09_2", gap=0.15)
        self.cue("Every")
        self.play(FadeIn(tag, shift=UP * 0.15), run_time=0.5)
        self.play(FadeIn(url, shift=UP * 0.1), run_time=0.4)
        self.hold(2.0)
        self.wait(0.4)
