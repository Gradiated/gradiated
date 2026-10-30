"""Create judge v3h from the locked v3g on the GPU host (does not modify v3g).

    python3 make_judge_v3h.py /opt/posthog-env/runner/judge_v3

v3h = v3g plus task grading notes. Curated environment tasks carry grading notes from the task editor (what a correct
answer contains, how to check it against the twin, acceptable variations, what is not required). When a transcript
carries `grading_notes`, they are shown to the judge as guidance; the rollout's tool results stay the ground truth and
notes contradicted by the evidence are ignored. Without notes v3h prompts exactly like v3g.
"""

import os
import sys

d = sys.argv[1]
src = open(f"{d}/judge_v3g.py").read()
out = f"{d}/judge_v3h.py"
if os.path.exists(out) and "--force" not in sys.argv:
    print("exists (pass --force to regenerate)")
    sys.exit(0)


def rep(s: str, old: str, new: str) -> str:
    assert s.count(old) == 1, (s.count(old), old[:60])
    return s.replace(old, new)


s = rep(src, '"""Judge v3g (2026-10-30)', '"""Judge v3h (2026-10-30): v3g plus task grading notes (see make_judge_v3h.py in the repo). When a\n'
        'transcript carries `grading_notes` they are shown as guidance; the rollout evidence stays the ground truth.\n\n'
        'Judge v3g (2026-10-30)')
s = rep(s, "{docs_section}\n## How to read the evidence", "{docs_section}{notes_section}\n## How to read the evidence")
s = rep(s, "{docs_rules}\n## First,", "{docs_rules}{notes_rules}\n## First,")
s = rep(s, 'DOCS_SECTION = """', '''NOTES_SECTION = """
## Task notes from the environment designer (guidance, not an answer key)
{notes}
"""

NOTES_RULES = """- Task notes. They say what a correct answer should contain and how to check it. Go through "must_include" item by
  item: an item the final answers do not deliver is an error (material when it is the user's main request, moderate
  otherwise), and a refusal or "I could not find it" does not deliver it unless the tool results show it truly
  cannot be done. The rollout's tool results are the ground truth: where the evidence contradicts a note, follow the
  evidence. Accept the listed acceptable variations; do not penalise what the notes mark as not required. Do not
  penalise a reasonable reading of an earlier turn because a later scripted turn asks for more.
- Data quality. If the agent correctly points out that data in the project looks implausible or inconsistent (and
  its tool results show it), that is good analysis, not an error, even if the task notes do not mention it.
"""

DOCS_SECTION = """''')
s = rep(s, '''                           docs_rules=DOCS_RULES if docs["ran"] else "")''',
        '''                           docs_rules=DOCS_RULES if docs["ran"] else "",
                           notes_section=NOTES_SECTION.format(notes=json.dumps(tr.get("grading_notes"), ensure_ascii=False,
                                                                               indent=1)[:6000]) if tr.get("grading_notes") else "",
                           notes_rules=NOTES_RULES if tr.get("grading_notes") else "")''')
s = rep(s, '    d["judge_version"] = "v3g"', '    d["judge_version"] = "v3h"\n    d["grading_notes_used"] = bool(tr.get("grading_notes"))')
open(out, "w").write(s)
print("written")
