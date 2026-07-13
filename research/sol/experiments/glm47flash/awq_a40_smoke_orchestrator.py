import base64,datetime,hashlib,json,os,pathlib,subprocess,time,urllib.error,urllib.request
R=pathlib.Path('/root/workspace/research/sol/experiments/glm47flash'); L=R/'ledger.jsonl'; IMAGE='lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af'; PRIOR=3.57688446353128; CAP=12.; START=300; DEAD=2400
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def api(path,method='GET',payload=None,timeout=60):
 h={'Authorization':'Bearer '+os.environ['RUNPOD_API_KEY']}; d=None
 if payload is not None:h['Content-Type']='application/json';d=json.dumps(payload).encode()
 q=urllib.request.Request('https://rest.runpod.io/v1'+path,data=d,headers=h,method=method)
 with urllib.request.urlopen(q,timeout=timeout) as x:b=x.read();return x.status,json.loads(b) if b else None
def log(x):
 with L.open('a') as f:f.write(json.dumps(x,separators=(',',':'))+'\n')
def fetch(u,p):
 with urllib.request.urlopen(u,timeout=180) as x,p.open('wb') as f:
  while c:=x.read(8*1024*1024):f.write(c)
def main():
 t=time.monotonic();pid=None;rec={'attempt':'attempt15_a6000_awq_extended_hotfix','started_at':utc(),'image':IMAGE,'model':'cyankiwi/GLM-4.7-Flash-AWQ-4bit','model_revision':'ab31d12','quantization':'compressed-tensors','shared_experts_fusion':False,'runtime_hotfix':'three hasattr weight guards in MLA initialization','hardware_role':'A40-path capacity proxy; not an A40 measurement','prior_spend_usd':PRIOR,'cap_usd':CAP,'events':[]}
 try:
  _,ps=api('/pods');a=[p.get('id') for p in ps if p.get('desiredStatus') in ('RUNNING','CREATED','RESTARTING')]
  if a:raise RuntimeError('active pods '+json.dumps(a))
  cmd='export CAMPAIGN_DEADLINE_EPOCH=$(( $(date +%s)+2100 )); printf %s "$SCRIPT"|base64 -d >/tmp/run.sh;chmod +x /tmp/run.sh;timeout --signal=TERM 2200 /tmp/run.sh'
  pay={'name':'glm47flash-a6000-awq-extended-hotfix-20260713','imageName':IMAGE,'computeType':'GPU','gpuTypeIds':['NVIDIA RTX A6000'],'gpuTypePriority':'availability','gpuCount':1,'cloudType':'COMMUNITY','supportPublicIp':True,'containerDiskInGb':30,'volumeInGb':50,'volumeMountPath':'/workspace','ports':['8000/tcp'],'dockerEntrypoint':['/bin/bash','-lc'],'dockerStartCmd':[cmd],'env':{'SCRIPT':base64.b64encode((R/'awq_a40_smoke.sh').read_bytes()).decode()}}
  _,p=api('/pods','POST',pay,120);pid=p['id'];rate=float(p.get('costPerHr',.44));rec.update({'pod_id':pid,'hourly_rate_usd':rate});rec['events'].append({'at':utc(),'event':'pod_created'});log({'timestamp':utc(),'event':'pod_created',**rec})
  cancel=str(R/f'.watchdog-{pid}.cancel');pathlib.Path(cancel).unlink(missing_ok=True);subprocess.Popen(['python3',str(R/'runpod_watchdog.py'),pid,str(time.time()+DEAD),cancel,str(R/'attempt15-watchdog.jsonl')],start_new_session=True)
  ep=None;end=time.monotonic()+START
  while time.monotonic()<end:
   _,s=api('/pods/'+pid);m=s.get('portMappings') or {};port=m.get('8000') or m.get(8000)
   if s.get('publicIp') and port:ep=f"http://{s['publicIp']}:{port}";break
   time.sleep(5)
  if not ep:raise TimeoutError('five-minute startup deadline exceeded')
  terminal=None;end=time.monotonic()+DEAD-START
  while time.monotonic()<end:
   try:
    with urllib.request.urlopen(ep+'/STATUS',timeout=10) as x:st=x.read().decode().strip()
    if st in ('READY','FAILED'):terminal=st;break
   except (urllib.error.URLError,TimeoutError):pass
   time.sleep(10)
  if not terminal:raise TimeoutError('experiment deadline')
  a=R/'attempt15-awq-smoke.tar.gz';c=R/'attempt15-awq-smoke.tar.gz.sha256.remote';fetch(ep+'/awq-smoke.tar.gz',a);fetch(ep+'/awq-smoke.tar.gz.sha256',c);lh=hashlib.sha256(a.read_bytes()).hexdigest();rh=c.read_text().split()[0]
  if lh!=rh:raise ValueError('checksum')
  rec.update({'terminal_status':terminal,'artifact':{'path':str(a),'bytes':a.stat().st_size,'sha256':lh}})
 except Exception as e:rec['error']=repr(e)
 finally:
  ds=None;v='not_created'
  if pid:
   try:ds,_=api('/pods/'+pid,'DELETE')
   except urllib.error.HTTPError as e:ds=e.code
   try:api('/pods/'+pid);v='present'
   except urllib.error.HTTPError as e:v=f'http_{e.code}'
   pathlib.Path(R/f'.watchdog-{pid}.cancel').touch()
  elapsed=time.monotonic()-t;rec.update({'finished_at':utc(),'allocation_seconds':elapsed,'conservative_spend_usd':elapsed*float(rec.get('hourly_rate_usd',0))/3600,'teardown':{'delete_http_status':ds,'verification':v}});(R/'attempt15-orchestrator.json').write_text(json.dumps(rec,indent=2)+'\n');log({'timestamp':utc(),'event':'attempt_finished',**rec});print(json.dumps(rec,indent=2))
 return 0 if rec.get('terminal_status')=='READY' and rec['teardown']['verification']=='http_404' else 1
if __name__=='__main__':raise SystemExit(main())
