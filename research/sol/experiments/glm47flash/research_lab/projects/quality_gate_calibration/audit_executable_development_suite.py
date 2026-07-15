#!/usr/bin/env python3
import hashlib, json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUITE=ROOT/"executable_development_v2"
def digest(v): return hashlib.sha256(v).hexdigest()
def unwrap(v,lang):
    a=v.strip().splitlines()
    if len(a)<3 or a[0]!=f"```{lang}" or a[-1]!="```": return None
    b="\n".join(a[1:-1]); return None if "```" in b else b
def main():
    raw=(SUITE/"development.jsonl").read_bytes(); rows=[json.loads(x) for x in raw.splitlines()]
    categories=Counter(r["category"] for r in rows)
    controls={"bare_code":unwrap("```python\nx=1\n```","python")=="x=1","prose_rejected":unwrap("x\n```python\nx=1\n```","python") is None,"nested_fence_rejected":unwrap("```python\nx=1\n```\n```python\ny=2\n```","python") is None,"wrong_schema_not_equal":{"arguments":{"file_path":"x"}}!={"arguments":{"path":"x"}}}
    ready=len(rows)==36 and set(categories.values())=={6} and all(controls.values()) and all("prompt" in r and "scorer" in r for r in rows)
    result={"schema_version":1,"classification":"derived_zero_cost_executable_development_readiness","suite_fixture_sha256":digest(raw),"ready":ready,"category_counts":dict(categories),"controls":controls,"holdout_status":"not_generated_not_inspected","nll_status":"unfrozen_requires_three_bf16_captures","provider_mutation":"prohibited"}
    (ROOT/"EXECUTABLE_DEVELOPMENT_SUITE_AUDIT.json").write_bytes(json.dumps(result,sort_keys=True,indent=2).encode()+b"\n")
    print(json.dumps(result,sort_keys=True))
    if not ready: raise SystemExit("not ready")
if __name__=="__main__": main()
