#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path('/home/glmrunner/gemma4-h200-ngram-sequential-validation')
INPUT = ROOT / 'input'
OUT = ROOT / 'artifacts'
CHECKPOINT = '/home/glmrunner/gemma4-async-result-pipeline/checkpoint'
IMAGE = 'docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
MODEL = 'google/gemma-4-31B-it'
BASE = ['--model-path','/work/checkpoint','--tokenizer-path','/work/checkpoint','--served-model-name',MODEL,'--dtype','bfloat16','--quantization','fp8','--tp-size','1','--kv-cache-dtype','fp8_e5m2','--host','0.0.0.0','--context-length','5000','--max-running-requests','32','--mem-fraction-static','0.85','--enable-metrics','--skip-server-warmup','--enable-dynamic-chunking','--chunked-prefill-size','2048','--enable-fused-qk-norm-rope','--cuda-graph-max-bs','32','--prefill-attention-backend','triton','--decode-attention-backend','triton','--page-size','1','--num-continuous-decode-steps','1','--triton-attention-num-kv-splits','8','--tool-call-parser','gemma4']

def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temp.replace(path)

def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)

def wait(port: int) -> None:
    for _ in range(240):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=5) as response:
                if MODEL in response.read().decode(): return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f'model_readiness_timeout:{port}')

def post(port: int, body: dict) -> dict:
    raw = json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode()
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=raw, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())

def ids(response: dict) -> list[int]:
    meta = response.get('meta_info') or {}
    rows = meta.get('output_token_logprobs') or meta.get('token_ids') or []
    result = []
    for row in rows:
        if isinstance(row, int): result.append(row)
        elif isinstance(row, dict) and isinstance(row.get('token_id'), int): result.append(row['token_id'])
        elif isinstance(row, (list, tuple)):
            values = [item for item in row if isinstance(item, int)]
            if values: result.append(values[-1])
    return result

