import base64,datetime,hashlib,json,os,pathlib,subprocess,time,urllib.error,urllib.request

ROOT=pathlib.Path('/root/workspace/research/sol/experiments/glm47flash')
LEDGER=ROOT/'ledger.jsonl'
RESULT=ROOT/'attempt4-orchestrator.json'
SCRIPT=ROOT/'smoke_h100_cuda13.sh'
IMAGE='lmsysorg/sglang@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af'
GPU='NVIDIA H100 80GB HBM3'
PRIOR_SPEND=2.072
CAP=12.0
STARTUP_DEADLINE=300
EXPERIMENT_DEADLINE=2400

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def api(path,method='GET',payload=None,timeout=60):
    h={'Authorization':'Bearer '+os.environ['RUNPOD_API_KEY']}; data=None
    if payload is not None: h['Content-Type']='application/json'; data=json.dumps(payload).encode()
    req=urllib.request.Request('https://rest.runpod.io/v1'+path,data=data,headers=h,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        b=r.read(); return r.status,json.loads(b) if b else None
def append(row):
    with LEDGER.open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
def fetch(url,path):
    with urllib.request.urlopen(url,timeout=180) as r,path.open('wb') as f:
        while chunk:=r.read(8*1024*1024): f.write(chunk)

def main():
    begun=time.monotonic(); created_wall=time.time(); pod_id=None; watchdog=None
    record={'attempt':'attempt4_native_cuda13_smoke','started_at':utc(),'image':IMAGE,'image_index_digest':'sha256:af911a303a12516adf23ab8bb89c8fdf161ec0ceafc278a436fa111f5c118988','sglang_source_commit':'f63458b5beaceabbd9d749b9fc956370e1b649e6','model_revision':'75fce70','gpu_type':GPU,'prior_consolidated_spend_usd':PRIOR_SPEND,'cap_usd':CAP,'startup_deadline_seconds':STARTUP_DEADLINE,'experiment_deadline_seconds':EXPERIMENT_DEADLINE,'events':[]}
    try:
        _,pods=api('/pods')
        active=[{'id':p.get('id'),'name':p.get('name'),'status':p.get('desiredStatus')} for p in pods if p.get('desiredStatus') in ('RUNNING','CREATED','RESTARTING')]
        if active: raise RuntimeError('active pods prevent mutation: '+json.dumps(active))
        if PRIOR_SPEND >= CAP: raise RuntimeError('spend cap exhausted')
        command='export CAMPAIGN_DEADLINE_EPOCH=$(( $(date +%s) + 2100 )); printf %s "$SCRIPT_B64" | base64 -d > /tmp/smoke.sh; chmod +x /tmp/smoke.sh; timeout --signal=TERM 2200 /tmp/smoke.sh'
        payload={'name':'glm47flash-h100-native-smoke-20260713','imageName':IMAGE,'computeType':'GPU','gpuTypeIds':[GPU],'gpuTypePriority':'availability','gpuCount':1,'cloudType':'SECURE','containerDiskInGb':40,'volumeInGb':100,'volumeMountPath':'/workspace','ports':['8000/tcp'],'dockerEntrypoint':['/bin/bash','-lc'],'dockerStartCmd':[command],'env':{'SCRIPT_B64':base64.b64encode(SCRIPT.read_bytes()).decode()}}
        _,pod=api('/pods','POST',payload,120); pod_id=pod['id']; rate=float(pod.get('costPerHr',2.99)); created_wall=time.time()
        record.update({'pod_id':pod_id,'hourly_rate_usd':rate,'provider_created_at':pod.get('createdAt'),'machine_id':pod.get('machineId')})
        record['events'].append({'at':utc(),'event':'pod_created'})
        append({'timestamp':utc(),'event':'pod_created',**record})
        cancel=str(ROOT/f'.watchdog-{pod_id}.cancel'); watchdog_log=str(ROOT/f'attempt4-watchdog.jsonl')
        pathlib.Path(cancel).unlink(missing_ok=True)
        watchdog=subprocess.Popen(['python3',str(ROOT/'runpod_watchdog.py'),pod_id,str(time.time()+EXPERIMENT_DEADLINE),cancel,watchdog_log],start_new_session=True)
        endpoint=None; deadline=time.monotonic()+STARTUP_DEADLINE
        while time.monotonic()<deadline:
            _,state=api('/pods/'+pod_id,timeout=30)
            if state.get('desiredStatus') not in ('RUNNING','CREATED','RESTARTING'): raise RuntimeError('terminal provider state: '+str(state.get('desiredStatus')))
            mappings=state.get('portMappings') or {}; ip=state.get('publicIp'); port=mappings.get('8000') or mappings.get(8000)
            if ip and port: endpoint=f'http://{ip}:{port}'; record['events'].append({'at':utc(),'event':'artifact_endpoint_ready'}); break
            time.sleep(5)
        if not endpoint: raise TimeoutError('five-minute pod startup deadline exceeded')
        deadline=time.monotonic()+EXPERIMENT_DEADLINE-STARTUP_DEADLINE
        terminal=None
        while time.monotonic()<deadline:
            try:
                with urllib.request.urlopen(endpoint+'/STATUS',timeout=10) as r: status=r.read().decode().strip()
                if status in ('READY','FAILED'): terminal=status; break
            except (urllib.error.URLError,TimeoutError): pass
            _,state=api('/pods/'+pod_id,timeout=30)
            if state.get('desiredStatus') not in ('RUNNING','CREATED','RESTARTING'): raise RuntimeError('pod terminated before artifact status')
            time.sleep(10)
        if terminal not in ('READY','FAILED'): raise TimeoutError('smoke experiment deadline exceeded')
        artifact=ROOT/'attempt4-smoke.tar.gz'; checksum=ROOT/'attempt4-smoke.tar.gz.sha256.remote'
        fetch(endpoint+'/glm-smoke.tar.gz',artifact); fetch(endpoint+'/glm-smoke.tar.gz.sha256',checksum)
        local=hashlib.sha256(artifact.read_bytes()).hexdigest(); remote=checksum.read_text().split()[0]
        if local!=remote: raise ValueError('artifact checksum mismatch')
        record['terminal_status']=terminal; record['artifact']={'path':str(artifact),'bytes':artifact.stat().st_size,'sha256':local}; record['events'].append({'at':utc(),'event':'artifact_verified','terminal_status':terminal})
        if terminal!='READY': record['error']='remote smoke reported FAILED'
    except Exception as e:
        record['error']=repr(e); record['events'].append({'at':utc(),'event':'attempt_failed','error':repr(e)})
    finally:
        delete_status=None; verification='not_created'
        if pod_id:
            try: delete_status,_=api('/pods/'+pod_id,'DELETE',timeout=30)
            except urllib.error.HTTPError as e: delete_status=e.code
            try: api('/pods/'+pod_id,timeout=30); verification='present'
            except urllib.error.HTTPError as e: verification=f'http_{e.code}'
            pathlib.Path(ROOT/f'.watchdog-{pod_id}.cancel').touch()
        elapsed=time.monotonic()-begun; record.update({'finished_at':utc(),'allocation_seconds':elapsed,'conservative_spend_usd':elapsed*float(record.get('hourly_rate_usd',0))/3600,'teardown':{'delete_http_status':delete_status,'verification':verification}})
        RESULT.write_text(json.dumps(record,indent=2)+'\n'); append({'timestamp':utc(),'event':'attempt_finished',**record}); print(json.dumps(record,indent=2),flush=True)
    return 0 if record.get('terminal_status')=='READY' and record.get('teardown',{}).get('verification')=='http_404' else 1

if __name__=='__main__': raise SystemExit(main())
