#!/usr/bin/env python3
"""The sole fixed 32-request NGRAM wave-admission measurement."""
from __future__ import annotations

import concurrent.futures, hashlib, json, math, statistics, subprocess, threading, time, urllib.request
from pathlib import Path

ROOT = Path('/home/glmrunner/gemma4-ngram-wave-admission')
OUT, INPUT = ROOT / 'out', ROOT / 'inputs' / 'bound'
MODEL = 'google/gemma-4-31B-it'
IMAGE = 'docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6'
CONTAINER = 'gemma4-ngram-wave-admission'
N, WAVE, SPACING = 1036, 32, 0.6946101132986054

def atomic(name, value):
    OUT.mkdir(parents=True, exist_ok=True); p = OUT / name; q = p.with_suffix(p.suffix + '.part')
    q.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n'); q.replace(p)
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(cmd, timeout=180): return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
def get(url, timeout=10): return urllib.request.urlopen(url, timeout=timeout).read()
def metric_snapshot():
    raw = get('http://127.0.0.1:30000/metrics').decode(); values = {}
    wanted = ('sglang:num_queue_reqs','sglang:num_running_reqs','sglang:kv_used_tokens','sglang:kv_available_tokens','sglang:token_usage','sglang:swa_used_tokens','sglang:swa_available_tokens','sglang:spec_accept_rate','sglang:spec_accept_length')
    for line in raw.splitlines():
        if line and not line.startswith('#'):
            name = line.split('{', 1)[0]
            if name in wanted:
                try: values[name] = float(line.rsplit(' ', 1)[1])
                except ValueError: pass
    return values, raw
def post(body):
    native = {'input_ids': body['prompt'], 'sampling_params': {'temperature':0,'max_new_tokens':body['max_tokens'],'min_new_tokens':body['min_tokens'],'ignore_eos':body['ignore_eos']}}
    raw = json.dumps(native, separators=(',', ':')).encode(); req = urllib.request.Request('http://127.0.0.1:30000/generate', raw, {'Content-Type':'application/json'})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=1200) as reply: response = reply.read()
    ended = time.monotonic(); parsed = json.loads(response); meta = parsed.get('meta_info') or {}
    usage = {'prompt_tokens':meta.get('prompt_tokens',len(body['prompt'])),'completion_tokens':meta.get('completion_tokens',body['max_tokens'])}
    usage['total_tokens'] = usage['prompt_tokens'] + usage['completion_tokens']
    ids = parsed.get('output_ids') or meta.get('output_ids') or meta.get('completion_token_ids')
    return {'usage':usage, 'latency_seconds':ended-started, 'raw_sha256':hashlib.sha256(response).hexdigest(), 'output_ids':ids, 'finish_reason':meta.get('finish_reason') or parsed.get('finish_reason'), 'text_sha256':hashlib.sha256(str(parsed.get('text')).encode()).hexdigest()}
def body(template, index):
    value = dict(template['request_body']); value.update({'model':MODEL,'ignore_eos':True,'min_tokens':358,'max_tokens':358,'request_id':f'sustainable-{index}'})
    value['prompt'] = list(value['prompt'])
    if isinstance(index, int): value['prompt'][535] = 200000 + index
    return value
def wait_server():
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            if MODEL.encode() in get('http://127.0.0.1:30000/v1/models', 4): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError('server_not_ready')
def invoke(index, arrival, released, request, expected, origin):
    started = time.monotonic() - origin
    try:
        answer = post(request); complete = time.monotonic() - origin
        request_sha = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        request_semantics = request['prompt'][535] == 200000 + index and len(request['prompt']) == 4214 and request['min_tokens'] == request['max_tokens'] == 358 and request['ignore_eos'] is True
        return {'i':index,'arrival_s':arrival,'released_s':released,'client_started_s':started,'completed_s':complete,'buffer_wait_seconds':released-arrival,'request_sha256':request_sha,'control_request_sha256':expected['request_sha256'],'request_matches_control':request_semantics,'usage':answer['usage'],'usage_matches_control':answer['usage']==expected['usage'],'raw_response_matches_control':answer['raw_sha256']==expected['timing']['raw_sha256'],'raw_response_sha256':answer['raw_sha256'],'output_ids':answer['output_ids'],'text_sha256':answer['text_sha256'],'finish_reason':answer['finish_reason'],'server_seconds':answer['latency_seconds']}
    except Exception as exc:
        return {'i':index,'arrival_s':arrival,'released_s':released,'client_started_s':started,'completed_s':time.monotonic()-origin,'buffer_wait_seconds':released-arrival,'error':repr(exc)}
def sampler(stop, rows, origin):
    while not stop.wait(2):
        row={'elapsed_s':time.monotonic()-origin}
        s=run(['nvidia-smi','--query-gpu=timestamp,utilization.gpu,power.draw,memory.used','--format=csv,noheader,nounits'],20); row['nvidia_smi']=s.stdout.strip()
        try: row['metrics']=metric_snapshot()[0]
        except Exception as e: row['metrics_error']=repr(e)
        rows.append(row)
