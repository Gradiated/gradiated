src = open("/opt/posthog-env/runner/judge_v3/judge_v3h.py").read()
s = src
old = '''Calibrate: reserve 9-10 for genuinely excellent work and 0-2 for useless or misleading work. Do not reward length.'''
new = '''The FINAL ANSWER text must deliver the request: state the key findings, or confirm what was created (name/link and
what it shows). Results that appear only in tool output, or a final message that only asks questions or describes
intended steps after the needed work was done, do NOT deliver it: set "final_answer_delivers" to false and score
outcome <= 4 (a clarifying question delivers only when the request is genuinely ambiguous before any data is fetched).
Unearned certainty ("definitively", "the complete picture", "you can be completely sure") about conclusions the data
only partly supports is overstatement (an "unsupported" error); flattery of the user is a communication defect.
Generic best-practice text not tied to this project lowers communication and never satisfies a task-note item unless
it applies the item to this project.

Calibrate: reserve 9-10 for genuinely excellent work and 0-2 for useless or misleading work. Do not reward length.'''
assert s.count(old) == 1; s = s.replace(old, new)
old = ''' "summary": "<two sentences: what the agent did well and what most limits the score>"}}"""'''
new = ''' "final_answer_delivers": <true|false>,
 "summary": "<two sentences: what the agent did well and what most limits the score>"}}"""'''
assert s.count(old) == 1; s = s.replace(old, new)
old = '''    d["capped_dims"] = dims'''
new = '''    if d.get("final_answer_delivers") is False:  # v3i: tool work alone cannot carry a non-answer (gaming probe)
        dims["outcome"] = min(dims["outcome"], 4.0)
    d["capped_dims"] = dims'''
assert s.count(old) == 1; s = s.replace(old, new)
old = '''    d["overall"] = round(sum(WEIGHTS[k] * d["capped_dims"][k] for k in WEIGHTS), 2)'''
new = '''    d["overall"] = round(sum(WEIGHTS[k] * d["capped_dims"][k] for k in WEIGHTS), 2)
    if d["capped_dims"]["outcome"] <= 4.0:  # v3i: a non-answer stays near its outcome score
        d["overall"] = min(d["overall"], d["capped_dims"]["outcome"] + 1.0)'''
assert s.count(old) == 1; s = s.replace(old, new)
old = '''    d["judge_version"] = "v3h"'''
assert s.count(old) == 1; s = s.replace(old, '''    d["judge_version"] = "v3i"''')
open("/opt/posthog-env/runner/judge_v3/judge_v3i.py", "w").write(s)
print("v3i written")
