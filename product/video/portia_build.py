"""Build Portia's narrated demo (plan 018): the manim chapters (scenes.py, rendered by build_video.py's render_one) and
the screen-footage chapters (record_narrated.py), joined in script order with captions, chapters and EBU R128 loudness.
The caption and chapter code is the skill's (build_video.caption_cues, srt); the join scales every input to one size
and frame rate first, since footage and manim renders differ in preview quality.

    python portia_build.py render  [--quality preview|final] [--only S02_Title,...] [--jobs 4]    (video env)
    python portia_build.py sheets  [--only ...]                                                  contact sheets
    python portia_build.py compile [--quality preview|final]                                     out/<name>.mp4 + .srt
"""
import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import build_video as BV
from project import BUILD, OUT, script, video_name

SIZE = {"final": (1920, 1080, 50), "draft": (960, 540, 25), "preview": (854, 480, 15)}
BV.QUALITY["final"] = (["-r", "1920,1080", "--fps", "50"], "1080p50")      # 50 fps: footage (25 fps) doubles exactly
BV.QUALITY["draft"] = (["-r", "960,540", "--fps", "25"], "540p25")         # quick, but smooth enough to judge motion
XF = 0.6                                                                    # the dissolve between chapters, seconds


def scenes(kind=None):
    return [s for s in script().SCENES if kind is None or s["kind"] == kind]


def scene_path(s, quality):
    return BV.scene_file(quality, s["cls"]) if s["kind"] == "manim" else BUILD / "footage" / f"{s['cls']}.mp4"


def render(args):
    names = args.only.split(",") if args.only else [s["cls"] for s in scenes("manim")]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for msg in pool.map(lambda n: BV.render_one(n, args.quality), names):
            print(msg, flush=True)


def sheets(args):
    """Contact sheets of every chapter at the chosen quality (manim previews and footage alike)."""
    out = BUILD / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    for s in scenes():
        if only and s["cls"] not in only:
            continue
        v = scene_path(s, args.quality)
        if not v.exists():
            print("missing", s["cls"])
            continue
        dur = BV.probe_duration(v)
        step = max(1.5, dur / 16)
        rows = int((dur / step + 3) // 4) + 1
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(v), "-vf",
                        f"fps=1/{step:.2f},scale=480:-1,tile=4x{rows}:padding=4:color=white", "-frames:v", "1",
                        str(out / f"{s['cls']}.png")], check=True)
        print(f"{s['cls']}: {dur:.1f} s, a frame every {step:.1f} s -> {out / (s['cls'] + '.png')}")


