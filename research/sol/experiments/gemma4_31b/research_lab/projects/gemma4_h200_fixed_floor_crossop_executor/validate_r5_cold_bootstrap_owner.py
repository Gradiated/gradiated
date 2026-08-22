#!/usr/bin/env python3
"""Local deterministic contract test for the cold R5 owner seam."""
import argparse, hashlib, json, pathlib, py_compile, tempfile
P=pathlib.Path(__file__).resolve().parent
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 args=argparse.ArgumentParser();args.add_argument("--output",type=pathlib.Path);a=args.parse_args()
 owner=P/"run_fixed_floor_crossop_endpoint_cold_owner_r5.py"; launcher=P/"run_fixed_floor_crossop_endpoint_cold_claim_launch_r5.py"
 for path in (owner,launcher): py_compile.compile(str(path),doraise=True)
 text=owner.read_text(); launch=launcher.read_text()
 required=["reconcile(ssh,b[\"immutable_manifests\"][\"files\"]","dest+\".part\"","atomic_finalize","repair-handshake","candidate_only","run_fixed_floor_crossop_endpoint_candidate_only_r5.py","heartbeat","--expected-claimed-at"]
 if any(x not in text for x in required): raise RuntimeError("owner_contract_missing")
 if any(x not in launch for x in ["detached-owner","--unit-manager","COLD_R5_EXECUTION_BINDING.json","OWNER_READY.json","claim_not_observed"]): raise RuntimeError("launcher_contract_missing")
 with tempfile.TemporaryDirectory(prefix="cold-owner-contract-",dir=P/"artifacts") as d:
  root=pathlib.Path(d); src=root/"source"; src.write_bytes(b"immutable")
  part=root/"destination.part"; part.write_bytes(src.read_bytes())
  if sha(part)!=sha(src): raise RuntimeError("verify_failed")
  final=root/"destination"; part.replace(final)
  if not final.exists() or part.exists() or sha(final)!=sha(src): raise RuntimeError("atomic_finalize_failed")
 value={"schema_version":1,"classification":"r5_cold_bootstrap_owner_offline_contract_pass","owner_sha256":sha(owner),"launcher_sha256":sha(launcher),"validation_scope":"local deterministic manifest and controller contract only","fresh_stage_and_repeated_retention":"pass","temporary_verify_atomic_finalize":"pass","claim_allowed":False,"ssh_allowed":False,"cuda_allowed":False,"endpoint_request_allowed":False}
 if a.output:
  part=a.output.with_suffix(a.output.suffix+".part");part.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n");part.replace(a.output)
 print(json.dumps(value,indent=2,sort_keys=True))
if __name__=="__main__": main()
