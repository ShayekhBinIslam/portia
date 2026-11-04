"""Eight lines with "GPUs" for the voice judge (user: "ask it to a local audio lm as in our skills, judge").
GJ_VARIANT picks how the voice is told to say it: orig "G P Us" (heard as "G-P-us"), a "G P U's", b "gee pee yous".
Two lines are the demo's own (s04_1, s09_1); six are short sentences of the same register.

    GJ_VARIANT=a VIDEO_SCRIPT=gpujudge python tts_render.py render --engine qwen-ryan --out audio/takes/gj_a
"""
import os

from spoken_numbers import numbers_to_words

TITLE = "GPU pronunciation"
SAYS = {"orig": "G P Us", "a": "G P U's", "b": "gee pee yous"}
SCENES = [{"id": "gj", "n": 1, "cls": "GJ", "kind": "test", "chapter": "GPUs", "beats": [
    ("gj_1", "Portia sends three Muse Glimmer agents, running on our own GPUs, to investigate on their own. They search "
             "the footage, read the transcripts and zoom into frames."),
    ("gj_2", "We built Portia during the hackathon, on our earlier video search tools: Muse Glimmer on our own GPUs, "
             "Muse Spark 1.3 on the Meta Model API, and Muse Spark Open."),
    ("gj_3", "We run every agent on our own GPUs."),
    ("gj_4", "Two GPUs serve the whole jury."),
    ("gj_5", "The GPUs stay busy through the night."),
    ("gj_6", "Muse Glimmer runs on our GPUs with speculative decoding."),
    ("gj_7", "No cloud bill, just our own GPUs."),
    ("gj_8", "Three agents share two GPUs, and every verdict comes back in minutes."),
]}]
RESPELL = {"GPUs": SAYS[os.environ.get("GJ_VARIANT", "a")], "API": "A P I", "Spark 1.3": "Spark one point three"}
SAY = {}


def spoken(bid, text):
    if bid in SAY:
        return SAY[bid]
    for a, b in RESPELL.items():
        text = text.replace(a, b)
    return numbers_to_words(text)


def beats():
    for s in SCENES:
        for bid, text in s["beats"]:
            yield s["id"], bid, text, spoken(bid, text)