def vdur(path):
    """The video stream's own length (xfade offsets must fall inside it)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return BV.probe_duration(path)


def encode(files, durs, srt_path, meta, out, quality):
    """Join the chapters with XF-second dissolves (xfade for the picture, acrossfade for the sound), then loudness."""
    w, h, fps = SIZE[quality]
    n, ins, chains = len(files), [], []
    for i, p in enumerate(files):
        ins += ["-i", str(p)]
        chains.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=#F6F5F1,"
                      f"fps={fps},setsar=1,format=yuv420p,settb=AVTB,trim=duration={durs[i]:.3f},setpts=PTS-STARTPTS[v{i}]")
        if BV.has_audio(p):
            chains.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,"
                          f"atrim=duration={durs[i]:.3f},asetpts=PTS-STARTPTS[a{i}]")
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={durs[i]:.3f},"
                          f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
    pv, pa, off = "v0", "a0", 0.0
    for i in range(1, n):
        off += durs[i - 1] - XF
        chains.append(f"[{pv}][v{i}]xfade=transition=fade:duration={XF}:offset={off:.3f}[xv{i}]")
        chains.append(f"[{pa}][a{i}]acrossfade=d={XF}:c1=qsin:c2=qsin[xa{i}]")
        pv, pa = f"xv{i}", f"xa{i}"
    graph = ";".join(chains) + f";[{pv}]null[v];[{pa}]{BV.LOUDNORM}[an]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-i", str(srt_path), "-i", str(meta),
                    "-filter_complex", graph, "-map", "[v]", "-map", "[an]", "-map", f"{n}:s", "-map_metadata", str(n + 1),
                    "-map_chapters", str(n + 1), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
                    "-movflags", "+faststart", str(out)], check=True)


def compile_all(args):
    S = script()
    pairs = [(s, scene_path(s, args.quality)) for s in scenes()]
    missing = [str(f) for _, f in pairs if not f.exists()]
    if missing:
        raise SystemExit("missing: " + ", ".join(missing))
    cues, lines, offset = [], [";FFMETADATA1", f"title={S.TITLE}"], 0.0
    if getattr(S, "ARTIST", ""):
        lines.append(f"artist={S.ARTIST}")
    durs = [vdur(f) for _, f in pairs]
    for k, ((s, f), dur) in enumerate(zip(pairs, durs)):
        cues += BV.caption_cues(s["cls"], offset)                           # each chapter starts XF into the dissolve
        end = offset + dur - (XF if k < len(pairs) - 1 else 0)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(offset * 1000)}", f"END={int(end * 1000)}",
                  f"title={s['chapter']}"]
        offset = end
    offset = sum(durs) - XF * (len(durs) - 1)
    base = video_name() + ("" if args.quality == "final" else f" ({args.quality})")
    OUT.mkdir(parents=True, exist_ok=True)
    srt_path, meta = OUT / f"{base}.srt", BUILD / "meta.txt"
    srt_path.write_text(BV.srt(cues), encoding="utf-8")
    meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
    encode([f for _, f in pairs], durs, srt_path, meta, OUT / f"{base}.mp4", args.quality)
    print(f"wrote {OUT / (base + '.mp4')} ({offset:.1f} s = {int(offset // 60)}:{offset % 60:04.1f}, {len(pairs)} chapters)")


XCUT = [("S01_ColdOpen", None), ("S06_Moments", None), ("S09_XEnd", None)]   # (scene, start after this beat): about 42 s;
#                                                                            S09_XEnd is the X-only ending (scenes.py)


def xcut(args):
    """A 30-45 s cut for X (plan 017's "Most Viral"): the hook, the moments, the Meta models with the end card. X autoplays muted, so the
    captions are burned in (and kept as a soft track too)."""
    S = script()
    by = {s["cls"]: s for s in S.SCENES}
    tmp = BUILD / "xcut"
    tmp.mkdir(parents=True, exist_ok=True)
    files, durs, cues, offset = [], [], [], 0.0
    for k, (cls, after) in enumerate(XCUT):
        src, t0 = scene_path(by.get(cls, {"cls": cls, "kind": "manim"}), "final"), 0.0
        if after:                                    # the end of that beat, from the scene's cue log
            cue = next(c for c in json.loads((BUILD / "cues" / f"{cls}.json").read_text(encoding="utf-8"))["cues"]
                       if c["beat"] == after)
            t0 = round(cue["start"] + cue["duration"], 2)
        if t0 > 0:
            part = tmp / f"{cls}_from{t0:g}.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t0:.3f}", "-i", str(src), "-c:v", "libx264", "-preset",
                            "medium", "-crf", "18", "-c:a", "aac", "-b:a", "160k", str(part)], check=True)
            src = part
        d = vdur(src)
        cues += [c for c in BV.caption_cues(cls, offset - t0) if c[0] >= offset - 0.05]
        files.append(src)
        durs.append(d)
        offset += d - (XF if k < len(XCUT) - 1 else 0)
    srt_path, meta = OUT / "Portia_x.srt", BUILD / "meta_x.txt"
    OUT.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(BV.srt(cues), encoding="utf-8")
    meta.write_text(f";FFMETADATA1\ntitle={S.TITLE}: every verdict turns on a detail\n", encoding="utf-8")
    soft = tmp / "x_soft.mp4"
    encode(files, durs, srt_path, meta, soft, "final")
    style = ("FontName=Inter,FontSize=15,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H99161718,"
             "BorderStyle=4,Outline=1,Shadow=0,MarginV=34")
    out = OUT / "Portia_x.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(soft), "-vf",
                    f"subtitles={srt_path}:force_style='{style}'", "-map", "0:v", "-map", "0:a", "-c:v", "libx264", "-preset",
                    "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    print(f"wrote {out} ({vdur(out):.1f} s, captions burned in)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "sheets", "compile", "xcut"])
    ap.add_argument("--quality", default="preview", choices=list(SIZE))
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    {"render": render, "sheets": sheets, "compile": compile_all, "xcut": xcut}[args.cmd](args)


if __name__ == "__main__":
    main()
