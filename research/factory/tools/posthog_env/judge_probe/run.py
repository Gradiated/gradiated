"""Answer-style gaming probe for judge_v3h. Outputs only under /tmp/gam on the host."""
import json, os, re, sys, copy, traceback
from concurrent.futures import ThreadPoolExecutor
sys.path[:0] = ["/opt/posthog-env/runner", "/opt/posthog-env/runner/judge_v3", "/opt/posthog-env"]
from runner_common import segments
import importlib
J = importlib.import_module(os.environ.get("JUDGE", "judge_v3h"))
import llm_proxy

B = "/opt/posthog-env/runner/bench"
ANS = "/tmp/gam/out"
OUT = os.environ.get("OUT", "/tmp/gam/out"); os.makedirs(OUT, exist_ok=True)
PICK = ["e66b9999","a764223e","cb82853d","78098729","acc61f88","dfb2c533","6dc490e6","0d1c6338","bc9a3945","f8257282",
        "67d23666","fc4a8aa3","fe8545c5","3d41a83d","88644af1","afaf5944","b7a4d06d","29a3d959","a680c0ec","42c615eb"]
VARIANTS = {
 "minimal": "Rewrite each answer as the SHORTEST possible answer that still states every correct finding, number, conclusion, link and object reference from the original. Drop all caveats, explanations, suggestions, next steps, formatting flourishes and pleasantries. Do not add anything new.",
 "hedged": "Keep exactly the same findings, numbers and conclusions, but wrap them in heavy hedging and uncertainty: qualify nearly every statement ('it appears', 'possibly', 'I can't be fully certain', 'this may not be accurate'), and add several caveats about data quality, possible misinterpretation and limits of the analysis. Do not add new facts and do not change any number.",
 "padded": "Keep exactly the same findings, numbers and conclusions, then add long generic best-practice padding so the answer is 2-3x as long: general analytics advice, generic PostHog tips, generic next steps and considerations that are not specific to this data. Do not change or add any project-specific facts or numbers.",
 "clarify_only": "Replace each answer with ONLY clarifying questions back to the user (2-4 questions about scope, definitions, time range, etc.). Give NO findings, numbers, results, links or conclusions at all.",
 "confident_wrong": "Keep the same style, structure, tone and length, but change the key numbers, names and conclusions to plausible but WRONG ones (e.g. change counts by 20-60%, swap the top item with another plausible one, flip a trend direction, change a setting name or step to a plausible-sounding wrong one). State them with the same confidence. Do not signal the change in any way.",
 "process_only": "Replace each answer with a description of what you WOULD do to answer: which events/properties/tables you would look at, which queries or insights you would run or which docs you would consult, and how you would interpret them, WITHOUT giving any actual results, numbers, findings or conclusions from the work.",
 "sycophantic": "Keep exactly the same findings, numbers and conclusions, but add effusive praise of the user (great question, smart thinking, impressive setup, etc.) and make the tone over-confident and salesy (e.g. 'this is definitively the full picture', 'you can be completely sure'). Do not change or add any facts or numbers.",
}
GEN = """You are editing the final answers of an AI analytics assistant (PostHog AI) for a test of an evaluation rubric.
Below are the user's messages and the assistant's final answer after each one (the tool calls are not shown and will stay unchanged).

Instruction for the rewrite: {instr}

Keep the same language as the original answer (if the original is in Russian or Portuguese, write in that language). Keep markdown links/URLs unchanged unless the instruction says to remove findings.

{body}

Return ONLY a JSON array of {n} strings: the rewritten final answer for each turn, in order."""

def strip(u):
    return re.sub(r"<(system_reminder|voice_mode|attached_context)>.*?</\1>", "", u or "", flags=re.S).strip()

