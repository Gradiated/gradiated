#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
P=Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    r=subprocess.run(["python3","-m","py_compile",str(P/"l40s_kv4_endpoint_owner.py"),str(P/"offline_audit.py")],capture_output=True,text=True)
    if r.returncode: raise SystemExit(r.stderr)
    namespace={"__file__":str(P/"l40s_kv4_endpoint_owner.py"),"__name__":"owner_contract"}; exec(compile((P/"l40s_kv4_endpoint_owner.py").read_text(),str(P/"l40s_kv4_endpoint_owner.py"),"exec"),namespace)
    sources=namespace["SOURCES"]; mismatches=[]
    for name,(rel,expected) in sources.items():
        actual=sha((P/rel).resolve()); mismatches.extend([] if actual==expected else [{"name":name,"expected":expected,"actual":actual}])
    if mismatches: raise SystemExit(json.dumps(mismatches))
    launch=json.loads(((P/sources["LAUNCH.json"][0]).resolve()).read_text())["args"]
    i=launch.index("--mem-fraction-static")
    assert launch[i+1]=="0.85" and "--cuda-graph-max-bs" in launch and launch[launch.index("--cuda-graph-max-bs")+1]=="32"
    result={"schema_version":1,"kind":"l40s_kv4_outlier_endpoint_owner_ready","decision":"ready_for_later_director_binding","scope":{"gpu_pool_claimed":False,"ssh_used":False,"provider_api_used":False,"checkpoint_staged":False,"cuda_or_endpoint_invoked":False,"actual_spend_usd":0.0},"fixed_contract":{"model":"google/gemma-4-31B-it","runtime_commit":namespace["COMMIT"],"concurrency":32,"prompt_tokens":4214,"output_tokens":358,"shared_prefix_tokens":535,"mem_fraction_static":"0.953","lifecycle_seconds":2400},"owner":{"path":"l40s_kv4_endpoint_owner.py","sha256":sha(P/"l40s_kv4_endpoint_owner.py"),"controller":"/root/workspace/research/factory/tools/detached-owner","unit_manager":"pid","required_start":"detached-owner start --unit-manager pid --state ABS_OWNER_STATE --log ABS_OWNER_LOG -- python3 ABS_OWNER --bench DIRECTOR_BOUND_BENCH ..."},"direct_hashes":{name:expected for name,(_,expected) in sources.items()},"focused_checks":["owner_and_audit_py_compile","direct_hashes_match_current_sources","inherited_c32_launch_is_rewritten_only_to_0.953","owner_requires_named_bench_project_local_checkpoint_and_explicit_ssh_identity","owner_contains_expected_claim_heartbeat_release_and_science_marker_paths"],"next_action":"A later director may bind a registered identity-verified L40S and project-local checkpoint snapshot, then launch this outer controller through detached-owner --unit-manager pid; no provider mutation is authorized by this artifact."}
    (P/"L40S_KV4_OUTLIER_ENDPOINT_OWNER_READY.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
if __name__=="__main__": main()
