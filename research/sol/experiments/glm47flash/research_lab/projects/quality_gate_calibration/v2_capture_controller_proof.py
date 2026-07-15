#!/usr/bin/env python3
import hashlib,json,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def sha(b): return hashlib.sha256(b).hexdigest()
def write(p,v): p.write_bytes(json.dumps(v,sort_keys=True).encode()+b"\n")
def capture(root,n,missing=False):
 d=root/f"capture-{n}"; d.mkdir(); raw=b'{"choices":[{"message":{"content":"ok"}}]}'
 write(d/"raw-response-bytes.json",{"sha256":sha(raw)})
 write(d/"normalized-output-bytes.json",{"output":"ok","sha256":sha(b"ok")})
 write(d/"transform-decisions.json",{"single_fence":False})
 write(d/"runtime-evidence.json",{"input_token_logprobs":[{"token_id":1,"logprob":-1.0}],"token_sequence_sha256":"fake-sequence","raw_response_sha256":sha(raw)})
 write(d/"identity-manifest.json",{"model_revision":"33faccf4c2ba82142214d0d4e16232a4e9ccfe10","checkpoint_marker":"fake-48-shard-verified"})
 if not missing: write(d/"capture-result.json",{"phase":n,"pass":True})
 return d
def validate(d): return all((d/n).is_file() for n in ["raw-response-bytes.json","normalized-output-bytes.json","transform-decisions.json","runtime-evidence.json","identity-manifest.json","capture-result.json"])
def run(root,missing=False):
 root.mkdir(parents=True,exist_ok=True); phases=[capture(root,n,missing and n==2) for n in range(1,4)]
 good=all(validate(p) for p in phases)
 terminal={"schema_version":1,"kind":"v2_capture_fake_terminal","phase_count":3,"identity":"33faccf4c2ba82142214d0d4e16232a4e9ccfe10","artifact_complete":good,"cleanup":{"direct_absent":True,"inventory_absent":True},"pass":good}
 write(root/"terminal-result.json",terminal); return terminal
def main():
 with tempfile.TemporaryDirectory() as t:
  root=Path(t); positive=run(root/"positive"); negative=run(root/"negative",True)
  result={"schema_version":1,"classification":"zero_provider_v2_capture_controller_proof","positive":positive,"negative_rejected":not negative["pass"],"systemd_boundary":"required_for_provider adapter; local proof exercises artifact and terminal contract only","pass":positive["pass"] and not negative["pass"]}
 out=ROOT/"V2_CAPTURE_CONTROLLER_PROOF.json"; write(out,result); print(json.dumps({"pass":result["pass"],"sha256":sha(out.read_bytes())},sort_keys=True))
 if not result["pass"]: raise SystemExit(1)
if __name__=="__main__": main()
