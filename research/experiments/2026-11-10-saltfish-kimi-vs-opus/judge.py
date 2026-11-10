#!/usr/bin/env python3
"""Blind pairwise judge for two Saltfish Max films made from the same source and brief.

  judge.py <pair_name> <film_a.mp4> <film_b.mp4> [--judges opus,gpt] [--swap]

Each film becomes a contact sheet (one frame per second, 6 per row) plus a 4 fps strip of
its first 6 s. Films are labelled only "Film 1"/"Film 2"; every judge sees both orders
(the order flip cancels position bias). Judges run through the CLIProxyAPI subscription proxy.
Output: .agents/runtime/saltfish_compare/judge/<pair>/verdicts.json
"""
import base64
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PROXY = "http://100.105.48.19:8317"
KEY = Path("/root/.t3/worktrees/workspace/t3-aeba9a3a/../t3-cb1453dc/.agents/runtime/cliproxy/client.key").resolve().read_text().strip()
OUT = Path("/root/.t3/worktrees/workspace/t3-aeba9a3a/.agents/runtime/saltfish_compare/judge")
JUDGES = {"opus": "claude-opus-5-5", "gpt": "gpt-6.1-sol"}

RUBRIC = """You are judging two short branded product videos made by an AI video studio from the SAME
source page and the SAME brief, for the same fictional brand kit ("Acme": chalk/ink/grape palette,
Work Sans headlines, Inter body, sentence case). They are music-only (no voiceover).

For each film you get a contact sheet (one frame per second, left-to-right, top-to-bottom; the
timestamp is burned into each frame) and a strip of the opening seconds at 4 fps.

Score each film 1-10 on:
1. story: does the sequence explain the source clearly and in a sensible order?
2. craft: layout, typography, hierarchy, spacing; no overlaps, clipping, cut-off or tiny text, empty frames.
3. motion: does it look alive (things move with purpose across frames) rather than static slides?
4. brand: stays inside the kit's colours/fonts/tone; uses the real logo, does not invent marks.
5. overall: would a marketing lead ship it as is?
Then list the 3 most serious visible defects per film with timestamps, and pick a winner
(or "tie" only if genuinely indistinguishable).

Reply with JSON only:
{"film1":{"story":n,"craft":n,"motion":n,"brand":n,"overall":n,"defects":["..."]},
 "film2":{...}, "winner":"film1|film2|tie", "reason":"two sentences"}"""


def sheets(mp4: Path, tmp: Path, tag: str):
    a = tmp / f"{tag}_sheet.jpg"
    b = tmp / f"{tag}_open.jpg"
    draw = "drawtext=text='%{pts\\:hms}':x=10:y=10:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.6"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp4), "-vf",
                    f"fps=1,{draw},scale=480:-1,tile=6x10", "-frames:v", "1", "-q:v", "4", str(a)], check=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-t", "6", "-i", str(mp4), "-vf",
                    f"fps=4,{draw},scale=480:-1,tile=6x4", "-frames:v", "1", "-q:v", "4", str(b)], check=True)
    return [a, b]


def img(p: Path):
    return base64.b64encode(p.read_bytes()).decode()


def ask(judge: str, films: list[list[Path]]):
    model = JUDGES[judge]
    if judge == "opus":
        content = [{"type": "text", "text": RUBRIC}]
        for i, (sheet, opening) in enumerate(films, 1):
            content += [{"type": "text", "text": f"Film {i} — contact sheet:"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img(sheet)}},
                        {"type": "text", "text": f"Film {i} — opening at 4 fps:"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img(opening)}}]
        body = {"model": model, "max_tokens": 16000, "thinking": {"type": "adaptive"}, "messages": [{"role": "user", "content": content}]}
        req = urllib.request.Request(f"{PROXY}/v1/messages", data=json.dumps(body).encode(),
                                     headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=900).read())
        text = "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")
    else:
        content = [{"type": "text", "text": RUBRIC}]
        for i, (sheet, opening) in enumerate(films, 1):
            content += [{"type": "text", "text": f"Film {i} — contact sheet:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img(sheet)}"}},
                        {"type": "text", "text": f"Film {i} — opening at 4 fps:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img(opening)}"}}]
        body = {"model": model, "messages": [{"role": "user", "content": content}]}
        req = urllib.request.Request(f"{PROXY}/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"authorization": f"Bearer {KEY}", "content-type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=900).read())
        text = r["choices"][0]["message"]["content"]
    s = text[text.find("{"): text.rfind("}") + 1]
    return json.loads(s)


def main():
    pair, a, b = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    judges = sys.argv[sys.argv.index("--judges") + 1].split(",") if "--judges" in sys.argv else ["opus", "gpt"]
    out = OUT / pair
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        fa, fb = sheets(a, tmp, "A"), sheets(b, tmp, "B")
        for p in fa + fb:
            (out / p.name).write_bytes(p.read_bytes())
        res = []
        for j in judges:
            for order in ("AB", "BA"):
                films = [fa, fb] if order == "AB" else [fb, fa]
                v = ask(j, films)
                win = v.get("winner")
                mapped = {"film1": order[0], "film2": order[1]}.get(win, "tie")
                res.append({"judge": j, "order": order, "winner": mapped, "A": v["film1" if order == "AB" else "film2"],
                            "B": v["film2" if order == "AB" else "film1"], "reason": v.get("reason")})
                print(json.dumps(res[-1])[:500], flush=True)
    (out / "verdicts.json").write_text(json.dumps({"A": str(a), "B": str(b), "verdicts": res}, indent=1))


if __name__ == "__main__":
    main()
