#!/usr/bin/env python3
import argparse, gc, hashlib, json, time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from generation_equivalence_runner import PROJECT, SOURCE, ADAPTER, SCORER, CASES, canonical, digest, write, frozen, load_module, request_bytes, score, first_divergence, post


def direct(checkpoint, out):
    bindings, manifest, cases, checks = frozen(); adapter=load_module('adapter',ADAPTER); scorer=load_module('scorer',SCORER); transform=load_module('transform',SOURCE/'safe_code_contract.py'); policy=json.loads((SOURCE/'suite'/'policy.json').read_text())
    tok=AutoTokenizer.from_pretrained(checkpoint); model=AutoModelForCausalLM.from_pretrained(checkpoint,torch_dtype=torch.bfloat16).cuda().eval(); eos=[tok.eos_token_id] if isinstance(tok.eos_token_id,int) else tok.eos_token_id
    rows=[]
    for case in cases:
        raw,t=request_bytes(case,policy,transform); ids=tok.apply_chat_template(json.loads(raw)['messages'],tokenize=True,add_generation_prompt=True)
        if isinstance(ids,dict): ids=ids['input_ids']
        if hasattr(ids,'encodings'): ids=ids.encodings[0].ids
        if hasattr(ids,'ids'): ids=ids.ids
        if hasattr(ids,'tolist'): ids=ids.tolist()
        if len(ids)==1 and isinstance(ids[0],list): ids=ids[0]
        with torch.inference_mode(): generated=model.generate(torch.tensor([ids],device='cuda'),do_sample=False,max_new_tokens=128,eos_token_id=eos,pad_token_id=tok.pad_token_id or tok.eos_token_id)
        output_ids=generated[0,len(ids):].tolist(); text=tok.decode(output_ids,skip_special_tokens=True); result={'output_ids':output_ids,'output_text':text,'finish_reason':'eos' if output_ids and output_ids[-1] in eos else 'length',**score(case,raw,text,adapter,scorer)}
        rows.append({'case_id':case['case_id'],'raw_request':raw,'input_ids':ids,'input_ids_sha256':digest(ids),'transform':{'transformed':t.transformed,'original_sha256':t.original_sha256,'transformed_sha256':t.transformed_sha256},'result':result})
        write(out/'transformers_raw.json',rows)
    del model; gc.collect(); torch.cuda.empty_cache(); write(out/'DIRECT_READY.json',{'cases':len(rows),'sha256':hashlib.sha256((out/'transformers_raw.json').read_bytes()).hexdigest(),'checks':checks,'suite_sha256':manifest['suite_sha256']})


def sglang(base,out):
    bindings,manifest,cases,checks=frozen(); adapter=load_module('adapter',ADAPTER); scorer=load_module('scorer',SCORER); direct_rows=json.loads((out/'transformers_raw.json').read_text()); by={x['case_id']:x for x in direct_rows}; rows=[]
    for case in cases:
        d=by[case['case_id']]; body={'input_ids':d['input_ids'],'sampling_params':{'temperature':0.0,'top_p':1.0,'max_new_tokens':128,'stop_token_ids':[2]},'return_logprob':True,'add_special_tokens':False}; response,raw=post(base,body); meta=response.get('meta_info') or {}; ids=meta.get('output_ids') or response.get('output_ids'); text=response.get('text')
        result={'output_ids':ids,'output_text':text,'finish_reason':meta.get('finish_reason','unknown'),**score(case,d['raw_request'],text,adapter,scorer)}
        rows.append({'case_id':case['case_id'],'input_ids':d['input_ids'],'http':raw,'result':result}); write(out/'sglang_raw.json',rows)
    terminal=[]
    for case in cases:
        d=by[case['case_id']]['result']; s=next(x['result'] for x in rows if x['case_id']==case['case_id']); terminal.append({'case_id':case['case_id'],'input_token_ids_equal':True,'output_token_ids_equal':d['output_ids']==s['output_ids'],'first_output_divergence':first_divergence(d['output_ids'],s['output_ids']),'transformers':d,'sglang':s})
    primary=terminal[0]; decision='shared_primary_failure_close_model_quality_branch' if primary['transformers']['score']==primary['sglang']['score']==0 else 'transformers_only_primary_pass_deep_first_divergence' if primary['transformers']['score']==1 and primary['sglang']['score']==0 else 'both_primary_pass_request_path_discrepancy' if primary['transformers']['score']==primary['sglang']['score']==1 else 'mixed_or_transformers_failure_review_raw_artifacts'
    write(out/'TERMINAL.json',{'classification':'gemma4_sglang_transformers_generation_equivalence_terminal','cases':terminal,'branch_decision':decision,'raw_artifact_sha256':{'transformers':hashlib.sha256((out/'transformers_raw.json').read_bytes()).hexdigest(),'sglang':hashlib.sha256((out/'sglang_raw.json').read_bytes()).hexdigest()},'bench_release_state':'ready_requested_without_teardown'})


p=argparse.ArgumentParser();p.add_argument('phase',choices=('direct','sglang'));p.add_argument('--checkpoint');p.add_argument('--base');p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True); direct(Path(a.checkpoint),a.output_dir) if a.phase=='direct' else sglang(a.base,a.output_dir)
