#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'qualified_c32_request_payloads.json'; SPEC=ROOT/'inputs/h200_55l5g_endpoint_packet/qualified_c32_workload.json'
def canonical(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def tokens(label,n):
 out=[]; i=0; seed='gemma4-background-exact-mix-c32-20260718'
 while len(out)<n:
  d=hashlib.sha256(f'{seed}|{label}|{i}'.encode()).digest()
  for j in range(0,len(d),4):
   out.append(1000+int.from_bytes(d[j:j+4],'big')%249000)
   if len(out)==n:return out
  i+=1
prefix=tokens('common-prefix',535); rows=[]
for i in range(32):
 suffix=tokens(f'suffix-{i}',3679);suffix[0]=200000+i
 rows.append({'model':'google/gemma-4-31B-it','prompt':prefix+suffix,'max_tokens':358,'min_tokens':358,'ignore_eos':True,'temperature':0,'seed':20260718,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'add_special_tokens':False})
spec=json.loads(SPEC.read_text()); hashes=[hashlib.sha256(canonical(x)).hexdigest() for x in rows]
if hashes!=spec['request_sha256']:raise SystemExit('bound_hash_mismatch')
t=OUT.with_suffix('.json.part');t.write_text(json.dumps(rows,separators=(',',':'))+'\n');json.loads(t.read_text());t.replace(OUT)
print(json.dumps({'payloads':str(OUT),'sha256':hashlib.sha256(OUT.read_bytes()).hexdigest(),'ordered_request_sha256':hashes}))
