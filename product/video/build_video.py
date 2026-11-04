"""Render the scenes of a narrated video and write captioned MP4s with chapters (`video` env, ffmpeg on PATH).

  python -X utf8 build_video.py render  [--quality final|preview] [--only S02_Idea,...] [--jobs 3]
  python -X utf8 build_video.py sheets  [--only ...]       contact sheets of the preview renders -> build/sheets/*.png
  python -X utf8 build_video.py compile [--quality ...]    every scene in one MP4, one chapter per scene
  python -X utf8 build_video.py split   [--quality ...] [--only ...]   one MP4 per scene (a series of short videos)
  python -X utf8 build_video.py all     [--quality ...] [--jobs 3]     render + compile

Each scene renders in its own media folder, so parallel renders never share manim's caches (shared Tex caches
collided on Windows). A rendered scene already carries its narration and sound cues. compile/split join scenes,
normalize loudness (EBU R128: -16 LUFS, true peak -1.5 dB, LRA 11), add chapters, and mux a soft caption track
(mov_text) built from the beat start times each scene logs (build/cues/) and the word times (audio/words.json); the
same captions go to an .srt next to the MP4. Output: out/<VIDEO_NAME>.mp4 (+ " (preview)" for preview quality).
"""
import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from project import AUDIO, BUILD, OUT, SCENES_FILE, script, video_name  # noqa: E402

QUALITY = {"final": (["-r", "1920,1080", "--fps", "30"], "1080p30"), "preview": (["-ql"], "480p15")}
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def safe(text):
    """Text usable in a Windows file name."""
    return re.sub(r'[<>:"/\\|?*]', "", text).strip()


def scene_classes():
    return re.findall(r"^class ([A-Z]\d\d_\w+)\(Slide\)", SCENES_FILE.read_text(encoding="utf-8"), re.M)


def scene_file(quality, name):
    return BUILD / f"media_{quality}" / name / "videos" / SCENES_FILE.stem / QUALITY[quality][1] / f"{name}.mp4"


def render_one(name, quality):
    flags, _ = QUALITY[quality]
    cmd = [sys.executable, "-m", "manim", "render", *flags, "--disable_caching", "--media_dir",
           str(BUILD / f"media_{quality}" / name), str(SCENES_FILE), name]
    done = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        return f"{name} FAILED\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}"
    log = json.loads((BUILD / "cues" / f"{name}.json").read_text(encoding="utf-8"))
    notes = "".join(f"\n   miss {m}" for m in log["misses"]) + "".join(f"\n   late {m}" for m in log["late"])
    return f"{name} ok ({log['duration']:.1f} s){notes}"


def render(args):
    names = args.only.split(",") if args.only else scene_classes()
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for msg in pool.map(lambda n: render_one(n, args.quality), names):
            print(msg, flush=True)


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


# ---------------------------------------------------------------- captions
def chunks(text, limit=84):
    """Split a beat's caption into pieces of at most two lines, breaking after sentence ends where possible."""
    words, out, cur = text.split(), [], []
    for w in words:
        if cur and len(" ".join(cur + [w])) > limit:
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.?!:]$", w) and len(" ".join(cur)) > limit * 0.45:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    if len(out) > 1 and len(" ".join(out[-1])) < 30:  # no orphan tail
        merged = out[-2] + out[-1]
        k = min(range(1, len(merged)), key=lambda k: abs(len(" ".join(merged[:k])) - len(" ".join(merged[k:]))))
        if len(" ".join(merged[:k])) <= limit and len(" ".join(merged[k:])) <= limit:
            out[-2:] = [merged[:k], merged[k:]]
    return out


def two_lines(words, width=42):
    text = " ".join(words)
    if len(text) <= width:
        return text
    best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


