#!/usr/bin/env python3
import concurrent.futures, hashlib, json, os, pathlib, subprocess, threading, time, urllib.request

ROOT=pathlib.Path(os.environ.get('NGRAM_SUSTAINABLE_ROOT','/home/glmrunner/gemma4-ngram-sustainable-cost'))
P=ROOT/'project'; OUT=ROOT/'out'; C=json.loads((P/'IMMUTABLE_CONSUMER_v2.json').read_text())
MODEL=C['model']['id']; IMAGE=C['runtime']['image']; LAUNCH=json.loads((P/'ngram-launch.json').read_text())['args']
def atomic(name,x):
    OUT.mkdir(parents=True,exist_ok=True); q=OUT/(name+'.part'); q.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n'); q.replace(OUT/name)
def run(x): return subprocess.run(x,text=True,capture_output=True,check=False)
def metrics(tag):
    try: raw=urllib.request.urlopen('http://127.0.0.1:30000/metrics',timeout=10).read().decode(); (OUT/(tag+'.prom')).write_text(raw); return hashlib.sha256(raw.encode()).hexdigest()
    except Exception as e: return 'error:'+repr(e)
def post(body):
    native={'input_ids':body['prompt'],'sampling_params':{'temperature':0,'max_new_tokens':body['max_tokens'],'min_new_tokens':body['min_tokens'],'ignore_eos':body['ignore_eos']}}
    raw=json.dumps(native,separators=(',',':')).encode(); req=urllib.request.Request('http://127.0.0.1:30000/generate',raw,{'Content-Type':'application/json'})
    t=time.monotonic(); first=[None]
    with urllib.request.urlopen(req,timeout=1200) as r:
        chunks=[]
        while True:
            z=r.read(8192)
            if not z: break
            if first[0] is None: first[0]=time.monotonic()
            chunks.append(z)
    e=time.monotonic(); data=b''.join(chunks); parsed=json.loads(data); meta=parsed.get('meta_info') or {}; parsed['usage']={'prompt_tokens':meta.get('prompt_tokens',len(body['prompt'])),'completion_tokens':meta.get('completion_tokens',body['max_tokens']),'total_tokens':meta.get('prompt_tokens',len(body['prompt']))+meta.get('completion_tokens',body['max_tokens'])}; return parsed, {'ttft_seconds':(first[0] or e)-t,'latency_seconds':e-t,'raw_sha256':hashlib.sha256(data).hexdigest()}
def launch_args(context_length):
    args=list(LAUNCH); i=args.index('--context-length'); args[i+1]=str(context_length); return args
