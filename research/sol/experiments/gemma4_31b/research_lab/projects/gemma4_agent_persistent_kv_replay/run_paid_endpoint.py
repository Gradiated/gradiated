#!/usr/bin/env python3
"""Single retained-bench owner for the preregistered persistent-KV pair."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, shlex, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

HERE=Path(__file__).resolve().parent
LAB=HERE.parents[1]; REPO=HERE.parents[6]
sys.path.insert(0,str(REPO/'research/factory/src'))
sys.path.insert(0,str(REPO/'research/sol/experiments/glm47flash/campaign_100/nebius'))
from grad_research.gpu_pool import GpuPool
from placement_control import SSH_USER, extract_public_ipv4, get_instance, ssh_base

PROJECT='gemma4_agent_persistent_kv_replay'; BENCH='h200-sync-linear-e00vhh6h29fj68x91g'
INSTANCE='computeinstance-e00vhh6h29fj68x91g'; KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
IMAGE='docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b1197a4'
# Correct binding digest is kept in the project JSON; this constant is checked at runtime below.
IMAGE='docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c14757912e5e0f84e152e1'
IMAGE='docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
REMOTE='/home/glmrunner/gemma4-agent-persistent-kv-replay'; CHECKPOINT='/home/glmrunner/gemma4-async-result-pipeline/checkpoint'
ART=HERE/'artifacts'/f'paid-{dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%SZ")}'; RATE=2.46

def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def sha_bytes(x): return hashlib.sha256(x).hexdigest()
def sha_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(16<<20),b''): h.update(b)
    return h.hexdigest()
def atomic(p,v):
    p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); q.replace(p)
def remote(ip,cmd,timeout=300): return subprocess.run([*ssh_base(ip,KEY),cmd],text=True,capture_output=True,timeout=timeout)
def scp(ip,src,target,timeout=1200): return subprocess.run(['scp',*ssh_base(ip,KEY)[1:-1],str(src),f'{SSH_USER}@{ip}:{target}'],text=True,capture_output=True,timeout=timeout)
def emit(e,**kw):
    ART.mkdir(parents=True,exist_ok=True)
    with (ART/'OWNER_EVENTS.jsonl').open('a') as f: f.write(json.dumps({'timestamp_utc':now(),'event':e,**kw},sort_keys=True)+'\n')

def metrics(ip,port,stem):
    r=remote(ip,f'curl -fsS http://127.0.0.1:{port}/metrics',60); (ART/f'{stem}.prom').write_text(r.stdout); return r.stdout
def metric_totals(text):
    keys=('prefix_cache_queries','prefix_cache_hits','request_prompt_tokens_total','request_generation_tokens_total','request_prefill_time_seconds_sum','request_decode_time_seconds_sum','request_e2e_latency_seconds_sum','request_queue_time_seconds_sum','gpu_cache_usage_perc')
    out={k:0.0 for k in keys}; present=set()
    for line in text.splitlines():
        if not line or line.startswith('#') or ' ' not in line: continue
        name,val=line.rsplit(' ',1); base=name.split('{',1)[0].removesuffix('_total')
        for k in keys:
            if base.endswith(k):
                try: out[k]+=float(val); present.add(k)
                except ValueError: pass
    return out,present
def delta(a,b): return {k:b.get(k,0)-a.get(k,0) for k in a}

def call(ip,port,body):
    raw=json.dumps(body,separators=(',',':'),ensure_ascii=False).encode(); start=time.monotonic()
    req=urllib.request.Request(f'http://{ip}:{port}/v1/chat/completions',data=raw,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=900) as r: payload=r.read(); value=json.loads(payload)
    except urllib.error.HTTPError as e: raise RuntimeError(f'http_{e.code}:{e.read(4096).decode(errors="replace")}')
    return value, time.monotonic()-start, payload
def compact(v):
    c=(v.get('choices') or [{}])[0]; m=c.get('message') or {}; meta=v.get('meta_info') or {}
    ids=meta.get('output_token_ids') or meta.get('token_ids') or []
    return {'output_token_ids':ids,'output_token_ids_sha256':sha_bytes(json.dumps(ids,separators=(',',':')).encode()),'content':m.get('content'),'tool_calls':m.get('tool_calls'),'finish_reason':c.get('finish_reason'),'usage':v.get('usage'),'raw_response_sha256':sha_bytes(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())}

def run_arm(ip,port,arm,disable_cache):
    out=ART/arm; out.mkdir(parents=True,exist_ok=True); before_text=metrics(ip,port,'before-'+arm); before,_=metric_totals(before_text)
    rows=[]; errors=[]; requests=[json.loads(x) for x in (HERE/'paid_workload.jsonl').read_text().splitlines() if x.strip()]
    for n,item in enumerate(requests):
        try:
            value,elapsed,payload=call(ip,port,item['body']); c=compact(value)
            row={'ordinal':n,'request_id':item['request_id'],'session_id':item['session_id'],'tenant_id':item['tenant_id'],'turn_index':item['turn_index'],'elapsed_seconds':elapsed,'request_body_sha256':sha_bytes(json.dumps(item['body'],sort_keys=True,separators=(',',':')).encode()),'response':c}
            (out/f'{n:04d}.response.json').write_bytes(payload)
            rows.append(row)
        except Exception as e:
            errors.append({'ordinal':n,'request_id':item['request_id'],'error':repr(e)}); break
        if n % 25 == 24: emit('request_progress',arm=arm,completed=n+1,total=len(requests))
    after_text=metrics(ip,port,'after-'+arm); after,_=metric_totals(after_text); d=delta(before,after)
    atomic(out/'ROWS.json',rows); atomic(out/'ERRORS.json',errors)
    return {'arm':arm,'rows':len(rows),'errors':errors,'metrics_delta':d,'metric_names':sorted(metric_totals(after_text)[1]),'wall_seconds':sum(x['elapsed_seconds'] for x in rows)}

def main():
    ART.mkdir(parents=True,exist_ok=True); atomic(ART/'INVOCATION_STATE.json',{'control_science_started':False,'candidate_science_started':False})
    binding=json.loads((HERE/'DIRECTOR_GPU_BINDING.json').read_text()); assert binding['bench']['id']==BENCH and binding['model'].startswith('google/gemma-4-31B-it@')
    assert sha_file(HERE/'paid_workload.jsonl')=='b467cc202c6d4ae54ba5f0dc3eb701d3923dce37773b9afb33bcdc28be7e6440'
    pool=GpuPool(LAB); pool.update(PROJECT,contents={'project':PROJECT,'runtime':'Pinned SGLang v0.5.13 matched persistent-KV endpoint pair','checkpoint':'Exact immutable checkpoint bound by DIRECTOR_GPU_BINDING.json; project-local tokenizer/workload snapshot staged.','server_state':'Owner preparing retained H200; no scientific request accepted.'})
    stop=threading.Event()
    def beat():
        while not stop.wait(40):
            try: pool.heartbeat(PROJECT); emit('heartbeat')
            except Exception as e: emit('heartbeat_failure',error=repr(e)); return
    t=threading.Thread(target=beat,daemon=True); t.start(); final={}; condition='ready'; claimed_at=time.time()
    try:
        ip=extract_public_ipv4(get_instance(INSTANCE));
        if not ip: raise RuntimeError('typed_provider_boundary:no_public_ip')
        ident=remote(ip,'hostname; nvidia-smi --query-gpu=name,driver_version,memory.used --format=csv,noheader; sudo docker image inspect '+shlex.quote(IMAGE)+' >/dev/null',90)
        (ART/'remote-identity.stdout').write_text(ident.stdout); (ART/'remote-identity.stderr').write_text(ident.stderr)
        if ident.returncode: raise RuntimeError('typed_remote_boundary:identity_or_pinned_image_failed')
        tar=ART/'project-snapshot.tar'; subprocess.run(['tar','-cf',str(tar),'--exclude=inputs/checkpoint','--exclude=artifacts','--exclude=__pycache__','-C',str(HERE),'.'],check=True); digest=sha_file(tar)
        prep=remote(ip,f'mkdir -p {shlex.quote(REMOTE)} && if test -f {shlex.quote(REMOTE+"/project-snapshot.tar.sha256")}; then cat {shlex.quote(REMOTE+"/project-snapshot.tar.sha256")}; fi',60); matched=prep.returncode==0 and prep.stdout.strip().split()[:1]==[digest]
        if not matched:
            part=f'{REMOTE}/project-snapshot.tar.{digest}.part'; sent=scp(ip,tar,part,1200)
            if sent.returncode: raise RuntimeError('typed_transfer_boundary:'+sent.stderr[-1000:])
            done=remote(ip,f'test "$(sha256sum {shlex.quote(part)} | awk \'{{print $1}}\')" = {digest} && mv -f {shlex.quote(part)} {shlex.quote(REMOTE+"/project-snapshot.tar")} && printf \'%s  %s\\n\' {digest} project-snapshot.tar > {shlex.quote(REMOTE+"/project-snapshot.tar.sha256")} && rm -rf {shlex.quote(REMOTE+"/project")} && mkdir -p {shlex.quote(REMOTE+"/project")} && tar -xf {shlex.quote(REMOTE+"/project-snapshot.tar")} -C {shlex.quote(REMOTE+"/project")}',180)
            if done.returncode: raise RuntimeError('typed_transfer_boundary:hash_or_extract_failed')
        emit('snapshot_bound',sha256=digest,bytes=tar.stat().st_size)
        prep=remote(ip,f'mkdir -p {shlex.quote(REMOTE+"/artifacts")} && sudo docker rm -f gemma-pkv-control gemma-pkv-candidate >/dev/null 2>&1 || true',60)
        base=['--model-path','/work/checkpoint','--tokenizer-path','/work/checkpoint','--served-model-name','google/gemma-4-31B-it','--dtype','bfloat16','--quantization','fp8','--tp-size','1','--kv-cache-dtype','fp8_e5m2','--host','0.0.0.0','--context-length','5000','--max-running-requests','1','--max-total-tokens','50000','--mem-fraction-static','0.85','--enable-metrics','--enable-cache-report','--skip-server-warmup','--enable-dynamic-chunking','--chunked-prefill-size','2048','--enable-fused-qk-norm-rope','--cuda-graph-max-bs','1','--prefill-attention-backend','triton','--decode-attention-backend','triton','--page-size','1','--num-continuous-decode-steps','1','--triton-attention-num-kv-splits','8','--tool-call-parser','gemma4']
        def launch(name,port,off):
            args=base+['--port',str(port)]+(['--disable-radix-cache'] if off else [])
            cmd='sudo docker run -d --name '+name+' --gpus all --ipc=host --network=host -v '+shlex.quote(CHECKPOINT)+':/work/checkpoint:ro -v '+shlex.quote(REMOTE+'/project')+':/work/project:ro -v '+shlex.quote(REMOTE+'/artifacts')+':/work/artifacts '+shlex.quote(IMAGE)+' python3 -m sglang.launch_server '+' '.join(shlex.quote(x) for x in args)
            r=remote(ip,cmd,90); (ART/(name+'-launch.stdout')).write_text(r.stdout); (ART/(name+'-launch.stderr')).write_text(r.stderr)
            if r.returncode: raise RuntimeError('launcher_failed:'+name+':'+r.stderr[-1000:])
            for _ in range(240):
                h=remote(ip,f'curl -fsS http://127.0.0.1:{port}/v1/models',10)
                if h.returncode==0 and 'gemma-4-31B-it' in h.stdout: return args
                time.sleep(2)
            diag=remote(ip,'sudo docker inspect '+shlex.quote(name)+'; sudo docker logs --tail 200 '+shlex.quote(name)+' 2>&1 || true',60); (ART/(name+'-readiness-diagnostic.txt')).write_text(diag.stdout+'\n'+diag.stderr); raise RuntimeError('model_readiness_timeout:'+name)
        atomic(ART/'INVOCATION_STATE.json',{'control_science_started':False,'candidate_science_started':False,'checkpoint':CHECKPOINT,'snapshot_sha256':digest})
        launch('gemma-pkv-control',30000,True); atomic(ART/'INVOCATION_STATE.json',{'control_science_started':True,'candidate_science_started':False,'checkpoint':CHECKPOINT,'snapshot_sha256':digest}); emit('control_science_started')
        control=run_arm(ip,30000,'control',True); atomic(ART/'CONTROL_TERMINAL.json',control)
        remote(ip,'sudo docker rm -f gemma-pkv-control >/dev/null 2>&1 || true',60); time.sleep(3)
        launch('gemma-pkv-candidate',30000,False); atomic(ART/'INVOCATION_STATE.json',{'control_science_started':True,'candidate_science_started':True,'checkpoint':CHECKPOINT,'snapshot_sha256':digest}); emit('candidate_science_started')
        candidate=run_arm(ip,30000,'candidate',False); atomic(ART/'CANDIDATE_TERMINAL.json',candidate)
        cr={x['request_id']:x for x in json.loads((ART/'control/ROWS.json').read_text())}; nr={x['request_id']:x for x in json.loads((ART/'candidate/ROWS.json').read_text())}
        identical=len(cr)==905 and len(nr)==905 and all(cr[k]['response']['output_token_ids_sha256']==nr[k]['response']['output_token_ids_sha256'] and cr[k]['response']['tool_calls']==nr[k]['response']['tool_calls'] and cr[k]['response']['content']==nr[k]['response']['content'] for k in cr)
        final={'schema_version':1,'classification':'matched_persistent_kv_endpoint_pair','pass':identical and not control['errors'] and not candidate['errors'],'identical_token_tool_behavior':identical,'control':control,'candidate':candidate,'candidate_scientific_invocation_started':True,'snapshot_sha256':digest,'checkpoint_path':CHECKPOINT,'cache_budget_tokens':50000,'cache_budget_gib_derived':50000*349000/1024**3,'synthetic_tool_results':True}
        atomic(ART/'FINAL_TERMINAL.json',final); emit('scientific_terminal',classification=final['classification'],pass_result=final['pass'])
    except Exception as e:
        final={'schema_version':1,'classification':'typed_external_blocker' if 'typed_' in str(e) else 'owner_failure','reason':repr(e),'timestamp_utc':now()}; atomic(ART/'FINAL_TERMINAL.json',final); emit('owner_failure',error=repr(e))
    finally:
        stop.set(); t.join(5); elapsed=time.time()-claimed_at; spend=elapsed/3600*RATE
        status=json.loads((HERE/'STATUS.json').read_text()); status.update({'active_session':None,'actual_spend_usd':round(spend,6),'terminal_artifact':str(ART/'FINAL_TERMINAL.json'),'terminal_sha256':sha_file(ART/'FINAL_TERMINAL.json'),'summary':final.get('classification'),'next_action':'Interpret matched control/candidate terminal.'}); atomic(HERE/'STATUS.json',status)
        try: pool.release(PROJECT,contents={'project':PROJECT,'artifacts':str(ART),'runtime':'Pinned SGLang matched cross-turn persistence control/candidate pair','result':final.get('classification'),'server_state':'No server retained; image/checkpoint/caches retained.'},condition=condition)
        except Exception as e: emit('release_failure',error=repr(e))
        emit('bench_released',claimed_seconds=elapsed,actual_spend_usd=spend,condition=condition)
    return 0 if final.get('classification')=='matched_persistent_kv_endpoint_pair' else 3
if __name__=='__main__': raise SystemExit(main())
