#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, hashlib, importlib.util, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; PROJECT_ROOT=HERE.parents[1]; SOURCE=PROJECT_ROOT/'iterations/graph-bound-endpoint-20260723t1930z'; PREVIOUS=HERE
spec=importlib.util.spec_from_file_location('prior_owner',SOURCE/'run_graph_endpoint_owner.py')
if spec is None or spec.loader is None: raise SystemExit('prior_owner_unavailable')
owner=importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
owner.HERE=HERE; owner.ARTIFACTS=HERE/'resident-consumer-repair-artifacts'; owner.REMOTE='/dev/shm/gemma4-fp8-tied-head-resident-consumer'; owner.PRIOR_SPEND_USD=1.3426684093166665; owner.ABSOLUTE_DEADLINE=dt.datetime(2026,7,23,23,30,tzinfo=dt.timezone.utc); owner.PRIOR_FINAL_SHA256=hashlib.sha256((PREVIOUS/'artifacts/FINAL_TERMINAL.json').read_bytes()).hexdigest(); owner.PRIOR_ARTIFACT_TREE_SHA256=owner.tree_sha256(PREVIOUS/'artifacts')
def validate_inputs():
 r=subprocess.run([sys.executable,str(PROJECT_ROOT/'verify_director_binding.py')],text=True,capture_output=True,timeout=30)
 if r.returncode: raise RuntimeError(f'director_binding_invalid:{r.stderr[-1000:]}')
 if hashlib.sha256((PROJECT_ROOT/'GRAPH_CAPTURE_PHASE_GATE_REPAIR.json').read_bytes()).hexdigest()!='759e64b139541a3e19cb5976ab818337c6f30cf4eb068b69b29cd74919389978': raise RuntimeError('graph_capture_phase_gate_repair_mutated')
def stage(ip):
 p=owner.remote(ip,f'rm -rf {owner.REMOTE}.stage && mkdir -p {owner.REMOTE}.stage',60)
 if p.returncode: raise RuntimeError(f'remote_stage_prepare_failed:{p.stderr[-1000:]}')
 owner.scp_to(ip,HERE/'remote_resident_consumer.sh',f'{owner.REMOTE}.stage/remote_graph_endpoint.sh')
 f=owner.remote(ip,f'rm -rf {owner.REMOTE}.previous && if test -d {owner.REMOTE}; then mv {owner.REMOTE} {owner.REMOTE}.previous; fi && mv {owner.REMOTE}.stage {owner.REMOTE}',60)
 if f.returncode: raise RuntimeError(f'remote_stage_finalize_failed:{f.stderr[-1000:]}')
owner.validate_inputs=validate_inputs; owner.stage=stage; raise SystemExit(owner.main())