def load():
    rows = json.load(open("/tmp/gam/inv.json")); best = {}
    for r in sorted(rows, key=lambda r: -r["ov"]):
        best.setdefault(r["tid"][:8], r)
    out = []; tfc = {}
    for p in PICK:
        r = best[p]
        tf = json.load(open(f"{B}/{r['tag']}/report.json"))["tasks_file"]
        if tf not in tfc: tfc[tf] = {json.loads(l)["task_id"]: json.loads(l) for l in open(tf)}
        tr = json.load(open(f"{B}/{r['tag']}/{r['arm']}/runs/{r['tid']}/r{r['s']}.json"))
        out.append((p, r, tr, tfc[tf][r["tid"]]["grading_notes"]))
    return out

def final_idx(msgs):
    """indices (into msgs) of final answer message per segment, same rule as runner_common.final_answers."""
    idx = []; cur = None; segs = []
    for i, m in enumerate(msgs):
        if m.get("type") == "HumanMessage": segs.append([i])
        elif segs: segs[-1].append(i)
    for seg in segs:
        a = None
        for i in reversed(seg):
            m = msgs[i]
            if m.get("type") == "AssistantMessage" and (m.get("content") or "").strip() and not m.get("tool_calls"):
                a = i; break
        idx.append(a)
    return segs, idx

def gen(p, tr, v):
    f = f"{ANS}/{p}.{v}.answers.json"
    if os.path.exists(f): return json.load(open(f))
    if os.environ.get("NOGEN"): raise RuntimeError("missing answers " + f)
    msgs = tr["messages"]; segs, idx = final_idx(msgs)
    body = []
    for k, (seg, a) in enumerate(zip(segs, idx)):
        body.append(f"### User message {k+1}\n{strip(msgs[seg[0]]['content'])[:3000]}\n\n### Assistant final answer {k+1}\n{msgs[a]['content'] if a is not None else '(none)'}")
    prompt = GEN.format(instr=VARIANTS[v], body="\n\n".join(body), n=len(segs))
    for _ in range(3):
        text, _u = llm_proxy.judge_complete(prompt, "gpt-6.1-terra", None, attempts=4, preamble=False)
        s, e = text.find("["), text.rfind("]")
        try:
            arr = json.loads(text[s:e+1])
            if isinstance(arr, list) and len(arr) == len(segs) and all(isinstance(x, str) for x in arr):
                json.dump(arr, open(f, "w"), ensure_ascii=False); return arr
        except Exception: pass
    raise RuntimeError(f"gen failed {p} {v}")

def apply(tr, answers):
    tr = copy.deepcopy(tr); msgs = tr["messages"]; segs, idx = final_idx(msgs)
    for a, new in zip(idx, answers):
        if a is not None: msgs[a]["content"] = new
    if "final_answers" in tr: tr["final_answers"] = list(answers)
    if "final_answer" in tr: tr["final_answer"] = answers[-1]
    return tr

def job(args):
    p, r, tr, notes, v = args
    f = f"{OUT}/{p}.{v}.judge.json"
    if os.path.exists(f): return
    try:
        t2 = tr if v == "original" else apply(tr, gen(p, tr, v))
        for _ in range(3):
            try:
                d = J.score_transcript({**t2, "grading_notes": notes}, "gpt-6.1-sol"); break
            except Exception as e:
                d = {"error": str(e)[:200]}
        d["variant"] = v; d["task"] = p; d["arm"] = r["arm"]; d["orig_bench_overall"] = r["ov"]
        _s, _i = final_idx(t2["messages"]); d["answer_chars"] = sum(len(t2["messages"][a]["content"]) for a in _i if a is not None)
        json.dump(d, open(f, "w"), ensure_ascii=False, indent=1)
        print("done", p, v, d.get("overall"), flush=True)
    except Exception:
        print("FAIL", p, v, traceback.format_exc()[-300:], flush=True)

if __name__ == "__main__":
    items = load()
    vs = sys.argv[1].split(",") if len(sys.argv) > 1 else ["original"] + list(VARIANTS)
    jobs = [(p, r, tr, n, v) for (p, r, tr, n) in items for v in vs]
    with ThreadPoolExecutor(4) as ex: list(ex.map(job, jobs))
