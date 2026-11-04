"""Where a narration (or narrated-video) project keeps its files, and which narration module it reads.

The project folder holds script.py (the beats), audio/ (beat clips, timing.json, asr.json, words.json, sound cues),
build/ (renders, cue logs, contact sheets) and out/ (final files). Environment variables point a run at another
script or folder, so several videos or voice mixes can share one project (manim subprocesses inherit them):

  VIDEO_SCRIPT   narration module                        default: script
  VIDEO_SCENES   manim scenes file                       default: scenes.py
  VIDEO_AUDIO    beat clips + timing.json + words.json   default: audio
  VIDEO_BUILD    renders, cue logs, contact sheets       default: build
  VIDEO_OUT      final MP4 and SRT                       default: out
  VIDEO_NAME     output file name without extension      default: the script's TITLE

A second video with its own voice mix in the same folder, for example:
  VIDEO_SCRIPT=script_lit VIDEO_SCENES=scenes_lit.py VIDEO_AUDIO=audio_lit VIDEO_BUILD=build_lit python build_video.py all
"""
import importlib
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
AUDIO = HERE / os.environ.get("VIDEO_AUDIO", "audio")
BUILD = HERE / os.environ.get("VIDEO_BUILD", "build")
OUT = HERE / os.environ.get("VIDEO_OUT", "out")
SCENES_FILE = HERE / os.environ.get("VIDEO_SCENES", "scenes.py")
SOUNDS = HERE / "audio"  # sounds.py writes the cue sounds here; every voice mix shares them
TAKES = HERE / "audio" / "takes"  # tts_render.py --out audio/takes/<voice>: one folder per candidate voice


def script():
    return importlib.import_module(os.environ.get("VIDEO_SCRIPT", "script"))


def video_name():
    """VIDEO_NAME, else the script's TITLE without the characters Windows refuses in file names."""
    return os.environ.get("VIDEO_NAME") or re.sub(r'[<>:"/\\|?*]', "", script().TITLE).strip()
