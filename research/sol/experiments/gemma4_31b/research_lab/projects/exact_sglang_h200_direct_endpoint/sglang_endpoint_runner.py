#!/usr/bin/env python3
import argparse,concurrent.futures,hashlib,json,pathlib,threading,time,urllib.request
def pull(url,path):
 try:path.write_bytes(urllib.request.urlopen(url,timeout=30).read())
 except Exception as e:path.with_suffix('.error').write_text(repr(e))
def call(body,path,barrier=None):
 if barrier:barrier.wait()
 raw=json.dumps(body,separators=(',',':')).encode();start=time.monotonic()
 try:response=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/completions',raw,{'Content-Type':'application/json'}),timeout=1800).read();parsed=json.loads(response);error=None
 except Exception as e:response=b'';parsed={};error=repr(e)
 row={'request_sha256':hashlib.sha256(raw).hexdigest(),'response_sha256':hashlib.sha256(response).hexdigest(),'request':body,'response':parsed,'error':error,'wall_seconds':time.monotonic()-start};path.write_text(json.dumps(row,sort_keys=True));return row
def valid(row,prompt,output):
 u=row['response'].get('usage',{});return not row['error'] and bool(row['response'].get('choices')) and u.get('prompt_tokens')==prompt and u.get('completion_tokens')==output
p=argparse.ArgumentParser();p.add_argument('--trace');p.add_argument('--output',type=pathlib.Path);p.add_argument('--deadline',type=float);a=p.parse_args();t=json.load(open(a.trace));a.output.mkdir();g=next(x for x in t['primary_groups'] if x['concurrency']==16);g={**g,'concurrency':32,'scored':g['scored']*2}
pull('http://127.0.0.1:30000/metrics',a.output/'metrics-before.prom');warm=g['scored'][0]['request_body'].copy();warm['max_tokens']=warm['min_tokens']=1;w=call(warm,a.output/'warmup.json');pull('http://127.0.0.1:30000/metrics',a.output/'metrics-after-warmup.prom');b=threading.Barrier(32);start=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=32) as x:rows=list(x.map(lambda z:call(z[1]['request_body'],a.output/f'c32-{z[0]}.json',b),enumerate(g['scored'])))
elapsed=time.monotonic()-start;pull('http://127.0.0.1:30000/metrics',a.output/'metrics-after-c32.prom');ok=valid(w,4214,1) and all(valid(x,4214,358) for x in rows);rps=32/elapsed
tenk={'attempted':False,'reason':'c32_invalid_or_less_than_20_minutes_remaining'}
if ok and time.time()+1200<=a.deadline:
 q=t['separate_10k_stream']['request_body'];tenk={'attempted':True,'row':call(q,a.output/'10k.json'),'pass':False};tenk['pass']=valid(tenk['row'],10000,358)
terminal={'classification':'sglang_bf16_fp8e5m2_c32','semantic_pass':ok,'c32_completed_requests_per_second':rps,'c32_service_seconds_per_request':elapsed/32,'market_gate_rps':2.118591,'market_pass':ok and rps>=2.118591,'batch_seconds':elapsed,'rows':32,'tenk':tenk};(a.output/'TERMINAL.json').write_text(json.dumps(terminal,sort_keys=True));raise SystemExit(0 if ok else 72)
