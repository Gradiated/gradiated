"""Let the fault-guided correction loop (/opt/posthog-env/correct/loop.py) judge with v3h and task grading notes.
Idempotent; backs up loop.py once.

    python3 patch_loop_v3h.py /opt/posthog-env/correct/loop.py

With LOOP_JUDGE=v3h, loop.v3_score (used by judge3, the critic and the keep decision) scores through
runner/judge_v3/judge_v3h.score_transcript, attaching the task's curation grading notes from LOOP_NOTES_FILE (a task
JSONL with "grading_notes"). Without the variable the loop is unchanged (judge v3d).
"""

import os
import shutil
import sys

p = sys.argv[1]
bak = p + ".before-v3h-20261031"
if not os.path.exists(bak):
    shutil.copy2(p, bak)
s = open(p).read()
if "LOOP_JUDGE" in s:
    print("already patched")
    sys.exit(0)
anchor = "\ndef passes(rec: dict, thresh: float) -> bool:"
assert s.count(anchor) == 1
s = s.replace(anchor, '''

# [V3H PATCH 2026-10-31] judge v3h with curation grading notes when LOOP_JUDGE=v3h
if os.environ.get("LOOP_JUDGE") == "v3h":
    sys.path.insert(0, "/opt/posthog-env/runner/judge_v3")
    import judge_v3h as _JH  # noqa: E402

    _NOTES: dict = {}

    def _notes_for(tid):
        if not _NOTES and os.environ.get("LOOP_NOTES_FILE"):
            for _line in open(os.environ["LOOP_NOTES_FILE"]):
                if _line.strip():
                    _t = json.loads(_line)
                    _NOTES[_t["task_id"]] = _t.get("grading_notes")
        return _NOTES.get(tid)

    def v3_score(tr: dict, judge_model: str = "gpt-6.1-sol") -> dict:  # noqa: F811
        notes = _notes_for(tr.get("task_id"))
        with V3_SLOTS:
            return _JH.score_transcript({**tr, "grading_notes": notes} if notes else tr, judge_model)
''' + anchor, 1)
open(p, "w").write(s)
print("patched")
