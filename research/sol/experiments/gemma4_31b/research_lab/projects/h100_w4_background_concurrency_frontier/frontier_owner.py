#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
NEBIUS = Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items

IMAGE = 'docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
KEY = Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
PUBLIC_KEY = KEY.with_suffix('.pub')
RATE, DISK_RATE, TIMEOUT = 2.15, 0.0097222, 1320


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp'); temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n'); temporary.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trigger(primary: dict[str, object]) -> bool:
    result = primary.get('result', {})
    return bool(primary.get('stage') == 'primary' and primary.get('pass') is True and result.get('type') == 'gemma4_h100_w4_machete_background_frontier' and result.get('all_actual_consumers_pass') is True and len(result.get('rows', [])) == 24)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--output-dir', type=Path, required=True); parser.add_argument('--name', required=True); parser.add_argument('--deadline-epoch', type=float, required=True); args = parser.parse_args()
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=False); now = time.time()
    files = tuple(PROJECT / item for item in ('w4_frontier.py', 'head_frontier.py', 'remote_frontier_stage.sh', 'frontier_owner.py', 'launch_owner.py', 'BINDINGS.json'))
    checks = {'durable_owner': bool(os.getenv('INVOCATION_ID')) and os.getenv('SYSTEMD_EXEC_PID') == str(os.getpid()), 'name': bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', args.name)), 'files': all(path.is_file() for path in files), 'keypair': KEY.is_file() and PUBLIC_KEY.is_file(), 'inventory': not list_items('instance') and not list_items('disk'), 'deadline': 0 < args.deadline_epoch-now <= TIMEOUT, 'budget': (RATE+DISK_RATE)*TIMEOUT/3600 <= 1.25, 'bindings': json.loads((PROJECT/'BINDINGS.json').read_text()).get('pass') is True}
    atomic(output/'PRECREATE_TERMINAL.json', {'schema_version':1,'type':'h100_w4_frontier_precreate','timestamp':dt.datetime.now(dt.UTC).isoformat(),'checks':checks,'files':{str(p):digest(p) for p in files},'pass':all(checks.values())})
    if not all(checks.values()): return 1
    controller.PLATFORM='gpu-h100-sxm'; controller.PRESET='1gpu-16vcpu-200gb'; controller.DISK_GIB=100; controller.HOURLY_RATE_USD=RATE; controller.DISK_HOURLY_RATE_USD=DISK_RATE
    atomic(PROJECT/'STATUS.json', {'status':'active','priority':290,'researcher_profile':'execution','summary':'Retained H100 development owner runs exact W4 c48/c64/c96/c128 then actual tied-head follow-up sequentially.','next_action':'Attach to this owner; repair an ordinary first-call failure in place, or reconcile the retrieved typed terminal after cleanup.','provider_mutation':'exclusive_durable_owner_only','authorized_spend_usd':1.25,'wall_clock_budget_minutes':35,'provider_exposure_budget_minutes':22,'compute_budget':'0.37 H100 GPU-hours plus 2 local CPU-hours','storage_budget':'one 100-GiB provider disk; 1 GiB retained plus 2 GiB temporary','repair_window_seconds':600,'bindings':'BINDINGS.json','active_session':{'mode':'development','unit':f'{args.name}.service','unit_manager':'systemd --user','owner_pid':os.getpid(),'name':args.name,'artifact_root':str(output),'deadline_epoch':args.deadline_epoch,'expected_terminal':'typed paired W4/BF16 c48/c64/c96/c128 rows, then conditional actual ParallelLMHead rows, followed by authenticated cleanup'}})
    code = controller.run(output,args.name,KEY,PUBLIC_KEY,digest(PROJECT/'BINDINGS.json'),PROJECT/'remote_frontier_stage.sh',PROJECT/'w4_frontier.py',(PROJECT.parent/'h100_w4_marlin_direct_falsifier'/'h100_w4_marlin_tp_single_rank.py', PROJECT.parent/'h100_w4_marlin_exact_shape_mechanism'/'h100_w4_marlin_falsifier.py', PROJECT.parent/'h100_w4_marlin_exact_shape_mechanism'/'h100_w4_contract.py'), 'w4-frontier', max(1,int(args.deadline_epoch-time.time())), IMAGE, PROJECT/'remote_frontier_stage.sh',PROJECT/'head_frontier.py',(), 'head-frontier', trigger, repair_window_seconds=600)
    summary = json.loads((output/'summary.json').read_text()) if (output/'summary.json').is_file() else {'outcome':'controller_observability_failure'}
    terminal = PROJECT/'artifacts'/'OWNER_TERMINAL.json'; terminal.parent.mkdir(exist_ok=True); atomic(terminal, {'classification':'h100_w4_background_frontier_owner_terminal','controller_returncode':code,'controller_summary':summary,'completed_at_utc':dt.datetime.now(dt.UTC).isoformat()})
    atomic(PROJECT/'STATUS.json', {'status':'active','priority':290,'researcher_profile':'execution','summary':'H100 frontier owner terminal requires scientific reconciliation.','next_action':'Reconcile typed W4/head rows and authenticated cleanup.','provider_mutation':'forbidden_pending_reconciliation','authorized_spend_usd':1.25,'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(terminal),'bindings':'BINDINGS.json'})
    return code


if __name__ == '__main__': raise SystemExit(main())