def launch(name, context_length):
    run(['sudo','docker','rm','-f',name])
    cmd=['sudo','docker','run','-d','--name',name,'--gpus','all','--ipc=host','--network','host','-v',f'{ROOT}:/work','-v',f'{ROOT}/checkpoint:/work/checkpoint:ro',IMAGE,'python3','-m','sglang.launch_server',*launch_args(context_length)]
    q=run(cmd); atomic(f'launch-{context_length}.json',{'cmd':cmd[9:],'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr})
    if q.returncode: raise RuntimeError(f'launch_failed_context_{context_length}')
    wait()
def wait():
    for _ in range(300):
        try:
            if MODEL in urllib.request.urlopen('http://127.0.0.1:30000/v1/models',timeout=4).read().decode(): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError('server_not_ready')
def sample(stop, rows):
    while not stop.wait(2):
        r=run(['nvidia-smi','--query-gpu=timestamp,utilization.gpu,power.draw,memory.used','--format=csv,noheader,nounits']); rows.append({'t':time.time(),'smi':r.stdout.strip()})
def body(row, tag):
    x=dict(row['request_body']); x['model']=MODEL; x['ignore_eos']=True; x['min_tokens']=358; x['max_tokens']=358; x['request_id']='sustainable-'+tag; return x
def execute(index, scheduled, submitted, request, origin):
    client_started=time.monotonic()-origin
    try:
        response,timing=post(request); usage=response.get('usage') or {}
        return {'i':index,'scheduled_s':scheduled,'submitted_s':submitted,'client_started_s':client_started,'completed_s':time.monotonic(),'usage':usage,'timing':timing,'request_sha256':hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()}
    except Exception as exc:
        return {'i':index,'scheduled_s':scheduled,'submitted_s':submitted,'client_started_s':client_started,'completed_s':time.monotonic(),'error':repr(exc)}
def main():
    name='gemma4-ngram-sustainable'; run(['sudo','docker','rm','-f',name])
    atomic('INVOCATION_STATE.json',{'science_started':False,'phase':'ten_k_server_load'})
    try:
      trace=json.loads((P/'TRACE_PACKET.json').read_text()); ten=body(trace['separate_10k_stream'],'10k')
      launch(name,11000); atomic('INVOCATION_STATE.json',{'science_started':True,'phase':'ten_k'})
      a,tm=post(ten); tenrow={'request_id':ten['request_id'],'usage':a.get('usage'),'timing':tm,'output_sha256':hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()}; atomic('TEN_K.json',tenrow)
      run(['sudo','docker','rm','-f',name]); atomic('INVOCATION_STATE.json',{'science_started':True,'phase':'primary_server_load'})
      launch(name,5000); before=metrics('metrics-before-primary')
      group=next(x for x in trace['primary_groups'] if x['name']=='primary_c1'); warm=body(group['warmup'],'warmup'); post(warm); metrics('metrics-after-warmup')
      stop=threading.Event(); smi=[]; th=threading.Thread(target=sample,args=(stop,smi),daemon=True); th.start(); started=time.monotonic(); spacing=C['arrival_spacing_seconds']
      n=int(C['duration_seconds']/spacing)
      atomic('INVOCATION_STATE.json',{'science_started':True,'phase':'primary_open_loop','scheduled':n})
      futures=[]
      with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for i in range(n):
          scheduled=i*spacing; due=started+scheduled; time.sleep(max(0,due-time.monotonic()))
          source=group['scored'][i % len(group['scored'])]; request=body(source,str(i)); request['prompt'][535]=200000+i; submitted=time.monotonic()-started
          futures.append(pool.submit(execute,i,scheduled,submitted,request,started))
        rows=[future.result() for future in concurrent.futures.as_completed(futures)]
      ended=time.monotonic(); stop.set(); th.join(3); rows.sort(key=lambda x:x['i']); errors=[x for x in rows if 'error' in x]; valid=[x for x in rows if 'error' not in x]
      for row in rows: row['completed_s']-=started
      metrics('metrics-after'); (OUT/'requests.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows)); (OUT/'power.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in smi))
      total=sum((x['usage'].get('total_tokens') or 0) for x in valid); prompt=sum((x['usage'].get('prompt_tokens') or 0) for x in valid); comp=sum((x['usage'].get('completion_tokens') or 0) for x in valid); final={'result':'measured_sustainable_cost_surface','ten_k':tenrow,'primary':{'scheduled':n,'completed':len(valid),'failures':errors,'elapsed_seconds':ended-started,'prompt_tokens':prompt,'completion_tokens':comp,'total_tokens':total,'queue_final_seconds':max([0]+[x['client_started_s']-x['scheduled_s'] for x in rows]),'latency_seconds':{'p50':sorted(x['timing']['latency_seconds'] for x in valid)[len(valid)//2] if valid else None}},'metrics_sha256':{'before':before,'after':metrics('metrics-final')},'power_samples':len(smi),'consumer_sha256':hashlib.sha256((P/'IMMUTABLE_CONSUMER_v2.json').read_bytes()).hexdigest()}; atomic('FINAL_TERMINAL.json',final)
    finally: run(['sudo','docker','rm','-f',name])
if __name__=='__main__': main()
