#!/usr/bin/env python3
"""Atomic standby-first R2 transition bound to one predecessor PID identity."""
from __future__ import annotations
import argparse, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent; LAB=ROOT.parent.parent; PROJECT='gemma4_h200_m384_target_verify_attention_executor'; BENCH='h200-downproj-computeinstance-e00qft1sf416qp6knw'
sys.path.insert(0,str(ROOT.parents[6]/'factory'/'src'))
def ticks(pid:int): return Path(f'/proc/{pid}/stat').read_text().split()[21]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(f'.{p.name}.{os.getpid()}.tmp');t.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');json.loads(t.read_text());os.replace(t,p)
def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',required=True);a.add_argument('--artifact-root',required=True);a.add_argument('--claimed-at',required=True);a.add_argument('--predecessor-pid',type=int,required=True);a.add_argument('--predecessor-start-ticks',required=True);x=a.parse_args(); binding=ROOT/x.binding; art=(ROOT/x.artifact_root).resolve(); r2=art/'r2'; r2.mkdir(parents=True,exist_ok=True); state=r2/'CONTROLLER_OWNER_R2.json'; ready=r2/'OWNER_R2_STANDBY_READY.json'; activate=r2/'ACTIVATE_R2.json'
 # Binding, original claim and predecessor are read before R2 exists.
 if sha(binding)!='7a4ea4de37f69ebac45ee84f7890f05b56668a43877d696adc384a8e5ed723df': raise RuntimeError('recovery binding changed')
 show=subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),'show','--bench',BENCH],text=True,capture_output=True,check=True); row=json.loads(show.stdout)
 if row.get('claim',{}).get('claimed_at')!=x.claimed_at or row['claim'].get('project')!=PROJECT or ticks(x.predecessor_pid)!=x.predecessor_start_ticks: raise RuntimeError('claim or predecessor changed before standby')
 launch=[str(ROOT.parents[5]/'factory/tools/detached-owner'),'start','--unit-manager','pid','--state',str(state),'--log',str(r2/'CONTROLLER_OWNER_R2.log'),'--ready-file',str(ready),'--stabilize-seconds','5','--cwd',str(ROOT),'--',sys.executable,str(ROOT/'m384_attention_h200_owner_r2.py'),'--binding',x.binding,'--artifact-root',str(r2.relative_to(ROOT)),'--claimed-at',x.claimed_at,'--activate-file',str(activate)]
 subprocess.run(launch,text=True,capture_output=True,check=True)
 # Exact re-read after dynamic standby is the only authority to signal PID 726791.
 row=json.loads(subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),'show','--bench',BENCH],text=True,capture_output=True,check=True).stdout)
 if row.get('claim',{}).get('claimed_at')!=x.claimed_at or ticks(x.predecessor_pid)!=x.predecessor_start_ticks: raise RuntimeError('claim or predecessor changed after standby')
 os.kill(x.predecessor_pid,signal.SIGTERM)
 for _ in range(20):
  if not Path(f'/proc/{x.predecessor_pid}').exists(): break
  time.sleep(.25)
 if Path(f'/proc/{x.predecessor_pid}').exists(): raise RuntimeError('matching predecessor did not exit')
 atomic(activate,{'state':'activate','claimed_at':x.claimed_at,'binding_sha256':sha(binding),'predecessor_pid':x.predecessor_pid,'predecessor_start_ticks':x.predecessor_start_ticks})
 atomic(r2/'TRANSITION_COMPLETE.json',{'claimed_at':x.claimed_at,'predecessor_pid':x.predecessor_pid,'r2_state':str(state),'state':'r2_activated'})
 status=ROOT/'STATUS.json'; current=json.loads(status.read_text()); owner=json.loads(state.read_text()); current['active_session']={'artifact_root':str(art),'bench':BENCH,'claimed_at':x.claimed_at,'deadline_utc':'2026-07-30T10:49:00Z','forward_progress':'r2_activated_producer_capture_then_exact_component','pid':owner['pid'],'start_ticks':owner['start_ticks'],'unit':str(state),'unit_manager':'pid'};current['updated_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());atomic(status,current)
 return 0
if __name__=='__main__':raise SystemExit(main())