def percentile(xs, q):
    if not xs: return None
    return sorted(xs)[min(len(xs)-1, math.ceil(q*len(xs))-1)]
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    atomic('INVOCATION_STATE.json', {'science_started':False,'phase':'stock_server_load'})
    checks = json.loads((INPUT/'SHA256SUMS.json').read_text())
    for name, expected in checks.items():
        if digest(INPUT/name) != expected: raise RuntimeError('input_hash_mismatch:'+name)
    trace=json.loads((INPUT/'TRACE_PACKET.json').read_text()); template=next(x for x in trace['primary_groups'] if x['name']=='primary_c1')['scored'][0]
    controls=[json.loads(x) for x in (INPUT/'requests.jsonl').read_text().splitlines()]
    if len(controls)!=N: raise RuntimeError('control_row_count_mismatch')
    launch=json.loads((INPUT/'ngram-launch.json').read_text())['args']
    run(['sudo','docker','rm','-f','gemma4-ngram-state-aging'],60)
    run(['sudo','docker','rm','-f',CONTAINER],60)
    cmd=['sudo','docker','run','-d','--name',CONTAINER,'--gpus','all','--ipc=host','--network','host','-v',f'{ROOT}:/work','-v','/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint:/work/checkpoint:ro',IMAGE,'python3','-m','sglang.launch_server',*launch]
    started_launch=run(cmd,120); atomic('LAUNCH.json', {'command_after_image':cmd[cmd.index(IMAGE)+1:],'returncode':started_launch.returncode,'stdout':started_launch.stdout,'stderr':started_launch.stderr})
    if started_launch.returncode: raise RuntimeError('stock_launch_failed')
    wait_server(); post(body(template, 'warmup'))
    before, raw = metric_snapshot(); (OUT/'metrics-before-primary.prom').write_text(raw)
    atomic('INVOCATION_STATE.json', {'science_started':True,'phase':'wave_admission_primary','requests':N,'full_waves':32,'tail':12})
    origin=time.monotonic(); telemetry=[]; stop=threading.Event(); thread=threading.Thread(target=sampler,args=(stop,telemetry,origin),daemon=True); thread.start()
    rows=[]; waves=[]
    try:
        for first in range(0,N,WAVE):
            end=min(N,first+WAVE); planned=(end-1)*SPACING; due=origin+planned; time.sleep(max(0,due-time.monotonic()))
            released=time.monotonic()-origin; snapshot=metric_snapshot()[0]
            with concurrent.futures.ThreadPoolExecutor(max_workers=end-first) as pool:
                futures=[pool.submit(invoke,i,i*SPACING,released,body(template,i),controls[i],origin) for i in range(first,end)]
                wave_rows=[f.result() for f in futures]
            rows.extend(wave_rows); completed=max(x['completed_s'] for x in wave_rows); valid=[x for x in wave_rows if 'error' not in x]
            waves.append({'wave_index':len(waves),'request_begin':first,'request_end_exclusive':end,'planned_release_s':planned,'actual_release_s':released,'release_drift_seconds':released-planned,'server_completion_s':completed,'server_span_seconds':completed-released,'upstream_queue_depth':snapshot.get('sglang:num_queue_reqs'),'upstream_queue_age_seconds':max(x['buffer_wait_seconds'] for x in wave_rows),'cache_realization':snapshot,'completed':len(valid),'failures':len(wave_rows)-len(valid)})
    finally:
        stop.set(); thread.join(5)
    after, raw=metric_snapshot(); (OUT/'metrics-after-primary.prom').write_text(raw)
    rows.sort(key=lambda x:x['i']); (OUT/'requests.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows)); (OUT/'waves.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in waves)); (OUT/'telemetry.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n' for x in telemetry))
    valid=[x for x in rows if 'error' not in x]; failures=[x for x in rows if 'error' in x]; elapsed=max(x['completed_s'] for x in rows); total=sum(x['usage']['total_tokens'] for x in valid); costs=3.25*(elapsed/3600)/(total/1e6) if total else None
    completion=[x['completed_s']-x['arrival_s'] for x in valid]; final_backlog=max(0.0, elapsed-(N-1)*SPACING)
    decision={'all_complete':len(valid)==N,'exact_request_semantics':all(x['request_matches_control'] for x in valid),'exact_response_semantics':all(x['raw_response_matches_control'] for x in valid),'exact_usage':all(x['usage_matches_control'] for x in valid),'no_release_miss':all(x['release_drift_seconds']<=SPACING for x in waves),'final_upstream_backlog_zero':final_backlog==0.0,'failures_zero':not failures,'planning_cost_at_or_below_target':costs is not None and costs<=0.14}
    terminal={'result':'measured_ngram_wave_admission','candidate_science_consumed':True,'identity':{'image':IMAGE,'model':MODEL,'launch_sha256':digest(INPUT/'ngram-launch.json'),'request_rows_sha256':digest(INPUT/'requests.jsonl'),'trace_sha256':digest(INPUT/'TRACE_PACKET.json')},'primary':{'requests':N,'waves':len(waves),'full_waves':32,'tail_requests':12,'elapsed_seconds':elapsed,'total_tokens':total,'failures':failures,'final_upstream_backlog_seconds':final_backlog,'completion_seconds':{'mean':statistics.mean(completion) if completion else None,'p95':percentile(completion,.95),'max':max(completion) if completion else None},'planning_cost_usd_per_million_total_tokens':costs,'gpu_samples':len(telemetry),'metrics_before':before,'metrics_after':after},'decision':decision,'retain_wave_admission':all(decision.values())}
    atomic('FINAL_TERMINAL.json',terminal)
if __name__ == '__main__':
    try: main()
    except Exception as exc:
        atomic('ATTEMPT_TERMINAL.json',{'classification':'recoverable_or_typed_remote_failure','error':repr(exc),'candidate_science_consumed':False}); raise
