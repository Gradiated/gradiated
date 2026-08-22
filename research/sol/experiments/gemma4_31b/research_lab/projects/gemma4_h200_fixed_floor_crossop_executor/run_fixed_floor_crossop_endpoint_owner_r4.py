#!/usr/bin/env python3
"""R4 retained owner: stage once, run candidate-only, retrieve or repair in place."""
import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, threading, time
P=pathlib.Path(__file__).resolve().parent; LAB=P.parents[1]; ENV={**os.environ,'PYTHONPATH':'/root/workspace/research/factory/src'}; REPAIR='/root/workspace/research/factory/tools/repair-handshake'
def now(): return dt.datetime.now(dt.UTC)
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); q.replace(p)
def call(x,t=60): return subprocess.run(x,text=True,capture_output=True,check=False,timeout=t,env=ENV)
def left(d,reserve=0): return max(1,int((d-now()).total_seconds())-reserve)
def main():
 a=argparse.ArgumentParser(); a.add_argument('--binding',type=pathlib.Path,required=True); a.add_argument('--owner-state',type=pathlib.Path,required=True); a.add_argument('--artifact-root',type=pathlib.Path,required=True); z=a.parse_args(); b=json.loads(z.binding.read_text()); d=dt.datetime.fromisoformat(b['absolute_release_deadline_utc'].replace('Z','+00:00')); root=z.artifact_root; root.mkdir(parents=True,exist_ok=True)
 packet=json.loads((P/'ENDPOINT_INTEGRATION_PACKET_R4.json').read_text())
 if sha(P/'ENDPOINT_INTEGRATION_PACKET_R4.json')!=b['packet_sha256']: raise RuntimeError('packet_hash')
 for n,h in packet['files'].items():
  if sha(P/n)!=h: raise RuntimeError('packet_member_hash:'+n)
 stop=threading.Event()
 def beat():
  while not stop.wait(35):
   r=call(['python3','-m','grad_research.gpu_pool','--lab',str(LAB),'heartbeat','--project',b['project']],30); put(root/'HEARTBEAT.json',{'at_utc':now().isoformat(),'rc':r.returncode,'stderr':r.stderr[-400:]})
 threading.Thread(target=beat,daemon=True).start()
 terminal=None
 try:
  inv=json.loads(call(['python3','-m','grad_research.gpu_pool','--lab',str(LAB),'show','--bench',b['bench_id']],30).stdout); r=inv['resource']
  if inv.get('claim',{}).get('claimed_at')!=b['predecessor']['claimed_at'] or r['gpu_uuid']!=b['gpu_uuid'] or r['ssh_ed25519_fingerprint']!=b['ssh_fingerprint'] or inv['lifecycle']['watchdog']['main_pid']!=b['watchdog_main_pid']: raise RuntimeError('same_claim_identity_mismatch')
  key=r['ssh_identity_path']; known=r['known_hosts_namespace']; host=r['ssh_user']+'@'+r['public_ipv4']; ssh=['ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+known,host]; remote='/home/glmrunner/fixed-floor-crossop-endpoint-r4'; files=list(packet['files']); archive=root/'packet.tar'; subprocess.run(['tar','-cf',str(archive),'-C',str(P),*files],check=True,timeout=120)
  made=call(ssh+[f'mkdir -p {remote}/project {remote}/artifacts'],left(d,300))
  if made.returncode: raise RuntimeError('remote_root:'+made.stderr[-300:])
  cp=call(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+known,str(archive),host+':'+remote+'/packet.tar.part'],left(d,300));
  if cp.returncode: raise RuntimeError('packet_stage:'+cp.stderr[-300:])
  un=call(ssh+[f'mkdir -p {remote}/project {remote}/artifacts && tar -xf {remote}/packet.tar.part -C {remote}/project && mv {remote}/packet.tar.part {remote}/packet.tar'],left(d,260));
  if un.returncode: raise RuntimeError('packet_unpack:'+un.stderr[-300:])
  control=remote+'/control'; # immutable control is already retrieved locally; stage only its oracle, never its request inputs
  oracle=root/'CONTROL_EMITTED_CHUNK_ORACLE.json'; local_control=P/'artifacts/fixed-floor-crossop-endpoint-r3-candidate-only-20260730t0503z-preflight/control'; subprocess.run(['python3',str(P/'fixed_floor_crossop_control_chunk_oracle.py'),'--control-root',str(local_control),'--terminal-sha256',b['control_terminal_sha256'],'--output',str(oracle)],check=True,timeout=90); cp=call(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+known,str(oracle),host+':'+remote+'/CONTROL_EMITTED_CHUNK_ORACLE.json'],left(d,220));
  if cp.returncode: raise RuntimeError('oracle_stage:'+cp.stderr[-300:])
  gen=0
  while now()<d:
   output=remote+'/artifacts/candidate-r4-g'+str(gen); put(root/'PROGRESS.json',{'phase':'candidate_only','generation':gen,'output':output,'at_utc':now().isoformat()})
   w=call(ssh+[f'python3 {remote}/project/run_fixed_floor_crossop_endpoint_candidate_only_r4.py --project {remote}/project --checkpoint {b["checkpoint_path"]} --oracle {remote}/CONTROL_EMITTED_CHUNK_ORACLE.json --output {output}'],left(d,120)); (root/f'worker-g{gen}.stdout').write_text(w.stdout); (root/f'worker-g{gen}.stderr').write_text(w.stderr)
   local=root/f'PAIR_TERMINAL-g{gen}.json'; got=call(['scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+known,host+':'+output+'/PAIR_TERMINAL.json',str(local)],left(d,90))
   if w.returncode==0 and got.returncode==0:
    pair=json.loads(local.read_text()); terminal={'classification':'decision_bearing_candidate_only_endpoint','science_consumed':True,'pair_sha256':sha(local),'pair':pair}; put(root/'PAIR_TERMINAL.json',terminal); break
   diag=root/f'RECOVERABLE_DIAGNOSTIC-g{gen}.json'; put(diag,{'scope':'candidate_only','worker_rc':w.returncode,'worker_stderr':w.stderr[-1200:],'terminal_retrieval_rc':got.returncode,'terminal_retrieval_stderr':got.stderr[-600:],'candidate_output':output,'at_utc':now().isoformat()}); rid='endpoint-r4-'+str(gen)+'-'+str(int(time.time())); ready=call([REPAIR,'ready','--root',str(root),'--repair-id',rid,'--deadline',d.isoformat(),'--failure-kind','candidate_only_recoverable','--diagnostic',sha(diag),'--retry-scope','candidate_only'],30); put(root/'PROGRESS.json',{'phase':'repair_wait','repair_id':rid,'at_utc':now().isoformat()})
   if ready.returncode: raise RuntimeError('repair_ready:'+ready.stderr[-300:])
   wait=call([REPAIR,'wait','--root',str(root),'--repair-id',rid,'--deadline',d.isoformat()],left(d)); state=json.loads(wait.stdout).get('state') if wait.returncode==0 else 'expired'
   if state!='requested': terminal={'classification':'repair_deadline_boundary','science_consumed':False,'diagnostic':str(diag)}; break
   req=root/'.repair-handshakes'/rid/'REPAIR_REQUEST.json'; consumed=req.with_name('REPAIR_REQUEST.'+sha(req)+'.consumed.json'); req.replace(consumed); gen+=1
  if terminal is None: terminal={'classification':'absolute_deadline_boundary','science_consumed':False}
 finally:
  put(root/'TERMINAL.json',terminal or {'classification':'unknown'}); stop.set()
if __name__=='__main__': main()
