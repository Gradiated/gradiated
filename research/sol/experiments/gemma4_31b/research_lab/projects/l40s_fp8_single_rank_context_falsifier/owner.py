#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, os, re, sys, time
from pathlib import Path
PROJECT=Path(__file__).resolve().parent
PREDECESSOR=PROJECT.parent/"l40s_online_fp8_actual_consumer_floor"
NEBIUS=Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0,str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name
IMAGE="docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY=Path("/root/.config/nebius/glm-campaign/ssh_ed25519"); PUBLIC_KEY=KEY.with_suffix(".pub")
RATE=0.8581222; DISK_RATE=0.0097222
BASE=(PREDECESSOR/"fp8_actual.py",PREDECESSOR/"w4_actual.py")
PRIMARY=(PROJECT/"fp8_single_rank.py",*BASE,PROJECT/"STAGED_MANIFEST.json")
CONDITIONAL=(PROJECT/"w4_single_rank.py",PROJECT/"fp8_single_rank.py",*BASE,PROJECT/"STAGED_MANIFEST.json")
def atomic(path,value):
    temp=path.with_suffix(path.suffix+".tmp"); temp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); os.replace(temp,path)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def trigger(primary,deadline,audit):
    result=primary.get("result") if isinstance(primary,dict) else None; gate=result.get("W4_RESIDUAL_TRIGGER") if isinstance(result,dict) else None
    return bool(primary.get("stage")=="primary" and primary.get("pass") is True and isinstance(gate,dict) and gate.get("pass") is True and deadline-time.time()>=600 and all(audit["remote_files"].get(p.name)==sha(p) for p in PRIMARY if p.name!="STAGED_MANIFEST.json"))
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output-dir",type=Path,required=True); parser.add_argument("--name",required=True); parser.add_argument("--deadline-epoch",type=float,required=True); parser.add_argument("--audit",type=Path,required=True); parser.add_argument("--identity",type=Path,required=True); args=parser.parse_args()
    audit=json.loads(args.audit.read_text()); identity=json.loads(args.identity.read_text()); output=args.output_dir.resolve(); output.mkdir(parents=True,exist_ok=False)
    instances=[metadata_name(x) for x in list_items("instance")]; disks=[metadata_name(x) for x in list_items("disk")]
    checks={"durable_owner":bool(os.getenv("INVOCATION_ID")) and os.getenv("SYSTEMD_EXEC_PID")==str(os.getpid()),"name":bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",args.name)),"identity":identity.get("pass") is True,"audit":audit.get("pass") is True,"inputs":all(x.is_file() for x in PRIMARY+CONDITIONAL+(PROJECT/"remote_stage.sh",)),"inventory_empty":not instances and not disks,"keys":KEY.is_file() and PUBLIC_KEY.is_file(),"budget":(RATE+DISK_RATE)*1980/3600<=0.54,"deadline":0<args.deadline_epoch-time.time()<=1980}
    atomic(output/"PRECREATE_TERMINAL.json",{"schema_version":1,"type":"l40s_single_rank_typed_precreate","checks":checks,"inventory":{"instances":instances,"disks":disks},"pass":all(checks.values())})
    if not all(checks.values()): return 1
    controller.PLATFORM="gpu-l40s-a"; controller.PRESET="1gpu-8vcpu-32gb"; controller.DISK_GIB=100; controller.HOURLY_RATE_USD=RATE; controller.DISK_HOURLY_RATE_USD=DISK_RATE
    atomic(PROJECT/"STATUS.json",{"status":"active","priority":225,"summary":"One durable owner holds the L40S through sentinel-first FP8 and strictly conditional W4.","provider_mutation":"exclusive_durable_owner","authorized_spend_usd":0.54,"wall_clock_budget_minutes":45,"provider_exposure_budget_minutes":33,"compute_budget":"0.56 L40S GPU-hours and 3 local CPU-hours","storage_budget":"one 100 GiB disk","active_session":{"unit":os.getenv("SYSTEMD_UNIT"),"unit_manager":"systemd --user","owner_pid":os.getpid(),"name":args.name,"artifact_root":str(output),"deadline_epoch":args.deadline_epoch,"expected_terminal":"typed sentinel/full FP8 terminal, optional typed W4 terminal, and authenticated cleanup"},"last_result_classification":"durable_l40s_single_rank_owner_running","terminal_artifact":None})
    code=controller.run(output,args.name,KEY,PUBLIC_KEY,sha(PROJECT/"PROJECT.md"),PROJECT/"remote_stage.sh",PROJECT/"fp8_single_rank.py",PRIMARY,"l40s-single-rank",max(1,int(args.deadline_epoch-time.time())),IMAGE,PROJECT/"remote_stage.sh",PROJECT/"w4_single_rank.py",CONDITIONAL,"l40s-single-rank-w4",lambda primary:trigger(primary,args.deadline_epoch,audit))
    summary=json.loads((output/"summary.json").read_text()) if (output/"summary.json").exists() else {"outcome":"controller_observability_failure"}
    atomic(PROJECT/"artifacts/SUMMARY.json",{"classification":"l40s_fp8_single_rank_context_terminal","controller_returncode":code,"controller_summary":summary,"completed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")})
    atomic(PROJECT/"STATUS.json",{"status":"complete","priority":225,"summary":"Durable L40S owner reached terminal; reconcile typed artifacts.","next_action":"Reconcile terminal artifacts and inventory.","active_session":None,"terminal_artifact":str(PROJECT/"artifacts/SUMMARY.json"),"last_result_classification":"l40s_fp8_single_rank_context_terminal"})
    return code
if __name__=="__main__": raise SystemExit(main())
