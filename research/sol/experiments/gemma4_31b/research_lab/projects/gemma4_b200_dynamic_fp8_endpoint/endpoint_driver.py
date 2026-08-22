#!/usr/bin/env python3
import argparse,concurrent.futures,hashlib,json,math,os,pathlib,threading,time,urllib.request
canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def one(pair,base,out,barrier):
 i,body=pair;(out/f'request-{i:02}.json').write_bytes(canon(body));barrier.wait();t=time.monotonic();raw=[];ids=[];text='';usage={};err=None
 try:
  with urllib.request.urlopen(urllib.request.Request(base+'/v1/completions',canon(body),{'Content-Type':'application/json'}),timeout=1800) as response:
   for line in response:
    raw.append(line)
    if line.startswith(b'data: ') and line.strip()!=b'data: [DONE]':
     x=json.loads(line[6:]);c=(x.get('choices')or[{}])[0];ids.extend(c.get('token_ids')or[]);text+=c.get('text')or'';usage=x.get('usage')or usage
 except Exception as exc: err=repr(exc)
 elapsed=time.monotonic()-t;(out/f'response-{i:02}.sse').write_bytes(b''.join(raw))
 return {'index':i,'error':err,'seconds':elapsed,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'returned_token_ids':len(ids),'nonempty':bool(text),'request_sha256':hashlib.sha256(canon(body)).hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--arm',required=True);p.add_argument('--requests',type=int,default=32);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);prefix=[1000+((j*7919+17)%48000)for j in range(535)];bodies=[]
 for i in range(a.requests):
  suffix=[60000+i]+[1000+((i*4214+j*1543)%48000)for j in range(3678)];bodies.append({'model':'google/gemma-4-31B-it','prompt':prefix+suffix,'max_tokens':358,'min_tokens':358,'ignore_eos':True,'temperature':0,'seed':20260728+i,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'add_special_tokens':False})
 b=threading.Barrier(a.requests);started=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.requests)as ex: rows=list(ex.map(lambda q:one(q,f'http://{a.host}:{a.port}',a.output,b),enumerate(bodies)))
 batch=time.monotonic()-started;ok=all(r['error']is None and r['prompt_tokens']==4214 and r['completion_tokens']==358 and r['returned_token_ids']==358 and r['nonempty']and math.isfinite(r['seconds'])for r in rows)
 value={'schema_version':1,'classification':'endpoint_measurement'if ok else'endpoint_invalid','arm':a.arm,'complete_requests':sum(r['error']is None for r in rows),'service_seconds_per_request':batch/a.requests,'batch_seconds':batch,'rows':rows,'identity':{'checkpoint_revision':'b9ea41a2887d8607f594846523f94c6cc75ac8a4','workload':f'c{a.requests}/4214/358/text-only/non-reasoning','runtime_quantization':'none'if a.arm=='bf16_control'else'fp8_dynamic_weights'}};tmp=a.output/'TERMINAL.json.part';tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');os.replace(tmp,a.output/'TERMINAL.json')
if __name__=='__main__':main()
