p = "/opt/posthog-env/correct/loop.py"
s = open(p).read()
old = '''if os.environ.get("LOOP_JUDGE") == "v3h":
    sys.path.insert(0, "/opt/posthog-env/runner/judge_v3")
    import judge_v3h as _JH  # noqa: E402'''
new = '''if os.environ.get("LOOP_JUDGE") in ("v3h", "v3i"):  # [V3I PATCH 2026-10-31] any judge_v3* with grading notes
    sys.path.insert(0, "/opt/posthog-env/runner/judge_v3")
    import importlib as _il  # noqa: E402
    _JH = _il.import_module("judge_" + os.environ["LOOP_JUDGE"])'''
if old in s:
    s = s.replace(old, new)
    open(p, "w").write(s)
    print("patched")
else:
    print("already" if "V3I PATCH" in s else "ANCHOR MISSING")
p = "/opt/posthog-env/correct/loop.py"
s = open(p).read()
old = '''if os.environ.get("LOOP_JUDGE") in ("v3h", "v3i"):  # [V3I PATCH 2026-10-31] any judge_v3* with grading notes'''
new = '''if os.environ.get("LOOP_JUDGE") == "v3h" and os.path.exists("/opt/posthog-env/runner/judge_v3/USE_V3I"):
    os.environ["LOOP_JUDGE"] = "v3i"  # judge v3i replaces v3h for loops started by scripts that export v3h
if os.environ.get("LOOP_JUDGE") in ("v3h", "v3i"):  # [V3I PATCH 2026-10-31] any judge_v3* with grading notes'''
assert s.count(old) == 1
open(p, "w").write(s.replace(old, new))
print("ok")
