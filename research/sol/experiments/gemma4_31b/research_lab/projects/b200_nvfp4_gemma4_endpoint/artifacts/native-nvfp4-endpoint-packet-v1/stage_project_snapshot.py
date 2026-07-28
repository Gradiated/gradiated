#!/usr/bin/env python3
"""Atomically admit the project-local BF16 snapshot before one conversion."""
import argparse, hashlib, json, os, pathlib, shutil
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--root",type=pathlib.Path,required=True);a=p.parse_args();packet=a.root/"packet"; identities=json.loads((packet/"IDENTITIES.json").read_text()); source=a.root/"inputs"/"bf16-source"; target=a.root/"bf16-source"; temporary=a.root/"bf16-source.tmp"
 if target.exists(): raise SystemExit("immutable_bf16_source_already_finalized")
 if temporary.exists(): raise SystemExit("staging_tmp_requires_reconciliation")
 temporary.mkdir(parents=True)
 for row in identities["checkpoint"]["files"]:
  src=source/row["path"]; dst=temporary/row["path"]; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
  if dst.stat().st_size != row["bytes"] or sha(dst) != row["sha256"]: raise SystemExit("checkpoint_manifest_mismatch:"+row["path"])
 os.replace(temporary,target)
 (target/"PROJECT_LOCAL_SOURCE_MANIFEST.json").write_text(json.dumps({"source_manifest_sha256":identities["checkpoint"]["source_manifest_sha256"],"files":identities["checkpoint"]["files"]},sort_keys=True,indent=2))
if __name__=="__main__": main()
