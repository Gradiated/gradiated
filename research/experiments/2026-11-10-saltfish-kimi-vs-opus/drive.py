#!/usr/bin/env python3
"""Drive one Saltfish Max video from 'ideas' to a rendered MP4 over the local Studio API.

  drive.py <port> <video_id> [--pick N]

A fixed, model-blind customer policy, identical for both arms:
  ideas  -> pick idea N (default 0, the first one offered), no note
  script -> approve as written ("Make the video")
  build  -> wait; then render the MP4.
State snapshots go to .agents/runtime/saltfish_compare/<video_id>/drive.jsonl.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

port, vid = sys.argv[1], sys.argv[2]
pick = int(sys.argv[sys.argv.index("--pick") + 1]) if "--pick" in sys.argv else 0
BASE = f"http://localhost:{port}/api/v2/videos/{vid}"
OUT = Path("/root/.t3/worktrees/workspace/t3-aeba9a3a/.agents/runtime/saltfish_compare") / vid
OUT.mkdir(parents=True, exist_ok=True)


def call(method, path="", body=None, timeout=900):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode()[:2000]}


def note(kind, **kw):
    rec = {"t": time.strftime("%H:%M:%S"), "kind": kind, **kw}
    print(json.dumps(rec)[:600], flush=True)
    with (OUT / "drive.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


t0 = time.time()
last = None
answered = set()
made = False
while time.time() - t0 < 4 * 3600:
    st = call("GET", "/director").get("state") or {}
    phase = st.get("phase")
    if phase != last:
        note("phase", phase=phase, error=st.get("error"), step=st.get("step"), turn=st.get("turn"), elapsed=round(time.time() - t0))
        last = phase
    ask = st.get("ask") or {}
    if phase == "pick" and ask.get("id") not in answered:
        ideas = ask.get("ideas") or []
        (OUT / "ideas.json").write_text(json.dumps(ideas, indent=1))
        choice = ideas[min(pick, len(ideas) - 1)]["name"]
        r = call("POST", "/director/answer", {"askId": ask["id"], "pick": choice})
        answered.add(ask["id"])
        note("picked", idea=choice, ok="_http" not in r, resp=r if "_http" in r else None)
    elif phase == "approve" and ask.get("id") not in answered and not made:
        (OUT / "script.json").write_text(json.dumps(ask, indent=1))
        body = {"effort": "max", "askId": ask["id"]}
        if ask.get("script") is not None:
            body["script"] = ask["script"]
        r = call("POST", "/run", body)
        answered.add(ask["id"])
        made = "_http" not in r
        note("make", ok=made, resp=r)
    elif phase == "failed":
        note("failed", error=st.get("error"))
        break
    elif phase == "done":
        v = call("GET")
        if v.get("stage") in ("ready", "done", "made") or True:
            break
    time.sleep(15)

v = call("GET")
(OUT / "video.json").write_text(json.dumps(v, indent=1))
note("video", stage=v.get("stage"), scenes=len(v.get("scenes") or []), elapsed=round(time.time() - t0))
if last == "done":
    import subprocess
    for _ in range(240):  # the run publishes and archives after the director is done
        r = subprocess.run(["docker", "exec", "saltfish-studio-db-1", "psql", "-U", "studio_app", "-d", "studio", "-Atc",
                            f"select data->>'status' from runs where id='{vid}'"], capture_output=True, text=True).stdout.strip()
        if r in ("ready", "failed"):
            break
        time.sleep(15)
    note("run", status=r)
    if r == "ready":
        studio = "/root/saltfish/editor-lek/studio"
        films = OUT.parent / "films"
        films.mkdir(exist_ok=True)
        env = "set -a; . ./.env; set +a; export MODE=local PUPPETEER_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome; "
        cmd = env + f"mise exec node@24 -- node lib/render.ts {vid} --base http://localhost:3100 --out {films}/{vid}.mp4"
        p = subprocess.run(["bash", "-c", cmd], cwd=studio, capture_output=True, text=True)
        note("render", ok=p.returncode == 0, tail=(p.stdout + p.stderr)[-400:])
