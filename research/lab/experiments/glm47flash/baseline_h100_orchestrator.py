import base64,datetime,hashlib,json,os,pathlib,subprocess,time,urllib.error,urllib.request
ROOT=pathlib.Path('/root/workspace/research/lab/experiments/glm47flash'); LEDGER=ROOT/'ledger.jsonl'; ATTEMPT=os.environ.get('ATTEMPT_NO','16'); RESULT=ROOT/f'attempt{ATTEMPT}-orchestrator.json'; SCRIPT=ROOT/'baseline_h100_cuda13.sh'; IMAGE='lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af'; GPU='NVIDIA H100 80GB HBM3'; PRIOR=float(os.environ.get('PRIOR_SPEND_USD','3.601873757533205')); CAP=12.0; STARTUP=300; DEADLINE=3600
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def api(path,method='GET',payload=None,timeout=60):
 h={'Authorization':'Bearer '+os.environ['RUNPOD_API_KEY']}; data=None
 if payload is not None: h['Content-Type']='application/json'; data=json.dumps(payload).encode()
 q=urllib.request.Request('https://rest.runpod.io/v1'+path,data=data,headers=h,method=method)
 with urllib.request.urlopen(q,timeout=timeout) as r: b=r.read(); return r.status,json.loads(b) if b else None
def append(x):
 with LEDGER.open('a') as f:f.write(json.dumps(x,separators=(',',':'))+'\n')
def fetch(url,path):
 with urllib.request.urlopen(url,timeout=180) as r,path.open('wb') as f:
  while c:=r.read(8*1024*1024): f.write(c)
def main():
 begun=time.monotonic(); pod_id=None; record={'attempt':f'attempt{ATTEMPT}_bf16_baseline','started_at':utc(),'image':IMAGE,'source_commit':'f63458b5beaceabbd9d749b9fc956370e1b649e6','model_revision':'75fce70','prior_spend_usd':PRIOR,'cap_usd':CAP,'events':[]}
 try:
  _,pods=api('/pods'); active=[p.get('id') for p in pods if p.get('desiredStatus') in ('RUNNING','CREATED','RESTARTING')]
  if active: raise RuntimeError('active pods prevent mutation: '+json.dumps(active))
  if PRIOR>=CAP: raise RuntimeError('cap exhausted')
  cmd='export CAMPAIGN_DEADLINE_EPOCH=$(( $(date +%s)+3300 )); printf %s "$SCRIPT_B64" | base64 -d > /tmp/run.sh; chmod +x /tmp/run.sh; timeout --signal=TERM 3400 /tmp/run.sh'
  payload={'name':f'glm47flash-h100-bf16-baseline-a{ATTEMPT}-20260713','imageName':IMAGE,'computeType':'GPU','gpuTypeIds':[GPU],'gpuTypePriority':'availability','gpuCount':1,'cloudType':'SECURE','containerDiskInGb':40,'volumeInGb':100,'volumeMountPath':'/workspace','ports':['8000/tcp'],'dockerEntrypoint':['/bin/bash','-lc'],'dockerStartCmd':[cmd],'env':{'SCRIPT_B64':base64.b64encode(SCRIPT.read_bytes()).decode()}}
  _,pod=api('/pods','POST',payload,120); pod_id=pod['id']; rate=float(pod.get('costPerHr',2.99)); record.update({'pod_id':pod_id,'hourly_rate_usd':rate,'provider_created_at':pod.get('createdAt')}); record['events'].append({'at':utc(),'event':'pod_created'}); append({'timestamp':utc(),'event':'pod_created',**record})
  cancel=str(ROOT/f'.watchdog-{pod_id}.cancel'); pathlib.Path(cancel).unlink(missing_ok=True); subprocess.Popen(['python3',str(ROOT/'runpod_watchdog.py'),pod_id,str(time.time()+DEADLINE),cancel,str(ROOT/f'attempt{ATTEMPT}-watchdog.jsonl')],start_new_session=True)
  endpoint=None; end=time.monotonic()+STARTUP
  while time.monotonic()<end:
   _,s=api('/pods/'+pod_id,timeout=30); m=s.get('portMappings') or {}; port=m.get('8000') or m.get(8000)
   if s.get('desiredStatus') not in ('RUNNING','CREATED','RESTARTING'): raise RuntimeError('provider terminal '+str(s.get('desiredStatus')))
   if s.get('publicIp') and port: endpoint=f"http://{s['publicIp']}:{port}"; record['events'].append({'at':utc(),'event':'artifact_endpoint_ready'}); break
   time.sleep(5)
  if not endpoint: raise TimeoutError('five-minute startup deadline exceeded')
  terminal=None; end=time.monotonic()+DEADLINE-STARTUP
  while time.monotonic()<end:
   try:
    with urllib.request.urlopen(endpoint+'/STATUS',timeout=10) as r: status=r.read().decode().strip()
    if status in ('READY','FAILED'): terminal=status; break
   except (urllib.error.URLError,TimeoutError): pass
   _,s=api('/pods/'+pod_id,timeout=30)
   if s.get('desiredStatus') not in ('RUNNING','CREATED','RESTARTING'): raise RuntimeError('pod terminated before artifact')
   time.sleep(10)
  if terminal not in ('READY','FAILED'): raise TimeoutError('baseline deadline exceeded')
  a=ROOT/f'attempt{ATTEMPT}-baseline.tar.gz'; c=ROOT/f'attempt{ATTEMPT}-baseline.tar.gz.sha256.remote'; fetch(endpoint+'/glm-baseline.tar.gz',a); fetch(endpoint+'/glm-baseline.tar.gz.sha256',c); local=hashlib.sha256(a.read_bytes()).hexdigest(); remote=c.read_text().split()[0]
  if local!=remote: raise ValueError('checksum mismatch')
  record.update({'terminal_status':terminal,'artifact':{'path':str(a),'bytes':a.stat().st_size,'sha256':local}}); record['events'].append({'at':utc(),'event':'artifact_verified','terminal_status':terminal})
  if terminal!='READY': record['error']='remote FAILED'
 except Exception as e: record['error']=repr(e); record['events'].append({'at':utc(),'event':'attempt_failed','error':repr(e)})
 finally:
  ds=None; verify='not_created'
  if pod_id:
   try: ds,_=api('/pods/'+pod_id,'DELETE',timeout=30)
   except urllib.error.HTTPError as e: ds=e.code
   try: api('/pods/'+pod_id); verify='present'
   except urllib.error.HTTPError as e: verify=f'http_{e.code}'
   pathlib.Path(ROOT/f'.watchdog-{pod_id}.cancel').touch()
  elapsed=time.monotonic()-begun; record.update({'finished_at':utc(),'allocation_seconds':elapsed,'conservative_spend_usd':elapsed*float(record.get('hourly_rate_usd',0))/3600,'teardown':{'delete_http_status':ds,'verification':verify}}); RESULT.write_text(json.dumps(record,indent=2)+'\n'); append({'timestamp':utc(),'event':'attempt_finished',**record}); print(json.dumps(record,indent=2),flush=True)
 return 0 if record.get('terminal_status')=='READY' and record.get('teardown',{}).get('verification')=='http_404' else 1
if __name__=='__main__': raise SystemExit(main())
