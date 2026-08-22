#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json
from pathlib import Path

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp=path.with_suffix(path.suffix+'.part'); temp.write_text(json.dumps(value,sort_keys=True)+'\n'); temp.replace(path)

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def tokens(label, count):
    out=[]; index=0; seed='gemma4-background-exact-mix-c32-20260718'
    while len(out)<count:
        digest=hashlib.sha256(f'{seed}|{label}|{index}'.encode()).digest()
        for offset in range(0,len(digest),4):
            out.append(1000+int.from_bytes(digest[offset:offset+4],'big')%249000)
            if len(out)==count: return out
        index+=1

def exact_workload(spec):
    if not isinstance(spec,dict) or (spec.get('concurrency'),spec.get('prompt_tokens'),spec.get('output_tokens'),spec.get('shared_prefix_tokens')) != (32,4214,358,535): raise RuntimeError('bound_c32_metadata_invalid')
    prefix=tokens('common-prefix',535); rows=[]
    for index in range(32):
        suffix=tokens(f'suffix-{index}',4214-535); suffix[0]=200000+index
        rows.append({'model':'google/gemma-4-31B-it','prompt':prefix+suffix,'max_tokens':358,'min_tokens':358,'ignore_eos':True,'temperature':0,'seed':20260718,'stream':True,'stream_options':{'include_usage':True},'return_token_ids':True,'add_special_tokens':False})
    observed=[hashlib.sha256(canonical(row)).hexdigest() for row in rows]
    if observed != spec.get('request_sha256'): raise RuntimeError('bound_c32_request_hash_mismatch')
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument('--pair',type=Path,required=True); p.add_argument('--workload',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--arm',choices=('stock','permanent_55local_5global')); p.add_argument('--url'); p.add_argument('--smoke',action='store_true'); a=p.parse_args()
    spec=importlib.util.spec_from_file_location('pair',a.pair); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    workload=exact_workload(json.loads(a.workload.read_text()))
    identity={'pair_sha256':hashlib.sha256(a.pair.read_bytes()).hexdigest(),'workload_sha256':hashlib.sha256(a.workload.read_bytes()).hexdigest(),'cwd':str(Path.cwd())}
    if a.smoke: write(a.out/'SMOKE.json',{'no_http':True,**identity}); print(json.dumps({'smoke':'pass',**identity})); return
    if not (a.arm and a.url): raise RuntimeError('arm_and_url_required')
    original=m.request; begun=False
    def request(url,payload,timeout):
        nonlocal begun
        if not begun:
            begun=True; write(a.out/f'{a.arm.upper()}_SUBMISSION.json',{'science_started':True,'arm':a.arm,**identity})
        return original(url,payload,timeout)
    m.request=request
    result=m.run_arm(a.arm,a.url,workload,900); write(a.out/f'{a.arm.upper()}_ARM.json',result); print(json.dumps(result))
if __name__=='__main__': main()
