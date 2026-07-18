#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, os, re, sys, time
from pathlib import Path

PROJECT=Path(__file__).resolve().parent
NEBIUS=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
sys.path.insert(0,str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE='docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); PUB=KEY.with_suffix('.pub')
RATE=2.15; DISK_RATE=.0097222
def atomic(path,value):
 tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,path)
def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--name',required=True); p.add_argument('--deadline-epoch',type=float,required=True); p.add_argument('--audit',type=Path,required=True); p.add_argument('--identity',type=Path,required=True); a=p.parse_args()
 out=a.output_dir.resolve(); out.mkdir(parents=True,exist_ok=False); audit=json.loads(a.audit.read_text()); identity=json.loads(a.identity.read_text())
 inputs=(PROJECT/'kv_paged_actual.py',PROJECT/'remote_stage.sh',a.audit,a.identity)
 instances=[metadata_name(x) for x in list_items('instance')]; disks=[metadata_name(x) for x in list_items('disk')]
 checks={'durable_owner':bool(os.getenv('INVOCATION_ID')) and os.getenv('SYSTEMD_EXEC_PID')==str(os.getpid()),'lowercase_name':bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',a.name)),'mechanical_identity':identity.get('pass') is True,'behavioral_precreate':audit.get('pass') is True,'staged_inputs':all(x.is_file() for x in inputs),'authenticated_empty_inventory':not instances and not disks,'keypair':KEY.is_file() and PUB.is_file(),'budget':(RATE+DISK_RATE)*1500/3600<=1.3,'deadline':0<a.deadline_epoch-time.time()<=1500}
 terminal={'schema_version':1,'type':'h100_actual_paged_fp8_kv_typed_precreate','timestamp':stamp(),'checks':checks,'inventory':{'instances':instances,'disks':disks},'pass':all(checks.values())}
 atomic(out/'PRECREATE_TERMINAL.json',terminal)
 if not terminal['pass']: return 1
 controller.PLATFORM='gpu-h100-sxm'; controller.PRESET='1gpu-16vcpu-200gb'; controller.DISK_GIB=100; controller.HOURLY_RATE_USD=RATE; controller.DISK_HOURLY_RATE_USD=DISK_RATE
 active={'unit':os.getenv('SYSTEMD_UNIT'),'unit_manager':'systemd --user','owner_pid':os.getpid(),'name':a.name,'artifact_root':str(out),'deadline_epoch':a.deadline_epoch,'expected_terminal':'atomically retrieved H100 actual-image producer/backend sentinel or typed provider failure with authenticated cleanup'}
 atomic(PROJECT/'STATUS.json',{'status':'active','priority':235,'researcher_profile':'execution','summary':'Durable H100 owner launched; actual unified KV producer is the first retrieved CUDA sentinel.','next_action':'Reconcile the durable owner terminal.','provider_mutation':'exclusive_durable_owner_only','authorized_spend_usd':1.3,'wall_clock_budget_minutes':40,'provider_exposure_budget_minutes':25,'compute_budget':'0.35 H100 GPU-hours plus 2 local CPU-hours','storage_budget':'one 100-GiB provider disk; 512 MiB retained plus 2 GiB temporary local','allocation_limit':1,'repair_limit':0,'active_session':active,'last_result_classification':'durable_h100_actual_paged_fp8_kv_owner_running','terminal_artifact':None})
 code=controller.run(out,a.name,KEY,PUB,hashlib.sha256((PROJECT/'PROJECT.md').read_bytes()).hexdigest(),PROJECT/'remote_stage.sh',PROJECT/'kv_paged_actual.py',(a.audit,a.identity),'h100-paged-kv-sentinel',max(1,int(a.deadline_epoch-time.time())),IMAGE)
 summary=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else {'outcome':'controller_observability_failure'}
 atomic(PROJECT/'artifacts/SUMMARY.json',{'classification':'h100_actual_paged_fp8_kv_terminal','controller_returncode':code,'controller_summary':summary,'completed_at_utc':stamp()})
 atomic(PROJECT/'STATUS.json',{'status':'active','priority':235,'researcher_profile':'execution','summary':'Durable H100 owner terminal requires typed scientific reconciliation.','next_action':'Reconcile the typed owner terminal and authenticated cleanup.','provider_mutation':'exclusive_durable_owner_only','authorized_spend_usd':1.3,'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(PROJECT/'artifacts/SUMMARY.json'),'last_result_classification':'h100_actual_paged_fp8_kv_owner_terminal'})
 return code
if __name__=='__main__': raise SystemExit(main())
