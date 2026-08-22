#!/usr/bin/env python3
import argparse, concurrent.futures, hashlib, json, math, os, pathlib, threading, time, urllib.request

def canon(x): return json.dumps(x, sort_keys=True, separators=(',', ':')).encode()
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p, x):
 t=p.with_suffix(p.suffix+'.part'); t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); os.replace(t,p)
def one(pair,base,out,barrier):
 i,b=pair; (out/f'request-{i:02}.json').write_bytes(canon(b)); barrier.wait(); started=time.monotonic(); raw=[]; ids=[]; text=''; usage={}; error=None
 try:
  with urllib.request.urlopen(urllib.request.Request(base+'/v1/completions',canon(b),{'Content-Type':'application/json'}),timeout=1800) as r:
   for line in r:
    raw.append(line)
    if line.startswith(b'data: ') and line.strip()!=b'data: [DONE]':
     x=json.loads(line[6:]); c=(x.get('choices')or[{}])[0]; ids.extend(c.get('token_ids')or[]); text+=c.get('text')or''; usage=x.get('usage')or usage
 except Exception as exc: error=repr(exc)
 (out/f'response-{i:02}.sse').write_bytes(b''.join(raw))
 return {'index':i,'error':error,'seconds':time.monotonic()-started,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'returned_token_ids':len(ids),'nonempty':bool(text),'request_sha256':hashlib.sha256(canon(b)).hexdigest()}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--host',required=True); p.add_argument('--port',type=int,required=True); p.add_argument('--output',type=pathlib.Path,required=True); p.add_argument('--binding',type=pathlib.Path,required=True); p.add_argument('--c64',type=pathlib.Path,required=True); a=p.parse_args()
 b=json.loads(a.binding.read_text()); c64=json.loads(a.c64.read_text()); ids=b['immutable_identities']
 assert b['driver_sha256']==sha(__file__) and sha(a.c64)==b['c64_terminal_sha256']
 assert ids=={'checkpoint_revision':'b9ea41a2887d8607f594846523f94c6cc75ac8a4','runtime_quantization':'runtime_dynamic_fp8_weights','model':'google/gemma-4-31B-it','workload':'c96/4214/358/text-only/non-reasoning'}
 prefix=[1000+((j*7919+17)%48000)for j in range(535)]; bodies=[]
 for i in range(96):
  suffix=[60000+i]+[1000+((i*4214+j*1543)%48000)for j in range(3678)]; bodies.append({'model':ids['model'],'prompt':prefix+suffix,'max_tokens':358,'min_tokens':358,'ignore_eos':True,'temperature':0,'seed':20260728+i,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'add_special_tokens':False})
 assert [hashlib.sha256(canon(x)).hexdigest() for x in bodies[:64]]==[x['request_sha256'] for x in c64['candidate']['rows']]
 a.output.mkdir(parents=True,exist_ok=True)
 def started(): write(a.output/'SCIENCE_STARTED.json',{'schema_version':1,'arm':'dynamic_fp8_c96_saturation','binding_sha256':sha(a.binding),'requests':96,'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
 barrier=threading.Barrier(96,action=started); t=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=96) as ex: rows=list(ex.map(lambda q:one(q,f'http://{a.host}:{a.port}',a.output,barrier),enumerate(bodies)))
 batch=time.monotonic()-t; ok=all(x['error'] is None and x['prompt_tokens']==4214 and x['completion_tokens']==358 and x['returned_token_ids']==358 and x['nonempty'] and math.isfinite(x['seconds']) for x in rows)
 write(a.output/'TERMINAL.json',{'schema_version':1,'classification':'endpoint_measurement'if ok else'endpoint_invalid','arm':'dynamic_fp8_c96_saturation','complete_requests':sum(x['error']is None for x in rows),'service_seconds_per_request':batch/96,'batch_seconds':batch,'rows':rows,'identity':ids,'binding_sha256':sha(a.binding)})
if __name__=='__main__': main()
