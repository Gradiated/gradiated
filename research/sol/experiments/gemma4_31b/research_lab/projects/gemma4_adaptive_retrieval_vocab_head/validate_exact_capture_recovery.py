#!/usr/bin/env python3
import argparse, hashlib, json, tarfile
from pathlib import Path
import torch

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--bundle",type=Path,required=True); p.add_argument("--hidden",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    with tarfile.open(a.bundle) as t:
        manifest=json.load(t.extractfile("hidden_states.manifest.json")); names={x.name for x in t.getmembers() if x.isfile()}
        checks=[]
        for row in manifest["files"]:
            stream=t.extractfile(row["path"]); data=stream.read() if stream else b""
            checks.append({"path":row["path"],"pass":row["path"] in names and len(data)==row["bytes"] and hashlib.sha256(data).hexdigest()==row["sha256"]})
        audit=[json.loads(line) for line in t.extractfile("hidden_states.audit.jsonl").read().decode().splitlines() if line]
        workload=json.load(t.extractfile("c32/WORKLOAD.json")); c32=json.load(t.extractfile("c32/TERMINAL.json")); marker=json.load(t.extractfile("science_started.json"))
    payload=torch.load(a.hidden,map_location="cpu",weights_only=False)
    hidden=payload["hidden_states"]; ownership=payload["ownership"]
    request_ids=[str(x["request_id"]) for x in ownership]
    commits=[x for x in audit if x.get("event")=="target_verify_hidden_rows_committed"]
    result={"schema_version":1,"classification":"trusted_local_exact_capture_consumer","bundle_sha256":sha(a.bundle),"hidden_sha256":sha(a.hidden),"bundle_members_pass":all(x["pass"] for x in checks),"bundle_checks":checks,"payload_schema_version":payload.get("schema_version"),"hidden_shape":list(hidden.shape),"hidden_dtype":str(hidden.dtype),"finite":bool(torch.isfinite(hidden).all().item()),"ownership_rows":len(ownership),"unique_request_ids":len(set(request_ids)),"unique_hidden_rows":int(torch.unique(hidden,dim=0).shape[0]),"audit_commits":len(commits),"audit_rows":sum(int(x.get("rows_added",0)) for x in commits),"workload_requests":len(workload.get("request_sha256",[])),"c32_pass":c32.get("pass") is True,"complete_requests":c32.get("complete_requests"),"science_started":marker.get("science_started") is True}
    result["pass"]=all([result["bundle_members_pass"],result["hidden_shape"]==[1536,5376],result["finite"],result["ownership_rows"]==1536,result["unique_request_ids"]==32,result["unique_hidden_rows"]>=2,result["audit_commits"]==4,result["audit_rows"]==1536,result["workload_requests"]==32,result["c32_pass"],result["complete_requests"]==32,result["science_started"]])
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return 0 if result["pass"] else 2
if __name__=="__main__": raise SystemExit(main())
