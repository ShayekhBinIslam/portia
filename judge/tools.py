"""portia/judge/tools.py: the long-video tools the judge can call (OpenAI function-calling schema).

Modelled on the QuantiPhy agent's frame/view/answer toolset, retargeted from measuring one clip to
judging two answers against a LIBRARY of long videos. Every tool is scoped to the contest's DOMAIN
(the same scope as the final campaign's retrieved_domain arm), so the judge gets no hint the static
judges lacked (it is never told which playlist the question came from).

    search            semantic retrieval over 30-second segments (query encoded by scripts/local_encoder.py)
    grep_transcripts  case-insensitive regex over the speech of every segment in scope
    read_transcript   full dialogue of chosen segments, optionally with their neighbours
    view_frames       look at a segment: n frames, attached to the conversation as images
    list_videos       titles + ids of the videos in scope
    answer            the verdict ("A" or "B") and a short rationale; it ends the episode

Their definitions (what the model reads) are in tools/*.yaml; this module implements them (Toolbox).
"""
from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from judge import corpus, prompting

ROOT = Path(__file__).resolve().parents[1]
TX_CACHE = ROOT / ".cache" / "transcripts"

# The tool definitions the model sees (name, description, parameters) live in tools/<name>.yaml, and the toolsets
# (which tools, in which order) in tools/toolsets.yaml; judge/prompting.py loads them.
# v2 (search_video, contact_sheet, zoom) aimed at what the v1 agent missed (analysis/tool_failures.py): the answers
# differ almost only in VISUAL details, the agent viewed the evidence segment in only 44% of contests, and it saw
# 448 px thumbnails of 1280x720 sources. v3 and v4 use the v2 tools.
TOOLS = prompting.toolset("v1")
TOOLS_V2 = prompting.toolset("v2")


def hires_tools(tools: list) -> list:
    """The same tool list with the hi-res zoom description (tools/toolsets.yaml: zoom.hires). Muse Glimmer's encoder
    takes up to 4096 visual tokens per image but zoom capped images at 1024 px; Toolbox(zoom_side=1792) sizes them."""
    return [prompting.tool("zoom", "hires") if t["function"]["name"] == "zoom" else t for t in tools]


def v5_tools(tools_v2: list | None = None) -> list:
    """Toolset v5 (tools/toolsets.yaml): the v2 tools with zoom shown next to the whole frame (zoom.v5), plus burst.
    Zooming alone hurts questions about large objects and settings; burst shows 5 sharp moments over +-2 s."""
    return prompting.toolset("v5", {"zoom": "v5"})


REGIONS = {"full": (0, 0, 1, 1), "center": (.25, .25, .75, .75), "top": (.2, 0, .8, .5), "bottom": (.2, .5, .8, 1),
           "left": (0, .2, .5, .8), "right": (.5, .2, 1, .8), "top-left": (0, 0, .55, .55),
           "top-right": (.45, 0, 1, .55), "bottom-left": (0, .45, .55, 1), "bottom-right": (.45, .45, 1, 1)}


