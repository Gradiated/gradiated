#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json, time, urllib.request
from pathlib import Path
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def atomic(p,x):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.part'); t.write_text(json.dumps(x,sort_keys=True)+'\n'); t.replace(p)
def parse_sse(response):
 text=''; ids=[]; usage={}; finish=None; meta={}
 for raw in response:
  if not raw.startswith(b'data: '): continue
  data=raw[6:].strip()
  if data==b'[DONE]': continue
  item=json.loads(data); choice=(item.get('choices') or [{}])[0]
  text+=choice.get('text') or ''; ids.extend(choice.get('token_ids') or item.get('token_ids') or [])
  usage=item.get('usage') or usage; finish=choice.get('finish_reason') or finish; meta=item.get('meta_info') or item.get('metadata') or meta
 return {'choices':[{'message':{'content':text},'token_ids':ids,'finish_reason':finish}],'usage':usage,'meta_info':meta}
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pair',type=Path,required=True); p.add_argument('--payloads',type=Path,required=True); p.add_argument('--identity',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--arm');p.add_argument('--url');p.add_argument('--smoke',action='store_true');a=p.parse_args()
 spec=importlib.util.spec_from_file_location('pair',a.pair); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
 rows=json.loads(a.payloads.read_text()); expected=json.loads(a.identity.read_text())['request_sha256']
 if not isinstance(rows,list) or len(rows)!=32 or [hashlib.sha256(canonical(x)).hexdigest() for x in rows]!=expected: raise RuntimeError('exact_payload_hash_mismatch')
 proof={'pair_sha256':hashlib.sha256(a.pair.read_bytes()).hexdigest(),'payloads_sha256':hashlib.sha256(a.payloads.read_bytes()).hexdigest(),'ordered_request_sha256':expected,'no_http':True}
 if a.smoke: atomic(a.out/'SMOKE.json',proof);print(json.dumps(proof));return
 if not a.arm or not a.url: raise RuntimeError('arm_url_required')
 first=True
 def request(_url,payload,timeout):
  nonlocal first
  if first: first=False; atomic(a.out/f'{a.arm.upper()}_SUBMISSION.json',{**proof,'science_started':True,'arm':a.arm})
  req=urllib.request.Request(a.url.rstrip('/')+'/v1/completions',canonical(payload),{'Content-Type':'application/json'},method='POST'); started=time.monotonic()
  with urllib.request.urlopen(req,timeout=timeout) as response: return parse_sse(response),time.monotonic()-started
 m.request=request; result=m.run_arm(a.arm,a.url,rows,900);atomic(a.out/f'{a.arm.upper()}_ARM.json',result);print(json.dumps(result))
if __name__=='__main__': main()
