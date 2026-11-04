"""Portia's 3-minute demo video: the narration (plan 018). The one source for every step: tts_render.py voices each
beat, scenes.py (manim) and record_narrated.py (screen footage) time their visuals to the beat clips, and the build
writes captions and one chapter per scene.

Every number below is traced (python script.py --facts prints the sources):
  a hundred hours the Drama collection the agents search: 109.1 h (/api/footage/Drama, 148 videos)
  one in five     unanimous verdicts that were wrong: 132 of 647 on 880 development runs (analysis/spark13_unanimous_report.py)
  880 / 74 / 82   runs, majority vote 74.1%, Spark 1.3 checking every verdict 82.0% (proof.json check_all)
  half a cent     $0.0038 per case (proof.json check_all.usd_per_case)
  a quarter, 93   the safest tier: 26.0% of verdicts at 93.4% (proof.json trust, s13_confirm_settled)
  case 038        job 1102-120834-5a94 (seeds 0-2, Spark 1.3 checking every verdict, all from cache): the three agents
                  looked at ARcH3epJjF4 21:00-21:30 (app wireframes) and said A, "sketches of human ears"; Spark 1.3
                  took a contact sheet of 20:00-22:00, zoomed 20:55 (isometric cubes, boxes, a page labelled BOX) and
                  21:05 (flowcharts), and overturned them to B; the answer key says B
  2 moments       the verdict's cited moments in 1 video, 20:55 and 21:05 (the search map, the evidence clip)
  before / during  NEW_WORK.md: only the video database and its segment index predate the hackathon (s00, the line
                  the organizers ask a video to open with)

Write for the ear: short sentences, plain words, one idea per sentence. Captions keep digits; spoken() turns numbers
into words and RESPELL fixes what the voice gets wrong. "kind" says how a scene is made: manim (scenes.py) or footage
(record_narrated.py drives the browser to the beats).

  python script.py     words and estimated seconds per scene, then every beat whose spoken text differs
"""
from spoken_numbers import numbers_to_words

TITLE = "Portia"
SUBTITLE = "Every verdict turns on a detail"
ARTIST = "Portia, Meta Global AI Developer Hackathon"

SCENES = [
    {"id": "s00", "n": 1, "cls": "S00_Before", "kind": "manim", "chapter": "Before and during the hackathon", "beats": [
        ("s00_1", "Before the hackathon, we had a video database and its search index. Everything else, we built "
                  "during the hackathon."),
    ]},
    {"id": "s01", "n": 2, "cls": "S01_ColdOpen", "kind": "footage", "chapter": "Three agents, one wrong answer", "beats": [
        ("s01_1", "Three AI agents searched over a hundred hours of video for one detail. All three agreed. All three "
                  "were wrong."),
    ]},
    {"id": "s02", "n": 3, "cls": "S02_Title", "kind": "manim", "chapter": "Portia", "beats": [
        ("s02_1", "This is Portia, a judge for AI answers about video. Every verdict shows the moments it rests on, "
                  "and how far to trust it."),
    ]},
    {"id": "s03", "n": 4, "cls": "S03_Problem", "kind": "footage", "chapter": "The problem", "beats": [
        ("s03_1", "Teams that build video AI compare answers like these every day. They differ in one detail: does "
                  "the notebook hold sketches of human ears, or of cubes?"),
        ("s03_2", "Checking means scrubbing through hours of footage. And agreement proves nothing: in our tests, "
                  "one unanimous verdict in five was wrong."),
    ]},
    {"id": "s04", "n": 5, "cls": "S04_How", "kind": "footage", "chapter": "How Portia works", "beats": [
        ("s04_1", "Portia sends three Muse Glimmer agents to investigate on their own, "
                  "turn by turn, with video tools we built: they search the footage, read the transcripts and zoom "
                  "into frames."),
        ("s04_2", "Then Muse Spark 1.3, on the Meta Model API, checks their evidence and rules."),
    ]},
    {"id": "s05", "n": 6, "cls": "S05_Catch", "kind": "footage", "chapter": "The catch", "beats": [
        ("s05_1", "In this case, all three agents found the notebook, looked at a page of app sketches, and went "
                  "with ears."),
        ("s05_2", "Spark 1.3 checked their evidence, then looked a little earlier in the scene: cubes, boxes, and a "
                  "page labelled BOX. It overturned all three, and flagged the verdict for a person to check."),
        ("s05_3", "The answer key agrees."),
    ]},
    {"id": "s06", "n": 7, "cls": "S06_Moments", "kind": "footage", "chapter": "The moments", "beats": [
        ("s06_1", "Here is everything they could search, over a hundred hours. Each square is thirty seconds, "
                  "colored where each agent looked."),
        ("s06_2", "The verdict rests on two moments in one video. Click, and you see them: the cubes, and the "
                  "flowcharts on the next page."),
    ]},
    {"id": "s07", "n": 8, "cls": "S07_Proof", "kind": "footage", "chapter": "Proof", "beats": [
        ("s07_1", "On our development set, a majority vote of three agents is right 74% of the time. A Muse Glimmer "
                  "adjudicator raises that to 75%, at no API cost."),
        ("s07_2", "On Baseten, Muse Spark Open gets 80.5%, and Spark 1.3 checking every verdict 82%, for under half a "
                  "cent a case."),
    ]},
    {"id": "s08", "n": 9, "cls": "S08_Teams", "kind": "footage", "chapter": "For evaluation teams", "beats": [
        ("s08_1", "Teams upload a whole run as a spreadsheet, or call the API, and get a verdict, a trust level and "
                  "a cost for every case."),
        ("s08_2", "It answers new questions live, too."),
    ]},
    {"id": "s09", "n": 10, "cls": "S09_Built", "kind": "manim", "chapter": "Built on Meta's models", "beats": [
        ("s09_1", "We built Portia and its video tools during the hackathon, on Meta's models: Muse Glimmer deployed "
                  "on Modal and Fireworks, Muse Spark 1.3 on the Meta Model API, and Muse Spark Open on Baseten."),
        ("s09_2", "Portia. Every verdict turns on a detail."),
    ]},
]

# names and acronyms the voice reads wrong, respelled for it (captions keep the real spelling)
RESPELL = {"GPUs": "G P U's", "API": "A P I", "Spark 1.3": "Spark one point three", "BOX": "box",   # "G P Us" was read "G P us"
           "Baseten": "Base ten"}

# a whole beat's spoken text, where respelling and number words are not enough
SAY = {}


def spoken(bid, text):
    """The words the voice reads."""
    if bid in SAY:
        return SAY[bid]
    for a, b in RESPELL.items():
        text = text.replace(a, b)
    return numbers_to_words(text)


def beats():
    """Every beat in order as (scene_id, beat_id, caption_text, spoken_text)."""
    for s in SCENES:
        for bid, text in s["beats"]:
            yield s["id"], bid, text, spoken(bid, text)


if __name__ == "__main__":
    total = 0
    for s in SCENES:
        w = sum(len(t.split()) for _, t in s["beats"])
        total += w
        print(f"{s['id']} {s['kind']:7s} {s['chapter']:32s} {len(s['beats'])} beats {w:4d} words  ~{w / 156 * 60:4.0f} s")
    print(f"{len(SCENES)} scenes, {sum(len(s['beats']) for s in SCENES)} beats, {total} words "
          f"(about {total / 156 * 60:.0f} s of narration at Ryan's 156 words a minute)")
    for _, bid, text, sp in beats():
        if sp != text:
            print(f"  {bid}: {sp}")