class Toolbox:
    """Executes tool calls for ONE contest. Images go back to the agent loop separately."""

    def __init__(self, contest, encoder, max_images: int = 24, log=print, toolset: str = "v1", zoom_side: int = 1024):
        self.c, self.enc, self.log, self.toolset, self.zoom_side = contest, encoder, log, toolset, zoom_side
        self.playlists = corpus.domain_playlists(contest.domain)
        corpus.register(self.playlists)          # every segment the search can return is resolvable
        self.max_images, self.images_used = max_images, 0
        self.calls: list[dict] = []

    # -------------------------------------------------------------- helpers
    def _line(self, s: dict, snippet: int = 160) -> str:
        title = corpus.titles().get(s["vid"], ("", None, None))[0][:70]
        tx = " ".join(corpus.transcript(s).split())[:snippet]
        sc = f" · sim {s['score']:.3f}" if "score" in s else ""
        return f"- {s['handle']} | {title} | {corpus.mmss(s['start'])}-{corpus.mmss(s['end'])}{sc} | \"{tx}\""

    def _transcripts(self, playlist: str) -> dict:
        """handle -> transcript for one playlist, built once into .cache/transcripts (thread-pooled reads)."""
        TX_CACHE.mkdir(parents=True, exist_ok=True)
        p = TX_CACHE / f"{corpus._key(playlist)}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        segs = corpus.index(playlist)["segs"]
        with ThreadPoolExecutor(max_workers=16) as ex:
            texts = list(ex.map(corpus.transcript, segs))
        d = {s["handle"]: t for s, t in zip(segs, texts)}
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d

    # -------------------------------------------------------------- tools
    def search(self, query: str, k: int = 8):
        k = max(1, min(12, int(k or 8)))
        qv = self.enc.encode([query])[0]
        hits = corpus.search(qv, self.playlists, k=k)
        return f"{len(hits)} segment(s) for \"{query}\":\n" + "\n".join(self._line(h) for h in hits), []

    def grep_transcripts(self, pattern: str, max_hits: int = 10):
        max_hits = max(1, min(20, int(max_hits or 10)))
        try:
            rx = re.compile(pattern, re.I)
        except re.error:
            rx = re.compile(re.escape(pattern), re.I)
        hits = []
        for pl in self.playlists:
            for h, t in self._transcripts(pl).items():
                m = rx.search(t)
                if m:
                    lo, hi = max(0, m.start() - 80), min(len(t), m.end() + 80)
                    hits.append((h, " ".join(t[lo:hi].split())))
        out = [f"- {h} | {corpus.titles().get(h.split('@')[0], ('',))[0][:60]} | "
               f"{corpus.mmss(int(h.split('@')[1]))} | \"...{snip}...\"" for h, snip in hits[:max_hits]]
        return (f"{len(hits)} segment(s) match /{pattern}/" + (f" (showing {max_hits})" if len(hits) > max_hits else "")
                + ":\n" + "\n".join(out)) if hits else f"no transcript matches /{pattern}/", []

    def read_transcript(self, handles: list, context: int = 0):
        context = max(0, min(2, int(context or 0)))
        out = []
        for h in list(handles)[:6]:
            s = corpus.segment(str(h))
            if not s:
                out.append(f"[{h}] unknown handle")
                continue
            for n in corpus.neighbors(s, context, context):
                mark = "*" if n["handle"] == s["handle"] else " "
                out.append(f"[{mark}{n['handle']} {corpus.mmss(n['start'])}-{corpus.mmss(n['end'])}] "
                           f"{corpus.transcript(n) or '(no speech)'}")
        return "\n".join(out), []

    def view_frames(self, handle: str, n: int = 4):
        n = max(1, min(6, int(n or 4)))
        s = corpus.segment(str(handle))
        if not s:
            return f"unknown handle {handle}", []
        left = self.max_images - self.images_used
        if left <= 0:
            return f"image budget ({self.max_images}) used up — decide from what you have seen and read", []
        title = corpus.titles().get(s["vid"], ("",))[0][:70]
        if self.toolset in ("v2", "v5"):         # ONE time-stamped strip (same 448 px per frame): 1 image of budget
            return self._strip(s, n, title)
        fr = corpus.frames(s, min(n, left))
        self.images_used += len(fr)
        return (f"{len(fr)} frame(s) of {handle} ({title}) at "
                + ", ".join(corpus.mmss(t) for _, t in fr) + " — attached below."), fr

    def list_videos(self):
        vids = []
        for pl in self.playlists:
            for v in corpus.database()[self.c.domain][pl]:
                if v["id"] not in {x[0] for x in vids}:
                    vids.append((v["id"], v.get("title", "")))
        shown = vids[:80]
        return (f"{len(vids)} video(s) in the library" + (" (first 80)" if len(vids) > 80 else "") + ":\n"
                + "\n".join(f"- {i} | {t[:90]}" for i, t in shown)), []

    # -------------------------------------------------------------- v2 tools
    def _strip(self, s: dict, n: int, title: str):
        from PIL import Image, ImageDraw, ImageFont
        fr = corpus.frames(s, n)
        w, h, cols = fr[0][0].width, fr[0][0].height, min(3, len(fr))
        sheet = Image.new("RGB", (cols * w + (cols - 1) * 4, math.ceil(len(fr) / cols) * (h + 4) - 4), "white")
        draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=20)
        for i, (im, t) in enumerate(fr):
            x, y = (i % cols) * (w + 4), (i // cols) * (h + 4)
            sheet.paste(im, (x, y))
            draw.rectangle((x, y, x + 74, y + 26), fill="black")
            draw.text((x + 5, y + 2), corpus.mmss(t), fill="yellow", font=font)
        self.images_used += 1
        return (f"{len(fr)} frame(s) of {s['handle']} ({title}) at " + ", ".join(corpus.mmss(t) for _, t in fr)
                + ", as one image (left to right, top to bottom, each stamped with its time). Use zoom(video, t) to "
                  "look closer."), [(sheet, f"frames {s['handle']}")]

    def _video(self, video):
        """'id' or 'id@seconds' -> (id, start or None); in scope (this contest's domain) or an error text."""
        m = re.fullmatch(r"\s*([A-Za-z0-9_-]{11})(?:@(\d+))?\s*", str(video))
        if not m:
            return None, None, f"unknown video {video!r}: pass an 11-character video id or a handle 'id@seconds'"
        segs = corpus.video_segments(m.group(1))
        if not segs or segs[0]["playlist"] not in self.playlists:
            return None, None, f"video {m.group(1)} is not in this library"
        return m.group(1), (int(m.group(2)) if m.group(2) else None), None

    def search_video(self, video: str, query: str, k: int = 6):
        vid, _, err = self._video(video)
        if err:
            return err, []
        k = max(1, min(10, int(k or 6)))
        hits = corpus.search_video(self.enc.encode([query])[0], vid, k=k)
        title = corpus.titles().get(vid, ("",))[0][:70]
        return f"{len(hits)} segment(s) of {vid} ({title}) for \"{query}\":\n" + "\n".join(self._line(h) for h in hits), []

    def contact_sheet(self, video: str, start, end, n: int = 12):
        from PIL import Image, ImageDraw, ImageFont
        vid, _, err = self._video(video)
        if err:
            return err, []
        if self.images_used >= self.max_images:
            return f"image budget ({self.max_images}) used up — decide from what you have seen and read", []
        segs = corpus.video_segments(vid)
        lo, hi = segs[0]["start"], segs[-1]["end"]
        s, e = max(lo, corpus.parse_time(start)), min(hi, corpus.parse_time(end))
        if e <= s:
            return f"empty range: {vid} runs {corpus.mmss(lo)}-{corpus.mmss(hi)}", []
        if e - s > 900:
            e = s + 900
        n = max(4, min(20, int(n or 12)))
        times = [s + (i + .5) * (e - s) / n for i in range(n)]
        with ThreadPoolExecutor(max_workers=8) as ex:
            frs = [f for f in ex.map(lambda t: corpus.frame_at(vid, t), times) if f]
        cols, tw = 4, 320
        th = int(tw * frs[0][0].height / frs[0][0].width)
        sheet = Image.new("RGB", (cols * tw + (cols - 1) * 4, math.ceil(len(frs) / cols) * (th + 4) - 4), "white")
        font = ImageFont.load_default(size=20)
        draw = ImageDraw.Draw(sheet)
        for i, (im, t) in enumerate(frs):
            x, y = (i % cols) * (tw + 4), (i // cols) * (th + 4)
            sheet.paste(im.resize((tw, th)), (x, y))
            draw.rectangle((x, y, x + 74, y + 26), fill="black")
            draw.text((x + 5, y + 2), corpus.mmss(t), fill="yellow", font=font)
        self.images_used += 1
        title = corpus.titles().get(vid, ("",))[0][:70]
        return (f"contact sheet of {vid} ({title}): {len(frs)} frames from {corpus.mmss(s)} to {corpus.mmss(e)}, one every "
                f"{(e - s) / n:.0f}s, left to right then top to bottom; each tile shows its time. Zoom in on a tile "
                f"with zoom(video, t)."), [(sheet, f"contact sheet {vid} {corpus.mmss(s)}-{corpus.mmss(e)}")]

    def zoom(self, video: str, t=None, region: str = "full", box=None):
        vid, start, err = self._video(video)
        if err:
            return err, []
        if self.images_used >= self.max_images:
            return f"image budget ({self.max_images}) used up — decide from what you have seen and read", []
        if t is None:
            if start is None:
                return "zoom needs t (the time to look at)", []
            t = start + 15
        fr = corpus.frame_at(vid, corpus.parse_time(t))
        if not fr:
            return f"no frame for {vid} at {t}", []
        im, ts = fr
        if box:
            try:
                x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in box)
            except (TypeError, ValueError):
                return "box must be [x0, y0, x1, y1] fractions between 0 and 1", []
            if x1 - x0 < .05 or y1 - y0 < .05:
                return "box too small: make each side at least 0.05 of the frame", []
            what = f"box [{x0:.2f}, {y0:.2f}, {x1:.2f}, {y1:.2f}]"
        else:
            region = region if region in REGIONS else "full"
            x0, y0, x1, y1 = REGIONS[region]
            what = f"region {region}"
        W, H = im.size
        crop = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        if self.toolset == "v5":
            return self._zoom_v5(vid, ts, im, crop, (x0, y0, x1, y1), what)
        sc = self.zoom_side / max(crop.size)
        if sc != 1:
            crop = crop.resize((int(crop.width * sc), int(crop.height * sc)), 1)      # 1 = LANCZOS
        self.images_used += 1
        title = corpus.titles().get(vid, ("",))[0][:70]
        return (f"zoom of {vid} ({title}) at {corpus.mmss(ts)}, {what}: {crop.width}x{crop.height} from "
                f"{int((x1 - x0) * W)}x{int((y1 - y0) * H)} source pixels."), [(crop, f"zoom {vid} {corpus.mmss(ts)} {what}")]

    def _zoom_v5(self, vid, ts, im, crop, frac, what):
        """The crop (up to 1280x720) next to the whole frame (640 px, crop outlined); a full-frame zoom is the native frame."""
        from PIL import Image, ImageDraw
        self.images_used += 1
        title = corpus.titles().get(vid, ("",))[0][:70]
        W, H = im.size
        if frac == (0, 0, 1, 1):
            return (f"zoom of {vid} ({title}) at {corpus.mmss(ts)}, whole frame at source resolution {W}x{H}."),\
                [(im.convert("RGB"), f"zoom {vid} {corpus.mmss(ts)} full")]
        sc = min(1280 / crop.width, 720 / crop.height)
        big = crop.resize((max(1, int(crop.width * sc)), max(1, int(crop.height * sc))), 1)
        thumb = im.convert("RGB").resize((640, int(640 * H / W)), 1)
        d = ImageDraw.Draw(thumb)
        x0, y0, x1, y1 = frac
        d.rectangle([x0 * thumb.width, y0 * thumb.height, x1 * thumb.width - 1, y1 * thumb.height - 1], outline=(255, 40, 40), width=4)
        canvas = Image.new("RGB", (big.width + 12 + thumb.width, max(big.height, thumb.height)), (255, 255, 255))
        canvas.paste(big.convert("RGB"), (0, 0))
        canvas.paste(thumb, (big.width + 12, 0))
        return (f"zoom of {vid} ({title}) at {corpus.mmss(ts)}, {what}: LEFT the crop enlarged to {big.width}x{big.height} "
                f"from {crop.width}x{crop.height} source pixels; RIGHT the whole frame with the crop outlined in red."),\
            [(canvas, f"zoom {vid} {corpus.mmss(ts)} {what}")]

    def burst(self, video: str, t=None, region: str = "full"):
        from PIL import Image, ImageDraw
        vid, start, err = self._video(video)
        if err:
            return err, []
        if self.images_used >= self.max_images:
            return f"image budget ({self.max_images}) used up — decide from what you have seen and read", []
        if t is None:
            if start is None:
                return "burst needs t (the middle moment)", []
            t = start + 15
        t0 = corpus.parse_time(t)
        region = region if region in REGIONS else "full"
        x0, y0, x1, y1 = REGIONS[region]
        tiles = []
        for dt in (-2, -1, 0, 1, 2):
            fr = corpus.frame_at(vid, max(0.0, t0 + dt))
            if not fr:
                continue
            im, ts = fr
            W, H = im.size
            crop = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))).convert("RGB")
            sc = 640 / crop.width
            tile = crop.resize((640, max(1, int(crop.height * sc))), 1)
            ImageDraw.Draw(tile).rectangle([0, 0, 92, 24], fill=(0, 0, 0))
            ImageDraw.Draw(tile).text((6, 5), corpus.mmss(ts) + f" {dt:+d}s", fill=(255, 255, 255))
            tiles.append(tile)
        if not tiles:
            return f"no frames for {vid} around {t}", []
        th = max(x.height for x in tiles)
        canvas = Image.new("RGB", (3 * 640 + 2 * 8, 2 * th + 8), (255, 255, 255))
        for i, tile in enumerate(tiles):
            canvas.paste(tile, ((i % 3) * 648, (i // 3) * (th + 8)))
        self.images_used += 1
        title = corpus.titles().get(vid, ("",))[0][:70]
        return (f"burst of {vid} ({title}) around {corpus.mmss(t0)}, region {region}: {len(tiles)} frames, 1 s apart, "
                f"left to right then the second row, each stamped with its time."), [(canvas, f"burst {vid} {corpus.mmss(t0)} {region}")]

    def run(self, name: str, args: dict):
        fn = {"search": self.search, "grep_transcripts": self.grep_transcripts,
              "read_transcript": self.read_transcript, "view_frames": self.view_frames,
              "list_videos": self.list_videos, "search_video": self.search_video,
              "contact_sheet": self.contact_sheet, "zoom": self.zoom, "burst": self.burst}.get(name)
        if fn is None:
            return f"unknown tool {name}", []
        try:
            text, imgs = fn(**(args or {}))
        except TypeError as e:
            text, imgs = f"bad arguments for {name}: {e}", []
        except Exception as e:
            text, imgs = f"{name} failed: {type(e).__name__}: {e}", []
        self.calls.append({"tool": name, "args": args, "result_chars": len(text), "images": len(imgs)})
        return text, imgs
