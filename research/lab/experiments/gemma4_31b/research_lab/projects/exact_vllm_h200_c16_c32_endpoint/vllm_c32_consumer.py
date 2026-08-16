import concurrent.futures,hashlib,json,math,pathlib,threading,time,urllib.request,argparse
from exact_mix_runner import canonical,tokens,MODEL,PROMPT_TOKENS,OUTPUT_TOKENS,COMMON_TOKENS
B='http://127.0.0.1:30000'
def get(x): return urllib.request.urlopen(B+x,timeout=30).read()
def post(x): return urllib.request.urlopen(urllib.request.Request(B+'/v1/completions',canonical(x),{'Content-Type':'application/json'}),timeout=1800)
def metric(raw,names):
 v=[]
 for l in raw.decode(errors='replace').splitlines():
  if not l.startswith('#') and l.split('{',1)[0].split(' ',1)[0] in names:
   try:v.append(float(l.rsplit(' ',1)[1]))
   except:pass
 return sum(v) if v else None
def one(i,x,r,b):
 (r/f'body-{i:02}.json').write_bytes(canonical(x));b.wait(120);st=time.monotonic();ids=[];text='';usage={};raw=[];err=None
 try:
  with post(x) as q:
   for z in q:
    raw.append(z)
    if z.startswith(b'data: ') and z.strip()!=b'data: [DONE]':
     y=json.loads(z[6:]);c=(y.get('choices')or[{}])[0];ids+=c.get('token_ids')or[];text+=c.get('text')or'';usage=y.get('usage')or usage
 except Exception as e:err=repr(e)
 en=time.monotonic();(r/f'response-{i:02}.sse').write_bytes(b''.join(raw));return {'index':i,'error':err,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'returned_token_ids':len(ids),'text_nonempty':bool(text),'wall_seconds':en-st,'request_sha256':hashlib.sha256(canonical(x)).hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();r=a.output;r.mkdir(parents=True);pre=tokens('common-prefix',535);bs=[]
 for i in range(32):
  s=tokens(f'suffix-{i}',4214-535);s[0]=200000+i;bs.append({'model':MODEL,'prompt':pre+s,'max_tokens':358,'min_tokens':358,'ignore_eos':True,'temperature':0,'seed':20260718,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'add_special_tokens':False})
 hashes=[hashlib.sha256(canonical(x)).hexdigest() for x in bs];(r/'WORKLOAD.json').write_text(json.dumps({'request_sha256':hashes},sort_keys=True));models=get('/v1/models');(r/'models.json').write_bytes(models);idle=get('/metrics');(r/'metrics-idle.prom').write_bytes(idle)
 reset=urllib.request.urlopen(urllib.request.Request(B+'/reset_prefix_cache',b'',method='POST'),timeout=30).read();(r/'cache-reset.json').write_bytes(reset);s=tokens('warmup-suffix',3679);s[0]=199999;w={**bs[0],'prompt':pre+s,'max_tokens':1,'min_tokens':1,'stream':False};(r/'warmup.json').write_bytes(post(w).read());before=get('/metrics');(r/'metrics-before.prom').write_bytes(before);bar=threading.Barrier(32);st=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:rows=[f.result() for f in [ex.submit(one,i,x,r,bar) for i,x in enumerate(bs)]]
 wall=time.monotonic()-st;after=get('/metrics');(r/'metrics-after.prom').write_bytes(after);q=metric(after,{'vllm:prefix_cache_queries','vllm:prefix_cache_queries_total'})-metric(before,{'vllm:prefix_cache_queries','vllm:prefix_cache_queries_total'});h=metric(after,{'vllm:prefix_cache_hits','vllm:prefix_cache_hits_total'})-metric(before,{'vllm:prefix_cache_hits','vllm:prefix_cache_hits_total'});ok=all(x['error']is None and x['prompt_tokens']==4214 and x['completion_tokens']==358 and x['returned_token_ids']==358 and x['text_nonempty'] and math.isfinite(x['wall_seconds']) for x in rows);out={'pass':ok and q==134848 and 0<=h<=17120,'complete_requests':sum(x['error']is None for x in rows),'reload_count':0,'service_seconds_per_request':wall/32,'batch_seconds':wall,'rows':rows,'cache':{'query_tokens':q,'hit_tokens':h},'runtime_identity':{'models':json.loads(models),'cache_reset_sha256':hashlib.sha256(reset).hexdigest(),'request_hashes_match_frozen_generator':len(hashes)==32}};(r/'TERMINAL.json').write_text(json.dumps(out,indent=2,sort_keys=True));return 0 if out['pass']else 72
if __name__=='__main__':raise SystemExit(main())
