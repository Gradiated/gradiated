#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,pathlib,py_compile,shutil,subprocess,sys
P=pathlib.Path(__file__).resolve().parent
def digest(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(16*1024*1024),b""):h.update(b)
 return h.hexdigest()
def main():
 b=json.loads((P/"CHECKPOINT_SOURCE_BINDING.json").read_text()); m=json.loads((P/b["manifest"]).read_text()); source=pathlib.Path(b["source_root"])
 rows=[]
 for r in m["checkpoint_files"]:
  q=source/r["path"]; ok=q.is_file() and q.stat().st_size==r["bytes"] and digest(q)==r["sha256"]; rows.append({"path":r["path"],"bytes":r["bytes"],"sha256":r["sha256"],"match":ok})
 if sum(x["bytes"] for x in rows)!=b["checkpoint_bytes"] or not all(x["match"] for x in rows): raise RuntimeError("checkpoint_source_binding_failed")
 py_compile.compile(str(P/"checkpoint_transfer_controller.py"),doraise=True)
 if shutil.which("sftp") is None: raise RuntimeError("sftp_unavailable")
 out={"schema_version":1,"status":"terminal","classification":"staging_ready","pass":True,"checkpoint_source_binding":b,"files":rows,"controller_sha256":digest(P/"checkpoint_transfer_controller.py"),"controller_compile":"pass","parallel_weight_shards":2,"no_provider_mutation":True}
 (P/"STAGING_READY.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
if __name__=="__main__":main()
