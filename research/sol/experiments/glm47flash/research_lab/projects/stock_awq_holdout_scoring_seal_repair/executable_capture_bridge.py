#!/usr/bin/env python3
"""Ingest the immutable r4 seven-file captures and bind the corrected runner contract."""
import hashlib,json,re,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ADJ=ROOT.parent/'bf16_v2_capture_adjudication'/'adjudicate_bf16_v2_capture.py'
ARCH=ROOT.parent/'bf16_vllm_quality_bridge'/'artifacts'/'nebius_h100_bf16_vllm_v2_2026-07-15-r4'/'vllm-awq-batch.tar.gz'
RUNNER=ROOT.parents[2]/'campaign_100'/'nebius'/'vllm_v2_quality_runner.py'
REQ={'raw-response-bytes','normalized-output-bytes','transform-decisions','responses.jsonl','runtime-evidence.json','identity-manifest.json','capture-result.json'}
def sha(b):return hashlib.sha256(b).hexdigest()
def read(t,n):
 f=t.extractfile(n)
 if not f: raise ValueError('missing:'+n)
 return f.read()
def main():
 with tempfile.TemporaryDirectory() as d:
  result=Path(d)/'adjudication.json'; p=subprocess.run([sys.executable,str(ADJ),'--output',str(result)],capture_output=True,text=True,timeout=120)
  if p.returncode: raise ValueError('adjudicator:'+p.stderr[-500:])
  adjudication=json.loads(result.read_text())
 with tarfile.open(ARCH) as t:
  members={m.name for m in t.getmembers() if m.isfile()}; manifest=json.loads(read(t,'bf16-v2-quality/manifest.json')); rows={x['path']:x for x in manifest}
  if len(rows)!=len(manifest):raise ValueError('archive_manifest_duplicate')
  for path,x in rows.items():
   b=read(t,'bf16-v2-quality/'+path)
   if x['bytes']!=len(b) or x['sha256']!=sha(b):raise ValueError('archive_manifest:'+path)
  pids=[]
  for i,name in enumerate(('server.stdout.log','server-2.stdout.log','server-3.stdout.log'),1):
   text=read(t,'bf16-v2-quality/'+name).decode(errors='replace'); found=re.search(r'APIServer pid=(\d+)',text)
   if not found:raise ValueError('process_identity:'+name)
   pids.append(int(found.group(1)))
   have={x.rsplit('/',1)[-1] for x in members if x.startswith(f'bf16-v2-quality/capture-{i}/')}
   if not REQ<=have:raise ValueError('seven_file_capture:'+str(i))
  if len(set(pids))!=3:raise ValueError('fresh_process_identity')
 output={'status':'HOLDOUT_EXECUTABLE_BRIDGE_PASS','archive_sha256':sha(ARCH.read_bytes()),'r4_adjudication_gate':adjudication['gate']['pass'],'r4_category_repeatability':adjudication['category_repeatability'],'r4_nll_ceilings_sha256':sha((ROOT.parent/'bf16_v2_capture_adjudication'/'BF16_V2_NLL_CEILINGS.json').read_bytes()),'seven_file_captures':[1,2,3],'fresh_api_server_pids':pids,'runner_sha256':sha(RUNNER.read_bytes()),'runner_contract':'returns actual prompt_token_ids and SHA-256 canonical ID serialization; request endpoint/payload and finish reason are per-case evidence'}
 if not output['r4_adjudication_gate']:raise ValueError('r4_adjudication_gate')
 (ROOT/'EXECUTABLE_CAPTURE_BRIDGE.json').write_text(json.dumps(output,sort_keys=True,indent=2)+'\n');print(json.dumps(output,sort_keys=True))
if __name__=='__main__':main()
