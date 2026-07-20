#!/usr/bin/env python3
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, pathlib, shlex, subprocess, time

PROJECT=pathlib.Path(__file__).resolve().parent
KEY=pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN=pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")

def sha256(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(16*1024*1024),b""): h.update(b)
    return h.hexdigest()
def atomic(path: pathlib.Path,value: object) -> None:
    q=path.with_suffix(path.suffix+".part"); q.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); os.replace(q,path)
def ssh(ip: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ip}",command],text=True,capture_output=True,timeout=timeout)
def transfer(ip: str, root: str, source: pathlib.Path, row: dict, artifacts: pathlib.Path) -> dict:
    name=row["path"]; expected=row["sha256"]; partial=f"{root}/checkpoint/.{name}.{expected}.part"; final=f"{root}/checkpoint/{name}"
    matched=ssh(ip,f"test -f {shlex.quote(final)} && test \"$(sha256sum {shlex.quote(final)}|awk '{{print $1}}')\" = {expected}",120)
    if matched.returncode==0: return {"name":name,"status":"already_matched","bytes":row["bytes"],"sha256":expected,"seconds":0.0}
    started=time.monotonic()
    batch=artifacts/f".{name}.sftp"
    batch.write_text(f"put -a {shlex.quote(str(source))} {shlex.quote(partial)}\n")
    result=subprocess.run(["sftp","-b",str(batch),"-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ip}"],text=True,capture_output=True,timeout=7200)
    (artifacts/f"{name}.sftp.stdout").write_text(result.stdout); (artifacts/f"{name}.sftp.stderr").write_text(result.stderr)
    seconds=time.monotonic()-started
    if result.returncode: raise RuntimeError(f"typed_transfer_boundary:sftp_failed:{name}:{result.stderr[-1000:]}")
    finalize=ssh(ip,f"test \"$(stat -c%s {shlex.quote(partial)})\" = {row['bytes']} && test \"$(sha256sum {shlex.quote(partial)}|awk '{{print $1}}')\" = {expected} && chmod 0444 {shlex.quote(partial)} && mv -f {shlex.quote(partial)} {shlex.quote(final)}",1800)
    if finalize.returncode: raise RuntimeError(f"typed_transfer_boundary:remote_hash_or_finalize_failed:{name}:{finalize.stderr[-1000:]}")
    return {"name":name,"status":"transferred","bytes":row["bytes"],"sha256":expected,"seconds":seconds,"bytes_per_second":row["bytes"]/seconds if seconds else None}
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--ip",required=True); p.add_argument("--remote-root",required=True); p.add_argument("--artifact-root",type=pathlib.Path,required=True); a=p.parse_args()
    binding=json.loads((PROJECT/"CHECKPOINT_SOURCE_BINDING.json").read_text()); manifest=json.loads((PROJECT/binding["manifest"]).read_text()); source=pathlib.Path(binding["source_root"])
    if not source.is_dir() or sum(x["bytes"] for x in manifest["checkpoint_files"])!=binding["checkpoint_bytes"]: raise RuntimeError("checkpoint_source_binding_invalid")
    a.artifact_root.mkdir(parents=True,exist_ok=True)
    prep=ssh(a.ip,f"mkdir -p {shlex.quote(a.remote_root)}/checkpoint",60)
    if prep.returncode: raise RuntimeError(f"typed_transfer_boundary:remote_prepare_failed:{prep.stderr[-1000:]}")
    rows=manifest["checkpoint_files"]
    for row in rows:
        path=source/row["path"]
        if not path.is_file() or path.stat().st_size!=row["bytes"] or sha256(path)!=row["sha256"]: raise RuntimeError(f"checkpoint_source_hash_mismatch:{row['path']}")
    weights=[r for r in rows if r["path"].endswith(".safetensors")]
    rest=[r for r in rows if r not in weights]
    outcomes=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes.extend(pool.map(lambda r:transfer(a.ip,a.remote_root,source/r["path"],r,a.artifact_root),weights))
    for row in rest: outcomes.append(transfer(a.ip,a.remote_root,source/row["path"],row,a.artifact_root))
    atomic(a.artifact_root/"CHECKPOINT_TRANSFER_TERMINAL.json",{"schema_version":1,"pass":True,"source_root":str(source),"files":outcomes,"checkpoint_bytes":binding["checkpoint_bytes"]})
    return 0
if __name__=="__main__": raise SystemExit(main())
