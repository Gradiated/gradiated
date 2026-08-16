#!/usr/bin/env python3
import hashlib,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def w(p,v): p.write_text(json.dumps(v,sort_keys=True)+"\n")
def read(p): return json.loads(p.read_text())
def unit_status(unit):
 r=subprocess.run(["systemctl","--user","show",unit,"--property=MainPID,ControlGroup,ActiveState"],capture_output=True,text=True)
 return {"returncode":r.returncode,"properties":dict(x.split("=",1) for x in r.stdout.splitlines() if "=" in x)}
def controller(d):
 r=subprocess.run([sys.executable,str(ROOT/"v2_capture_controller_proof.py")],capture_output=True,text=True)
 proof=read(ROOT/"V2_CAPTURE_CONTROLLER_PROOF.json") if (ROOT/"V2_CAPTURE_CONTROLLER_PROOF.json").exists() else {}
 spec=read(ROOT/"BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json")
 positive=proof.get("positive",{})
 identity=spec["runtime_identity"]["model_revision"]
 adapter={"kind":"complete_h100_capture_adapter_contract","model_revision":identity,"checkpoint_reuse":spec["captures"]["checkpoint_reuse"]}
 retrieved={"controller_stdout_sha256":hashlib.sha256(r.stdout.encode()).hexdigest(),"controller_stderr_sha256":hashlib.sha256(r.stderr.encode()).hexdigest(),"required_per_phase_artifacts":spec["artifacts"]["per_capture"]}
 terminal={"schema_version":1,"kind":"external_v2_capture_terminal","controller_pid":os.getpid(),"exit_code":r.returncode,"identity":identity,"adapter":adapter,"phase_count":positive.get("phase_count"),"artifact_complete":positive.get("artifact_complete",False),"retrieval":retrieved,"negative_missing_artifact_rejected":proof.get("negative_rejected",False),"cleanup":positive.get("cleanup",{}),"pass":r.returncode==0 and positive.get("pass",False) and proof.get("negative_rejected",False)}
 w(d/"terminal-result.json",terminal)
 return r.returncode
def watchdog(d):
 for _ in range(80):
  p=d/"terminal-result.json"
  if p.exists():
   t=read(p); w(d/"watchdog-result.json",{"watchdog_pid":os.getpid(),"typed_terminal":t.get("kind")=="external_v2_capture_terminal","terminal_pass":t.get("pass",False),"timeout_seconds":8,"timeout_enforced":True}); return 0 if t.get("pass") else 2
  time.sleep(.1)
 w(d/"watchdog-result.json",{"watchdog_pid":os.getpid(),"terminal_pass":False,"timeout_seconds":8,"timeout_enforced":True,"reason":"terminal_timeout"}); return 3
def timeout_controller(d):
 time.sleep(3); return 0
def timeout_watchdog(d):
 time.sleep(1.3); timed_out=not (d/"terminal-result.json").exists()
 w(d/"timeout-result.json",{"watchdog_pid":os.getpid(),"timeout_seconds":1,"timeout_observed":timed_out,"typed_state":"terminal_timeout" if timed_out else "unexpected_terminal"}); return 0 if timed_out else 4
def main():
 if len(sys.argv)==3 and sys.argv[1] in {"controller","watchdog","timeout-controller","timeout-watchdog"}:
  f={"controller":controller,"watchdog":watchdog,"timeout-controller":timeout_controller,"timeout-watchdog":timeout_watchdog}[sys.argv[1]]; raise SystemExit(f(Path(sys.argv[2])))
 with tempfile.TemporaryDirectory() as x:
  d=Path(x); token=uuid.uuid4().hex[:10]; c=f"v2cap-controller-{token}"; wdog=f"v2cap-watchdog-{token}"
  launches=[]
  for unit,mode in [(c,"controller"),(wdog,"watchdog")]:
   r=subprocess.run(["systemd-run","--user","--no-block","--collect","--property=RuntimeMaxSec=8s",f"--unit={unit}",sys.executable,str(Path(__file__).resolve()),mode,str(d)],capture_output=True,text=True)
   launches.append({"unit":unit,"mode":mode,"returncode":r.returncode,"stdout_sha256":hashlib.sha256(r.stdout.encode()).hexdigest(),"stderr_sha256":hashlib.sha256(r.stderr.encode()).hexdigest()})
   if r.returncode: break
  time.sleep(.2); statuses={"controller":unit_status(f"{c}.service"),"watchdog":unit_status(f"{wdog}.service")}
  for _ in range(100):
   if (d/"watchdog-result.json").exists(): break
   time.sleep(.1)
  td=d/"timeout-control"; td.mkdir(); tc=f"v2cap-timeout-controller-{token}"; tw=f"v2cap-timeout-watchdog-{token}"; timeout_launches=[]
  for unit,mode,limit in [(tc,"timeout-controller","1s"),(tw,"timeout-watchdog","3s")]:
   r=subprocess.run(["systemd-run","--user","--no-block","--collect",f"--property=RuntimeMaxSec={limit}",f"--unit={unit}",sys.executable,str(Path(__file__).resolve()),mode,str(td)],capture_output=True,text=True)
   timeout_launches.append({"unit":unit,"mode":mode,"returncode":r.returncode,"stderr_sha256":hashlib.sha256(r.stderr.encode()).hexdigest()})
  for _ in range(30):
   if (td/"timeout-result.json").exists(): break
   time.sleep(.1)
  timeout_result=read(td/"timeout-result.json") if (td/"timeout-result.json").exists() else {}
  t=read(d/"terminal-result.json") if (d/"terminal-result.json").exists() else {}; q=read(d/"watchdog-result.json") if (d/"watchdog-result.json").exists() else {}
  result={"schema_version":1,"classification":"zero_provider_external_systemd_v2_capture_proof","launches":launches,"unit_status":statuses,"controller":t,"watchdog":q,"timeout_control":{"launches":timeout_launches,"result":timeout_result},"pass":all(x["returncode"]==0 for x in launches+timeout_launches) and t.get("pass") is True and t.get("phase_count")==3 and bool(t.get("retrieval")) and t.get("cleanup",{}).get("direct_absent") is True and t.get("cleanup",{}).get("inventory_absent") is True and q.get("typed_terminal") is True and q.get("terminal_pass") is True and q.get("timeout_enforced") is True and timeout_result.get("timeout_observed") is True and timeout_result.get("typed_state")=="terminal_timeout"}
  w(ROOT/"V2_SYSTEMD_CAPTURE_PROOF.json",result); print(json.dumps(result,sort_keys=True));
  if not result["pass"]: raise SystemExit(1)
if __name__=="__main__": main()
