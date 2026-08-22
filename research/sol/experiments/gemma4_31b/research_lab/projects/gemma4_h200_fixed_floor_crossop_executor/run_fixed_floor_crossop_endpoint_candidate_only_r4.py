#!/usr/bin/env python3
"""The sole R4 science consumer: candidate traffic only, compared to frozen SSE bytes."""
import argparse, concurrent.futures, hashlib, json, pathlib, subprocess, time, urllib.request
from run_fixed_floor_crossop_endpoint_pair import IMAGE, MODEL, CONCURRENCY, workload, canonical
def put(p,v):
 q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); q.replace(p)
def parse(raw):
 chunks=[]; finish=[]; usage=[]; n=0
 for line in raw.splitlines():
  if not line.startswith(b'data: ') or line==b'data: [DONE]': continue
  n+=1; item=json.loads(line[6:]); c=(item.get('choices') or [{}])[0]
  if c.get('text'): chunks.append(c['text'])
  if c.get('finish_reason') is not None: finish.append(c.get('finish_reason'))
  if item.get('usage') is not None: usage.append(item['usage'])
 return {'sse_events':n,'chunks':chunks,'finish_reason':finish,'usage':usage}
def request(url,body):
 start=time.monotonic(); raw=b''
 try:
  with urllib.request.urlopen(urllib.request.Request(url+'/v1/chat/completions',data=canonical(body),headers={'Content-Type':'application/json'}),timeout=600) as r:
   raw=r.read()
  return raw,{'error':None,'wall_seconds':time.monotonic()-start,'request_sha256':hashlib.sha256(canonical(body)).hexdigest()}
 except Exception as e:return raw,{'error':type(e).__name__+': '+str(e),'wall_seconds':time.monotonic()-start,'request_sha256':hashlib.sha256(canonical(body)).hexdigest()}
def main():
 a=argparse.ArgumentParser(); a.add_argument('--project',type=pathlib.Path,required=True); a.add_argument('--checkpoint',type=pathlib.Path,required=True); a.add_argument('--oracle',type=pathlib.Path,required=True); a.add_argument('--output',type=pathlib.Path,required=True); a.add_argument('--port',type=int,default=30001); z=a.parse_args()
 if z.output.exists(): raise SystemExit('fresh_candidate_output_required')
 z.output.mkdir(parents=True); name='gemma4-fixed-floor-candidate-r4'; url='http://127.0.0.1:'+str(z.port)
 cmd=['sudo','-n','docker','run','-d','--name',name,'--gpus','all','--ipc=host','--network=host','-v',f'{z.project}:/work/project:ro','-v',f'{z.checkpoint}:/work/checkpoint:ro','-v',f'{z.output}:/work/output','-v',f'{z.project}/endpoint_candidate_gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro','-e','PYTHONPATH=/work/project:/sgl-workspace/sglang/python','-e','FIXED_FLOOR_CROSSOP_AUDIT=/work/output/candidate-path.jsonl',IMAGE,'python3','-m','sglang.launch_server','--model-path','/work/checkpoint','--tokenizer-path','/work/checkpoint','--served-model-name',MODEL,'--dtype','bfloat16','--quantization','fp8','--tp-size','1','--kv-cache-dtype','fp8_e5m2','--host','0.0.0.0','--port',str(z.port),'--context-length','5000','--max-running-requests','32','--mem-fraction-static','0.85','--skip-server-warmup','--enable-dynamic-chunking','--chunked-prefill-size','2048','--enable-fused-qk-norm-rope','--cuda-graph-max-bs','32','--prefill-attention-backend','triton','--decode-attention-backend','triton','--page-size','1','--num-continuous-decode-steps','1','--tool-call-parser','gemma4']
 launch=subprocess.run(cmd,text=True,capture_output=True,timeout=120); put(z.output/'launch.json',{'returncode':launch.returncode,'stderr':launch.stderr})
 if launch.returncode: raise RuntimeError('candidate_launch_failed')
 try:
  for _ in range(180):
   running=subprocess.run(['sudo','-n','docker','inspect','-f','{{.State.Running}}',name],text=True,capture_output=True,timeout=20)
   if running.returncode or running.stdout.strip()!='true': raise RuntimeError('candidate_server_exited_before_ready')
   try:
    if MODEL in urllib.request.urlopen(url+'/v1/models',timeout=5).read().decode(): break
   except Exception: pass
   time.sleep(2)
  else: raise RuntimeError('candidate_server_readiness_timeout')
  started=time.monotonic()
  with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool: results=list(pool.map(lambda b:request(url,b),workload()))
  oracle=json.loads(z.oracle.read_text()); rows=[]; exact=True
  for i,(raw,row) in enumerate(results):
   (z.output/f'response-{i:02d}.sse').write_bytes(raw); observed=parse(raw); expected=oracle['rows'][i]; match=(not row['error'] and observed['chunks']==expected['chunks'] and observed['finish_reason']==expected['finish_reason'] and observed['usage']==expected['usage'] and observed['sse_events']==expected['sse_events']); exact &= match; rows.append({**row,**observed,'exact_emitted_chunk_match':match})
  audit=(z.output/'candidate-path.jsonl').read_text().splitlines() if (z.output/'candidate-path.jsonl').exists() else []
  proof={json.loads(x).get('class') for x in audit}
  put(z.output/'PAIR_TERMINAL.json',{'schema_version':1,'classification':'candidate_only_exact_emitted_chunk_endpoint','science_consumed':True,'valid':bool(exact and len(rows)==32 and proof=={'local','global'}),'candidate':{'complete_requests':sum(not r['error'] for r in rows),'service_seconds_per_request':(time.monotonic()-started)/32,'rows':rows},'candidate_local_global_proof':sorted(proof),'oracle_sha256':hashlib.sha256(z.oracle.read_bytes()).hexdigest()})
 finally:
  logs=subprocess.run(['sudo','-n','docker','logs',name],text=True,capture_output=True,timeout=120); (z.output/'server.stdout').write_text(logs.stdout); (z.output/'server.stderr').write_text(logs.stderr); subprocess.run(['sudo','-n','docker','rm','-f',name],text=True,capture_output=True,timeout=120)
if __name__=='__main__': main()
