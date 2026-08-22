#!/usr/bin/env python3
import hashlib,json,os,shlex,subprocess,sys,tempfile,threading,time
from pathlib import Path
R=Path(__file__).resolve().parent; LAB=R.parents[1]; P='gemma4_hybrid_attention_placement_codesign'; B=R/'DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_WORKLOAD_MATERIALIZATION_REPAIR_20260729T0221Z.json'; E=R/'DIRECTOR_H200_55L5G_ENDPOINT_EXECUTION_20260729T0047Z.json'; A=R/'artifacts/h200-55l5g-endpoint-workload-materialization-repair-20260729t0221z'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atom(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);f=tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False);json.dump(x,f,sort_keys=True);f.write('\n');f.close();Path(f.name).replace(p)
def pool(*x):return subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*x],text=True,capture_output=True,env={**os.environ,'PYTHONPATH':str(R.parents[5]/'factory'/'src')})
def run(c,t,n):
 try:r=subprocess.run(c,text=True,capture_output=True,timeout=t)
 except subprocess.TimeoutExpired as e:r=subprocess.CompletedProcess(c,124,e.stdout or '',e.stderr or 'timeout')
 atom(A/'commands'/f'{n}.json',{'argv':c,'returncode':r.returncode,'stdout':r.stdout[-20000:],'stderr':r.stderr[-20000:]});return r
def main():
 b,e=load(B),load(E);assert sha(B)=='36b5b4a4359702f838b2fd2d4ebea52686076daf97de8e6cac48a9d239b40344';assert sha(R/'qualified_c32_request_payloads.json')=='60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c'
 shown=pool('show','--bench',b['live_claim']['bench_id']);bench=json.loads(shown.stdout);claim=bench['claim'];assert claim['project']==P and claim['claimed_at']==b['live_claim']['expected_claimed_at_utc'];assert not pool('heartbeat','--project',P,'--bench',bench['id']).returncode
 A.mkdir(parents=True,exist_ok=True);x=bench['resource'];host=x['ssh_user']+'@'+x['public_ipv4'];o=['-i',x['identity_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+x['known_hosts_namespace']];ssh=['/usr/bin/ssh',*o,host];scp=['/usr/bin/scp',*o];remote=e['runtime_destinations']['remote_root'];packet=remote+'/packet';state=os.environ.get('DETACHED_OWNER_STATE',str(A.parent/(A.name+'-controller')/'OWNER_STATE.json'))
 s=load(R/'STATUS.json');s['active_session']={'artifact_root':str(A),'bench_id':bench['id'],'expected_claimed_at_utc':claim['claimed_at'],'deadline_utc':b['lifecycle']['owner_deadline_utc'],'expected_terminal':'HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json','forward_progress':'materialized exact workload; stock adapter then candidate','unit':state,'pid':os.getpid(),'start_ticks':int(Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(') ',1)[1].split()[19]),'unit_manager':'pid'};atom(R/'STATUS.json',s)
 stop=threading.Event();threading.Thread(target=lambda: [pool('heartbeat','--project',P,'--bench',bench['id']) for _ in iter(lambda:not stop.wait(35),False)],daemon=True).start()
 try:
  for f in ('h200_55l5g_exact_workload_adapter.py','qualified_c32_request_payloads.json'):
   q=run([*scp,str(R/f),f'{host}:{packet}/{f}.part'],120,'copy_'+f);z=run([*ssh,f"test $(sha256sum {shlex.quote(packet+'/'+f+'.part')}|awk '{{print $1}}') = {sha(R/f)} && mv {shlex.quote(packet+'/'+f+'.part')} {shlex.quote(packet+'/'+f)}"],30,'finalize_'+f)
   if q.returncode or z.returncode:raise RuntimeError('remote_copy_failed')
  base=['sudo','-n','docker','exec','-w','/work','hybrid-55l5g','python3','/work/h200_55l5g_exact_workload_adapter.py','--pair','/work/run_h200_55l5g_endpoint_pair.py','--payloads','/work/qualified_c32_request_payloads.json','--identity','/work/qualified_c32_workload.json','--out','/work/materialized-stock-0221-r1']
  smoke=run([*ssh,shlex.join(base+['--smoke'])],120,'smoke');
  if smoke.returncode:raise RuntimeError('smoke_failed')
  stock=run([*ssh,shlex.join(base+['--arm','stock','--url','http://127.0.0.1:30000'])],1800,'stock')
  got=run([*ssh,'sudo -n cat '+shlex.quote(packet+'/materialized-stock-0221/STOCK_ARM.json')],60,'stock_retrieve')
  if stock.returncode or got.returncode:raise RuntimeError('stock_failed_or_unknown')
  result=json.loads(got.stdout);atom(A/'STOCK_ARM.json',result)
  if result.get('complete_requests')!=32 or result.get('failures')!=0:raise RuntimeError('invalid_stock')
  atom(A/'REPAIR_READY.json',{'classification':'candidate_transition_required','science_consumed':True,'stock_terminal':str(A/'STOCK_ARM.json'),'repair_deadline_utc':b['lifecycle']['owner_deadline_utc']});return 72
 except Exception as ex: atom(A/'REPAIR_READY.json',{'classification':'recoverable_pre_science','science_consumed':False,'exception':repr(ex),'repair_deadline_utc':b['lifecycle']['owner_deadline_utc']});return 72
 finally:stop.set()
if __name__=='__main__':raise SystemExit(main())