def compact(response: dict) -> dict:
    choice = (response.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    return {'token_ids': ids(response), 'content': message.get('content'), 'tool_calls': message.get('tool_calls'), 'finish_reason': choice.get('finish_reason'), 'usage': response.get('usage'), 'raw_sha256': hashlib.sha256(json.dumps(response, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}

def cases() -> list[dict]:
    text = [{'id':'ordinary','body':{'model':MODEL,'messages':[{'role':'user','content':'State the capital of France in one word.'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'stop_length','body':{'model':MODEL,'messages':[{'role':'user','content':'Reply exactly with OK.'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'cached_prefix','body':{'model':MODEL,'messages':[{'role':'system','content':'You are concise. Reply with only the requested word.'},{'role':'user','content':'What color is a clear daytime sky?'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}, {'id':'repeated_pattern','body':{'model':MODEL,'messages':[{'role':'user','content':'Continue this pattern with four letters: ababab'}],'temperature':0,'seed':20260718,'max_tokens':16,'return_logprob':True,'top_logprobs_num':1}}]
    tools = [{'type':'function','function':{'name':'lookup_user','description':'Look up a user by id.','parameters':{'type':'object','properties':{'user_id':{'type':'string'}},'required':['user_id']}}}, {'type':'function','function':{'name':'get_user_details','description':'Get details for a user.','parameters':{'type':'object','properties':{'user_id':{'type':'string'}},'required':['user_id']}}}]
    return text + [{'id':'single_tool','body':{'model':MODEL,'messages':[{'role':'user','content':'Call lookup_user for user_id demo_user.'}],'tools':tools,'tool_choice':'required','temperature':0,'seed':20260718,'max_tokens':128}}, {'id':'multi_tool','body':{'model':MODEL,'messages':[{'role':'user','content':'Call lookup_user for user_id demo_user, then get_user_details for user_id demo_user. Use both tools in that order.'}],'tools':tools,'tool_choice':'required','temperature':0,'seed':20260718,'max_tokens':128}}]

def launch(arm: str, port: int, ngram: bool) -> str:
    name = f'gemma-ngram-sequential-{arm}'
    run(['sudo','docker','rm','-f',name])
    env = ['-e','PYTHONPATH=/work/input:/sgl-workspace/sglang/python','-e',f'FP8_MODULE_AUDIT=/work/artifacts/{arm}.modules.jsonl','-e',f'FP8_CONSUMER_AUDIT=/work/artifacts/{arm}.consumers.jsonl','-e',f'FP8_RUNTIME_AUDIT=/work/artifacts/{arm}.runtime.json','-e',f'FP8_STACK_MODULE_AUDIT=/work/artifacts/{arm}.stack-modules.jsonl','-e',f'FP8_STACK_CONSUMER_AUDIT=/work/artifacts/{arm}.stack-consumers.jsonl']
    args = BASE + ['--port',str(port)] + (['--speculative-algorithm','NGRAM'] if ngram else [])
    result = run(['sudo','docker','run','-d','--name',name,'--gpus','all','--ipc=host','--network','host','-v',f'{ROOT}:/work','-v',f'{INPUT}:/work/input:ro','-v',f'{CHECKPOINT}:/work/checkpoint:ro',*env,IMAGE,'python3','/work/input/endpoint_entrypoint.py',*args])
    atomic(OUT / f'{arm}-launch.json', {'args':args,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'name':name})
    if result.returncode: raise RuntimeError(f'launch_failed:{arm}:{result.stderr[-800:]}')
    wait(port)
    return name

def capture(arm: str, port: int) -> dict:
    raw = []
    work = cases()
    for case in work:
        response = post(port, case['body']); raw.append({'mode':'serial','id':case['id'],'request':case['body'],'response':response,'compact':compact(response)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda case: post(port, case['body']), work[:4]))
    for case, response in zip(work[:4], responses): raw.append({'mode':'batched','id':case['id'],'request':case['body'],'response':response,'compact':compact(response)})
    atomic(OUT / f'{arm}-raw-events.json', raw)
    return {'rows':raw,'metrics':run(['curl','-fsS',f'http://127.0.0.1:{port}/metrics']).stdout}

def empty_proof() -> dict:
    result = run(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader'])
    memory = run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader'])
    return {'compute_query_returncode':result.returncode,'compute_processes':result.stdout.strip(),'gpu':memory.stdout.strip(),'zero':not result.stdout.strip() and memory.stdout.strip().startswith('0 MiB')}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(OUT / 'INVOCATION_STATE.json', {'control_science_started':False,'candidate_science_started':False})
    control = launch('control',30000,False)
    state=json.loads((OUT/'INVOCATION_STATE.json').read_text()); state['control_science_started']=True; atomic(OUT/'INVOCATION_STATE.json',state)
    control_capture=capture('control',30000); atomic(OUT/'CONTROL_STAGE.json',control_capture)
    run(['sudo','docker','rm','-f',control]); time.sleep(3); zero=empty_proof(); atomic(OUT/'ZERO_HBM_AFTER_CONTROL.json',zero)
    if not zero['zero']: raise RuntimeError(f'control_cleanup_not_zero:{zero}')
    candidate = launch('candidate',30000,True)
    source=run(['sudo','docker','exec',candidate,'python3','-c',"import inspect,hashlib; from sglang.srt.speculative.ngram_worker import NGRAMWorker; s=inspect.getsource(NGRAMWorker); print(hashlib.sha256(s.encode()).hexdigest()); print('target_worker.forward_batch_generation(batch, is_verify=True)' in s); print('verify_input.verify(' in s)"])
    inspect_args=run(['sudo','docker','inspect',candidate,'--format','{{json .Config.Cmd}}'])
    atomic(OUT/'CANDIDATE_PATH_PROOF.json',{'source_stdout':source.stdout,'source_stderr':source.stderr,'source_returncode':source.returncode,'command':inspect_args.stdout,'no_assistant_model':'speculative-draft-model-path' not in inspect_args.stdout})
    state=json.loads((OUT/'INVOCATION_STATE.json').read_text()); state['candidate_science_started']=True; atomic(OUT/'INVOCATION_STATE.json',state)
    candidate_capture=capture('candidate',30000); atomic(OUT/'CANDIDATE_STAGE.json',candidate_capture)
    def index(rows: list[dict]) -> dict: return {(r['mode'],r['id']):r['compact'] for r in rows}
    c=index(control_capture['rows']); n=index(candidate_capture['rows'])
    text_keys=[('serial',x['id']) for x in cases()[:4]]; tool_keys=[('serial','single_tool'),('serial','multi_tool')]
    exact=all(c[k]==n[k] and bool(c[k]['token_ids']) for k in c)
    stable=all(c[('serial',x['id'])]==c[('batched',x['id'])] and n[('serial',x['id'])]==n[('batched',x['id'])] for x in cases()[:4])
    tools=all(c[k]['tool_calls']==n[k]['tool_calls'] and c[k]['finish_reason']=='tool_calls' and n[k]['finish_reason']=='tool_calls' for k in tool_keys)
    proof=json.loads((OUT/'CANDIDATE_PATH_PROOF.json').read_text())
    path=proof['source_returncode']==0 and 'True\nTrue' in proof['source_stdout'] and proof['no_assistant_model']
    terminal={'schema_version':1,'classification':'sequential_native_ngram_token_tool_equivalence','pass':exact and stable and tools and path,'exact_token_and_response_identity':exact,'serial_batched_stable':stable,'native_tool_equal':tools,'target_verification_and_no_assistant':path,'control_rows':len(c),'candidate_rows':len(n),'candidate_scientific_invocation_started':True}
    atomic(OUT/'TERMINAL.json',terminal)
    run(['sudo','docker','rm','-f',candidate])

if __name__ == '__main__': main()
