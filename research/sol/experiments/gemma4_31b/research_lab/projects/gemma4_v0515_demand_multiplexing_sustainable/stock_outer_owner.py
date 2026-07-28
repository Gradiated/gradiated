#!/usr/bin/env python3
import datetime as dt, hashlib, json, os, pathlib, subprocess, sys, time
P=pathlib.Path(__file__).resolve().parent; L=P.parents[1]; F='/root/workspace/research/factory/src'; N='/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'; K='/root/.config/nebius/glm-campaign/ssh_ed25519'; H='/root/.config/nebius/glm-campaign/known_hosts'; B='h200-ngram-verifier-e00kcm9nfhwt7e7gbc'; R='/home/glmrunner/gemma4-stock-multiplex'; D=dt.datetime(2026,7,25,9,25,tzinfo=dt.timezone.utc); rate=2.46
def run(a,t=180): return subprocess.run(a,text=True,capture_output=True,timeout=t)
def atom(p,v): p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part');q.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');q.replace(p)
def pool(*x): return run(['python3','-m','grad_research.gpu_pool','--lab',str(L),*x],60)
def host():
 sys.path.insert(0,N); from placement_control import extract_public_ipv4,get_instance
 return extract_public_ipv4(get_instance('computeinstance-e00kcm9nfhwt7e7gbc'))
def ssh(ip,cmd,t=180): return run(['ssh','-i',K,'-o','BatchMode=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',f'glmrunner@{ip}',cmd],t)
def main():
 a=P/'artifacts'/('stock-multiplex-packet-id-repair-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%Sz'));a.mkdir(parents=True); began=time.time(); ip=host(); tar=P/'artifacts/packet-id-repair/stock_packet_complete.tar'; worker=P/'remote_stock_worker.sh'; owner=P/'OWNER_STATE_STOCK_REPAIR.json'; start_ticks=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]); status=json.loads((P/'STATUS.json').read_text()); status['active_session']={'unit':str(owner),'unit_manager':'pid','pid':os.getpid(),'start_ticks':start_ticks,'deadline_utc':'2026-07-25T09:25:00Z','artifact_root':str(a),'bench_id':B,'expected_terminal':'out/FINAL_TERMINAL.json'}; atom(P/'STATUS.json',status)
 try:
  ssh(ip,f'mkdir -p {R}');
  for src,dst in ((tar,'packet.tar'),(worker,'remote_stock_worker.sh')):
   want=hashlib.sha256(src.read_bytes()).hexdigest(); q=run(['scp','-p','-i',K,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',str(src),f'glmrunner@{ip}:{R}/{dst}.part'],900)
   (a/(dst+'.scp.log')).write_text(q.stdout+q.stderr)
   if q.returncode: raise RuntimeError('staging_scp')
   if ssh(ip,f"test \"$(sha256sum {R}/{dst}.part | cut -d' ' -f1)\" = {want} && mv {R}/{dst}.part {R}/{dst}").returncode: raise RuntimeError('staging_hash')
  if ssh(ip,f'cd {R} && rm -rf stock_packet out && mkdir stock_packet && tar -xf packet.tar -C stock_packet && test -f stock_packet/PACKET_ID.json && chmod 0555 remote_stock_worker.sh && STOCK_ROOT={R} nohup ./remote_stock_worker.sh > WORKER.log 2>&1 & echo $! > WORKER.pid').returncode: raise RuntimeError('worker_launch')
  while dt.datetime.now(dt.timezone.utc)<D:
   time.sleep(45); pool('heartbeat','--project','gemma4_v0515_demand_multiplexing_sustainable'); z=ssh(ip,f'cd {R}; test -f out/FINAL_TERMINAL.json && echo FINAL || true; cat out/INVOCATION_STATE.json 2>/dev/null || true',90); (a/'remote_state.log').write_text(z.stdout+z.stderr)
   if 'FINAL' in z.stdout: break
  q=run(['scp','-r','-p','-i',K,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',f'glmrunner@{ip}:{R}/out',str(a/'retrieved')],900); (a/'retrieve.log').write_text(q.stdout+q.stderr)
  terminal=json.loads((a/'retrieved'/'out'/'FINAL_TERMINAL.json').read_text()) if q.returncode==0 else {'result':'typed_retrieval_boundary','candidate_sample_consumed':None}
  spent=1.49+(time.time()-began)/3600*rate; status=json.loads((P/'STATUS.json').read_text()); status.update({'active_session':None,'actual_spend_usd':round(spent,6),'candidate_sample_consumed':bool(terminal.get('candidate_sample_consumed')),'summary':terminal['result'],'terminal':terminal,'status':'complete'});atom(P/'STATUS.json',status)
  content={'project':'gemma4_v0515_demand_multiplexing_sustainable','result':terminal['result'],'candidate_sample_consumed':terminal.get('candidate_sample_consumed'),'artifacts':str(a.relative_to(P)),'server_state':'Official stock v0.5.15 server gemma4-stock-multiplex remains loaded on port 30000; needs compatible successor or director disposition.'};atom(P/'BENCH_CONTENTS.json',content);pool('release','--project','gemma4_v0515_demand_multiplexing_sustainable','--condition','maintenance','--contents',str(P/'BENCH_CONTENTS.json'))
 except Exception as e:
  atom(a/'OWNER_EXCEPTION.json',{'error':repr(e)}); pool('release','--project','gemma4_v0515_demand_multiplexing_sustainable','--condition','maintenance','--contents',str(P/'BENCH_CONTENTS.json'))
if __name__=='__main__': main()
