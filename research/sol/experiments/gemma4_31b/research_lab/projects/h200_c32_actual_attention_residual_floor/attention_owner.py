#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, os, sys, time
from pathlib import Path
PROJECT=Path(__file__).resolve().parent; NEBIUS=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'); sys.path.insert(0,str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items
from vllm_smoke_control import start_independent_watchdog
IMAGE='docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'; KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); PUB=KEY.with_suffix('.pub')
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def atomic(p,v):
 t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--name',required=True); p.add_argument('--deadline-epoch',type=float,required=True); p.add_argument('--audit',type=Path,required=True); p.add_argument('--identity',type=Path,required=True); a=p.parse_args(); out=a.output_dir.resolve(); out.mkdir(parents=True, exist_ok=False); audit=json.loads(a.audit.read_text()); identity=json.loads(a.identity.read_text())
 checks={'durable_owner':bool(os.getenv('INVOCATION_ID')) and os.getenv('SYSTEMD_EXEC_PID')==str(os.getpid()),'audit_pass':audit.get('pass') is True,'identity_pass':identity.get('pass') is True,'inventory_empty':not list_items('instance') and not list_items('disk'),'keypair':KEY.is_file() and PUB.is_file(),'deadline':0<a.deadline_epoch-time.time()<=3900}
 atomic(out/'PRECREATE_TERMINAL.json',{'type':'typed_precreate','timestamp':now(),'checks':checks,'pass':all(checks.values())})
 if not all(checks.values()): return 1
 controller.PLATFORM='gpu-h200-sxm'; controller.PRESET='1gpu-16vcpu-200gb'; controller.DISK_GIB=100; controller.HOURLY_RATE_USD=2.45; controller.DISK_HOURLY_RATE_USD=.0097222
 atomic(PROJECT/'STATUS.json',{'status':'active','summary':'Durable pinned-image H200 actual-attention owner launched.','provider_mutation':'exclusive_durable_owner','authorized_spend_usd':1.5,'active_session':{'unit':os.getenv('SYSTEMD_UNIT'),'unit_manager':'systemd --user','owner_pid':os.getpid(),'name':a.name,'artifact_root':str(out),'deadline_epoch':a.deadline_epoch,'expected_terminal':'typed actual-attention rows or typed execution failure with authenticated cleanup'},'last_result_classification':'durable_actual_attention_owner_running','terminal_artifact':None})
 code=controller.run(out,a.name,KEY,PUB,hashlib.sha256((PROJECT/'PROJECT.md').read_bytes()).hexdigest(),PROJECT/'remote_attention_stage.sh',PROJECT/'attention_bench.py',(a.audit,a.identity), 'h200-c32-attention', min(1800,max(1,int(a.deadline_epoch-time.time()))),IMAGE)
 summary=json.loads((out/'summary.json').read_text()); atomic(PROJECT/'artifacts/SUMMARY.json',{'classification':'actual_attention_completed' if code==0 else 'actual_attention_typed_execution_terminal','controller_returncode':code,'controller_summary':summary,'completed_at_utc':now()}); atomic(PROJECT/'STATUS.json',{'status':'complete','summary':'actual attention owner terminal; reconcile artifacts','active_session':None,'terminal_artifact':str(PROJECT/'artifacts/SUMMARY.json'),'last_result_classification':'actual_attention_owner_terminal'})
 return code
if __name__=='__main__': raise SystemExit(main())