def stamp(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def caption_cues(name, offset=0.0):
    """Caption pieces of every beat a scene said, timed by the aligned words (or evenly when there is no alignment).
    Captions show the written text (digits); the alignment is of the spoken text, so pieces map by word share."""
    timing = json.loads((AUDIO / "timing.json").read_text(encoding="utf-8"))
    words_path = AUDIO / "words.json"
    aligned = json.loads(words_path.read_text(encoding="utf-8")) if words_path.exists() else {}
    log = json.loads((BUILD / "cues" / f"{name}.json").read_text(encoding="utf-8"))
    cues = []
    for c in log["cues"]:
        bid, start = c["beat"], offset + c["start"]
        caption, dur = timing[bid]["text"], timing[bid]["duration"]
        spoken = aligned.get(bid, [])
        n_words, done = len(caption.split()), 0
        for part in chunks(caption):
            first, last = done, done + len(part) - 1
            done += len(part)
            if spoken:
                i0 = min(len(spoken) - 1, round(first / n_words * len(spoken)))
                i1 = min(len(spoken) - 1, max(i0, round((last + 1) / n_words * len(spoken)) - 1))
                a, b = spoken[i0]["s"], spoken[i1]["e"]
            else:
                a, b = dur * first / n_words, dur * (last + 1) / n_words
            cues.append([start + a, start + b + 0.25, two_lines(part)])
    return cues


def srt(cues):
    for k in range(len(cues) - 1):
        cues[k][1] = min(cues[k][1], cues[k + 1][0] - 0.04)
    return "\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))


# ---------------------------------------------------------------- encoding
def encode(files, srt_path, meta, out):
    """Concatenate scene files (a scene with no sound gets silence of its own length: without an audio stream the
    concat fails and leaves a 0-byte MP4), normalize loudness, and mux captions, chapters and metadata."""
    n = len(files)
    chains, joins, ins = [], "", []
    for i, p in enumerate(files):
        ins += ["-i", str(p)]
        if has_audio(p):
            chains.append(f"[{i}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={probe_duration(p):.3f},"
                          f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        joins += f"[{i}:v][a{i}]"
    graph = ";".join(chains) + f";{joins}concat=n={n}:v=1:a=1[v][a];[a]{LOUDNORM}[an]"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *ins, "-i", str(srt_path), "-i", str(meta),
           "-filter_complex", graph, "-map", "[v]", "-map", "[an]", "-map", f"{n}:s", "-map_metadata", str(n + 1),
           "-map_chapters", str(n + 1), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
           "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


def rendered(quality, names):
    files = [scene_file(quality, n) for n in names]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        raise SystemExit("render first: " + ", ".join(missing))
    return files


def compile_all(args):
    S = script()
    names = scene_classes()
    files = rendered(args.quality, names)
    chapters = {s["cls"]: s["chapter"] for s in S.SCENES}
    cues, lines, offset = [], [";FFMETADATA1", f"title={S.TITLE}"], 0.0
    if getattr(S, "ARTIST", ""):
        lines.append(f"artist={S.ARTIST}")
    for name, f in zip(names, files):
        dur = probe_duration(f)
        cues += caption_cues(name, offset)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(offset * 1000)}", f"END={int((offset + dur) * 1000)}",
                  f"title={chapters[name]}"]
        offset += dur
    base = video_name() + ("" if args.quality == "final" else " (preview)")
    OUT.mkdir(parents=True, exist_ok=True)
    srt_path, meta = OUT / f"{base}.srt", BUILD / "meta.txt"
    srt_path.write_text(srt(cues), encoding="utf-8")
    meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
    encode(files, srt_path, meta, OUT / f"{base}.mp4")
    print(f"wrote {OUT / (base + '.mp4')} ({offset / 60:.1f} min, {len(files)} chapters)")


def split(args):
    """One MP4 per scene, named "<n> - <chapter>", e.g. for a series of short videos."""
    S = script()
    by_cls = {s["cls"]: s for s in S.SCENES}
    names = args.only.split(",") if args.only else scene_classes()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, f in zip(names, rendered(args.quality, names)):
        s = by_cls[name]
        base = f"{s['n']:02d} - {safe(s['chapter'])}" + ("" if args.quality == "final" else " (preview)")
        srt_path, meta = OUT / f"{base}.srt", BUILD / f"{name}_meta.txt"
        srt_path.write_text(srt(caption_cues(name)), encoding="utf-8")
        meta.write_text(f";FFMETADATA1\ntitle={s['chapter']}\ncomment={S.TITLE}\n", encoding="utf-8")
        encode([f], srt_path, meta, OUT / f"{base}.mp4")
        print(f"wrote {base}.mp4 ({probe_duration(OUT / (base + '.mp4')):.1f} s)", flush=True)


def sheets(args):
    """A 4-column grid of frames from each preview render, to check layouts by eye before the final render."""
    out = BUILD / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    for name in (args.only.split(",") if args.only else scene_classes()):
        v = scene_file("preview", name)
        if not v.exists():
            print("missing", name)
            continue
        dur = probe_duration(v)
        step = max(2.5, dur / 20)
        rows = int((dur / step + 3) // 4) + 1
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(v), "-vf",
                        f"fps=1/{step:.2f},scale=480:-1,tile=4x{rows}:padding=4:color=white", "-frames:v", "1",
                        str(out / f"{name}.png")], check=True)
        print(f"{name}: {dur:.0f} s, frame every {step:.1f} s -> {out / (name + '.png')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "compile", "split", "sheets", "all"])
    ap.add_argument("--quality", default="final", choices=list(QUALITY))
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=3)
    args = ap.parse_args()
    if args.cmd in ("render", "all"):
        render(args)
    if args.cmd in ("compile", "all"):
        compile_all(args)
    if args.cmd == "split":
        split(args)
    if args.cmd == "sheets":
        sheets(args)


if __name__ == "__main__":
    main()
