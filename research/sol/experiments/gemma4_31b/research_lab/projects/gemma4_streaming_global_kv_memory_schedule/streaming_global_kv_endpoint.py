#!/usr/bin/env python3
"""Run only the candidate-marked exact c32 endpoint and bind layer-35 proof."""
from __future__ import annotations
import json, os, pathlib, subprocess, sys

root=pathlib.Path(os.environ['STREAMING_GLOBAL_KV_OUTPUT_ROOT'])
runner=pathlib.Path('/home/glmrunner/streaming-global-kv/input/exact_runner.py')
telemetry=pathlib.Path(os.environ.get('GLOBAL_KV_TELEMETRY', root/'candidate-telemetry.jsonl'))
if os.environ.get('STREAMING_GLOBAL_KV_CANDIDATE_SERVER') != '1':
    raise RuntimeError('candidate_server_activation_proof_missing')
root.mkdir(parents=True, exist_ok=False)
result=subprocess.run([sys.executable,str(runner),'--output',str(root/'exact-c32'),'--arm','streamed-candidate','--concurrency','32'],text=True,capture_output=True,check=False)
(root/'endpoint.stdout').write_text(result.stdout); (root/'endpoint.stderr').write_text(result.stderr)
if result.returncode: raise RuntimeError(f'exact_candidate_endpoint_exit:{result.returncode}')
rows=[json.loads(line) for line in telemetry.read_text().splitlines() if line.strip()]
matches=[row for row in rows if row.get('layer_id')==35 and row.get('candidate_path')=='u8_streamed']
if not matches: raise RuntimeError('layer35_candidate_path_proof_missing')
(root/'LAYER35_PASSAGE.json').write_text(json.dumps({'schema_version':1,'layer_id':35,'candidate_path':'u8_streamed','rows':matches},indent=2,sort_keys=True)+'\n')
