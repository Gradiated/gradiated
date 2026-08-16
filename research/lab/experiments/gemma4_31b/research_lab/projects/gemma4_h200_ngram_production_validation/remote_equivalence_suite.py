#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import inspect
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path('/home/glmrunner/gemma4-h200-ngram-speculative-endpoint')
OUT = ROOT / 'ngram-production-validation'
IMAGE = 'docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
MODEL = 'google/gemma-4-31B-it'

BASE = ['--model-path','/work/checkpoint','--tokenizer-path','/work/checkpoint','--served-model-name',MODEL,'--dtype','bfloat16','--quantization','fp8','--tp-size','1','--kv-cache-dtype','fp8_e5m2','--host','0.0.0.0','--context-length','5000','--max-running-requests','32','--mem-fraction-static','0.85','--enable-metrics','--skip-server-warmup','--enable-dynamic-chunking','--chunked-prefill-size','2048','--enable-fused-qk-norm-rope','--cuda-graph-max-bs','32','--prefill-attention-backend','triton','--decode-attention-backend','triton','--page-size','1','--num-continuous-decode-steps','1','--triton-attention-num-kv-splits','8']

def put(name: str, value: object) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False)

def wait(port: int) -> None:
    for _ in range(180):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=5) as r:
                if MODEL in r.read().decode(): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError(f'server_not_ready:{port}')

def post(port: int, body: dict) -> dict:
    raw = json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=raw, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())

def token_ids(value: object) -> list[int]:
    found: list[int] = []
    def visit(x: object) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in {'token_id','id'} and isinstance(v, int): found.append(v)
                else: visit(v)
        elif isinstance(x, list):
            for v in x: visit(v)
    meta = value.get('meta_info', {}) if isinstance(value, dict) else {}
    visit(meta.get('output_token_logprobs', meta.get('token_ids', [])))
    return found

def summary(response: dict) -> dict:
    choice = (response.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    return {'token_ids': token_ids(response), 'content': message.get('content'), 'tool_calls': message.get('tool_calls'), 'finish_reason': choice.get('finish_reason'), 'usage': response.get('usage'), 'raw_sha256': hashlib.sha256(json.dumps(response, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}

def request_case(case: dict, port: int) -> dict:
    return summary(post(port, case['body']))

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = run(['sudo','docker','exec','gemma-ngram-pair','python3','-c',"import inspect,hashlib; from sglang.srt.speculative.ngram_worker import NGRAMWorker; s=inspect.getsource(NGRAMWorker); print(hashlib.sha256(s.encode()).hexdigest()); print('target_worker.forward_batch_generation(batch, is_verify=True)' in s); print('verify_input.verify(' in s)"])
    put('SOURCE_BINDING.json', {'returncode':source.returncode,'stdout':source.stdout,'stderr':source.stderr})
    name, port = 'gemma-ngram-control', 30001
    run(['sudo','docker','rm','-f',name])
    args = BASE + ['--port',str(port)]
    env = ['-e','PYTHONPATH=/work/input:/sgl-workspace/sglang/python','-e',f'FP8_MODULE_AUDIT=/work/ngram-production-validation/{name}.modules.jsonl','-e',f'FP8_CONSUMER_AUDIT=/work/ngram-production-validation/{name}.consumers.jsonl','-e',f'FP8_RUNTIME_AUDIT=/work/ngram-production-validation/{name}.runtime.json','-e',f'FP8_STACK_MODULE_AUDIT=/work/ngram-production-validation/{name}.stack-modules.jsonl','-e',f'FP8_STACK_CONSUMER_AUDIT=/work/ngram-production-validation/{name}.stack-consumers.jsonl']
    launched = run(['sudo','docker','run','-d','--name',name,'--gpus','all','--ipc=host','--network','host','-v',f'{ROOT}:/work','-v','/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint:/work/checkpoint:ro',*env,IMAGE,'python3','/work/input/endpoint_entrypoint.py',*args])
    if launched.returncode: raise RuntimeError(f'launch_failed:{name}:{launched.stderr[-1000:]}')
    wait(port)
    text_cases = [{'id':'ordinary','body':{'model':MODEL,'messages':[{'role':'user','content':'State the capital of France in one word.'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'stop','body':{'model':MODEL,'messages':[{'role':'user','content':'Reply exactly with OK.'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'cached-prefix','body':{'model':MODEL,'messages':[{'role':'system','content':'You are concise. Reply with only the requested word.'},{'role':'user','content':'What color is a clear daytime sky?'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'repeated-pattern','body':{'model':MODEL,'messages':[{'role':'user','content':'Continue this pattern with four letters: ababab'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}]
    tools = [{'type':'function','function':{'name':'lookup_user','description':'Look up a user by id.','parameters':{'type':'object','properties':{'user_id':{'type':'string'}},'required':['user_id']}}}, {'type':'function','function':{'name':'get_user_details','description':'Get details for a user.','parameters':{'type':'object','properties':{'user_id':{'type':'string'}},'required':['user_id']}}}]
    tool_cases = [{'id':'single-tool','body':{'model':MODEL,'messages':[{'role':'user','content':'Call lookup_user for user_id demo_user.'}],'tools':tools,'tool_choice':'required','temperature':0,'seed':20260718,'max_tokens':128}}, {'id':'multi-tool','body':{'model':MODEL,'messages':[{'role':'user','content':'Call lookup_user for user_id demo_user, then get_user_details for user_id demo_user. Use both tools in that order.'}],'tools':tools,'tool_choice':'required','temperature':0,'seed':20260718,'max_tokens':128}}]
    rows=[]
    for mode, cases in [('serial-text', text_cases), ('serial-tool', tool_cases)]:
        for case in cases:
            c=request_case(case,30001); n=request_case(case,30000)
            rows.append({'mode':mode,'id':case['id'],'control':c,'candidate':n,'exact':c==n,'token_ids_present':bool(c['token_ids']) and bool(n['token_ids'])})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        control=list(ex.map(lambda c: request_case(c,30001), text_cases)); candidate=list(ex.map(lambda c: request_case(c,30000), text_cases))
    for case,c,n in zip(text_cases,control,candidate): rows.append({'mode':'batched-text','id':case['id'],'control':c,'candidate':n,'exact':c==n,'token_ids_present':bool(c['token_ids']) and bool(n['token_ids'])})
    metrics = {name: run(['curl','-fsS',f'http://127.0.0.1:{port}/metrics']).stdout for name,port in [('candidate',30000),('control',30001)]}
    put('RAW_SUITE.json', {'rows':rows,'metrics':metrics})
    gate = all(row['exact'] and row['token_ids_present'] for row in rows)
    put('TERMINAL.json', {'schema_version':1,'classification':'native_ngram_token_and_tool_equivalence','pass':gate,'rows':len(rows),'exact_rows':sum(r['exact'] for r in rows),'token_id_rows':sum(r['token_ids_present'] for r in rows),'candidate_cuda_scientific_invocation_started':True,'candidate_ngram_server':'gemma-ngram-pair','control_server':'gemma-ngram-control','source_binding':'SOURCE_BINDING.json'})

if __name__ == '__main__': main()
