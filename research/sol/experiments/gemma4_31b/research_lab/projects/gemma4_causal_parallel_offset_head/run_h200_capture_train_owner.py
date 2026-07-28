#!/usr/bin/env python3
"""One retained H200 owner: capture is persisted once; training is resumable."""
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, os, pathlib, shlex, subprocess, sys, tarfile, tempfile, threading, time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
FACTORY = PROJECT.parents[5] / "factory" / "src"
REPAIR = PROJECT.parents[5] / "factory" / "tools" / "repair-handshake"
POOL = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
PROJECT_ID = "gemma4_causal_parallel_offset_head"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
TIED_SHA = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
SERVER = "--model-path /work/checkpoint --tokenizer-path /work/checkpoint --served-model-name google/gemma-4-31B-it --dtype bfloat16 --quantization fp8 --tp-size 1 --kv-cache-dtype fp8_e5m2 --host 0.0.0.0 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 --enable-fused-qk-norm-rope --prefill-attention-backend triton --decode-attention-backend triton --page-size 1 --num-continuous-decode-steps 1 --triton-attention-num-kv-splits 8 --tool-call-parser gemma4 --port 30000 --disable-cuda-graph"

def sha(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=path.parent,delete=False) as f:
        json.dump(value,f,indent=2,sort_keys=True); f.write("\n"); t=pathlib.Path(f.name)
    t.replace(path)

def run(cmd:list[str], timeout:float, out:pathlib.Path, input_text:str|None=None) -> subprocess.CompletedProcess[str]:
    r=subprocess.run(cmd,input=input_text,text=True,capture_output=True,timeout=max(1,timeout),check=False)
    out.write_text(r.stdout); out.with_suffix(out.suffix+".stderr").write_text(r.stderr); return r

def pool(args:list[str], out:pathlib.Path) -> subprocess.CompletedProcess[str]: return run(POOL+args,30,out)
def deadline(epoch:float)->str: return dt.datetime.fromtimestamp(epoch,dt.timezone.utc).isoformat().replace("+00:00","Z")

def sources() -> dict[str,pathlib.Path]:
    return {"capture_offset_taps.py":PROJECT/"capture_offset_taps.py","capture_bootstrap/sitecustomize.py":PROJECT/"capture_bootstrap/sitecustomize.py","causal_parallel_offset_head.py":PROJECT/"causal_parallel_offset_head.py","train_and_evaluate.py":PROJECT/"train_and_evaluate.py","exact_runner.py":PROJECT/"inputs/exact_runner.py","IMMUTABLE_SPLIT.json":PROJECT/"IMMUTABLE_SPLIT.json","COST_MODEL.json":PROJECT/"COST_MODEL.json","EXPERIMENT_CONTRACT.json":PROJECT/"EXPERIMENT_CONTRACT.json"}

def packet(output:pathlib.Path, repair_request:dict|None) -> tuple[pathlib.Path,dict[str,str]]:
    bound=sources()
    if repair_request and repair_request.get("patch_artifact"):
        patch=pathlib.Path(str(repair_request["patch_artifact"])).resolve(); spec=json.loads(patch.read_text())
        for name,row in spec.get("mutable_files",{}).items():
            candidate=pathlib.Path(row["path"]).resolve()
            if name not in bound or sha(candidate)!=row["sha256"]: raise RuntimeError("repair_patch_binding_mismatch:"+name)
            bound[name]=candidate
    hashes={n:sha(p) for n,p in bound.items()}; result=output/f"packet-{hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()}.tar.gz"
    with tarfile.open(result,"w:gz",format=tarfile.PAX_FORMAT) as a:
        for n,p in bound.items():
            i=a.gettarinfo(str(p),arcname=n); i.uid=i.gid=i.mtime=0; i.uname=i.gname=""
            with p.open("rb") as f:a.addfile(i,f)
    return result,hashes

def access(bench:str)->tuple[str,str]:
    b=json.loads((LAB/"runtime/gpus.json").read_text())["benches"]; r=b[bench] if isinstance(b,dict) else next(x for x in b if x["id"]==bench)
    todo=[r]; host=user=None
    while todo:
        x=todo.pop()
        if isinstance(x,dict): host=host or x.get("public_ipv4") or x.get("ssh_host"); user=user or x.get("ssh_user"); todo.extend(x.values())
    if not isinstance(host,str) or not isinstance(user,str): raise RuntimeError("inventory_missing_explicit_ssh_access")
    return host,user

def stage_checkpoint(ssh:list[str], key:pathlib.Path, known:pathlib.Path, user:str, host:str, root:str, source:pathlib.Path, output:pathlib.Path)->str:
    """Reconcile immutable checkpoint files without rewriting a matched remote byte."""
    manifest_path=PROJECT/"CHECKPOINT_MANIFEST.json"; manifest=json.loads(manifest_path.read_text())
    remote=f"{root}/checkpoint"; rows=[]
    if run([*ssh,f"mkdir -p {shlex.quote(remote)}"],120,output/"checkpoint-mkdir.stdout").returncode: raise RuntimeError("checkpoint_remote_directory_failed")
    for item in manifest["files"]:
        name=str(item["name"]); size=int(item["bytes"]); digest=str(item["sha256"]); local_path=source/name; target=f"{remote}/{name}"; temporary=f"{target}.{digest}.part"
        if not local_path.is_file() or local_path.stat().st_size!=size or sha(local_path)!=digest: raise RuntimeError("checkpoint_source_manifest_mismatch:"+name)
        match=run([*ssh,f"test -f {shlex.quote(target)} && test \"$(stat -c %s {shlex.quote(target)})\" = {size} && test \"$(sha256sum {shlex.quote(target)}|cut -d' ' -f1)\" = {digest}"],900,output/f"checkpoint-match-{name}.stdout")
        if match.returncode==0:
            rows.append({"name":name,"bytes":size,"sha256":digest,"remote_path":target,"reused":True}); continue
        if run([*ssh,f"rm -f {shlex.quote(temporary)}"],120,output/f"checkpoint-temp-{name}.stdout").returncode: raise RuntimeError("checkpoint_temp_cleanup_failed:"+name)
        copied=run(["scp","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",str(local_path),f"{user}@{host}:{temporary}"],max(900,size//20_000_000+300),output/f"checkpoint-copy-{name}.stdout")
        if copied.returncode: raise RuntimeError("checkpoint_copy_failed:"+name)
        verified=run([*ssh,f"test \"$(stat -c %s {shlex.quote(temporary)})\" = {size} && test \"$(sha256sum {shlex.quote(temporary)}|cut -d' ' -f1)\" = {digest} && chmod 0444 {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(target)}"],max(900,size//35_000_000+300),output/f"checkpoint-verify-{name}.stdout")
        if verified.returncode: raise RuntimeError("checkpoint_finalize_failed:"+name)
        rows.append({"name":name,"bytes":size,"sha256":digest,"remote_path":target,"reused":False})
    atomic(output/"CHECKPOINT_STAGE.json",{"classification":"immutable_checkpoint_staged","manifest_path":"CHECKPOINT_MANIFEST.json","manifest_sha256":sha(manifest_path),"source":str(source),"remote_path":remote,"files":rows})
    return remote

def capture_script(root:str, checkpoint:str)->str:
    q=shlex.quote
    '''Superseded malformed generation-one command construction.
    return "\n".join(("set -Eeuo pipefail",f"root={q(root)}","in=$root/input","a=$root/artifacts","c=gemma4-causal-offset-capture",f"test \"$(sha256sum {q(checkpoint)}/model-00001-of-00002.safetensors|cut -d\" \" -f1)\" = {TIED_SHA}",f"sudo -n docker image inspect {q(IMAGE)} >/dev/null || sudo -n docker pull {q(IMAGE)}","sudo -n docker rm -f $c >/dev/null 2>&1 || true","sudo -n docker run -d --name $c --gpus all --ipc=host --network=host -v $in:/work/input:ro -v $a:/project-local/artifacts -v "+q(checkpoint)+":/work/checkpoint:ro -e PYTHONPATH=/work/input/capture_bootstrap:/work/input -e CAUSAL_OFFSET_CAPTURE_ROOT=/project-local/artifacts/offset-capture "+q(IMAGE)+" python3 -m sglang.launch_server "+SERVER,"for i in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models >$a/server-health.json && break; sudo -n docker inspect -f '{{.State.Running}}' $c|grep -x true >/dev/null || { sudo -n docker logs $c >$a/server-fatal.log 2>&1||true; exit 71; }; sleep 2; done","curl -fsS http://127.0.0.1:30000/v1/models >$a/server-health-final.json","sudo -n docker inspect -f '{{.State.Running}}' $c|grep -x true >/dev/null","sudo -n docker exec $c bash -lc 'python3 - <<\"PY\"\nimport json,pathlib,time\np=pathlib.Path("/project-local/artifacts/offset-capture/science_started.json");p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(".part");t.write_text(json.dumps({"science_started":True,"stage":"first_capture_request","at_unix_s":time.time()})+"\\n");t.replace(p)\nPY\nexec python3 /work/input/exact_runner.py --output /project-local/artifacts/offset-capture/requests --arm causal-offset-ar-c32 --concurrency 32'","sudo -n docker stop $c >/dev/null || true","test -s $a/offset-capture/CAPTURE_TERMINAL.json","test -s $a/offset-capture/chunks.jsonl"))

    '''
    return "\n".join([
        "set -Eeuo pipefail", f"root={q(root)}", "in=$root/input", "a=$root/artifacts", "c=gemma4-causal-offset-capture",
        f"test \"$(sha256sum {q(checkpoint)}/model-00001-of-00002.safetensors | cut -d' ' -f1)\" = {TIED_SHA}",
        f"sudo -n docker image inspect {q(IMAGE)} >/dev/null || sudo -n docker pull {q(IMAGE)}", "sudo -n docker rm -f $c >/dev/null 2>&1 || true",
        f"sudo -n docker run -d --name $c --gpus all --ipc=host --network=host -v $in:/work/input:ro -v $a:/project-local/artifacts -v {q(checkpoint)}:/work/checkpoint:ro -e PYTHONPATH=/work/input/capture_bootstrap:/work/input -e CAUSAL_OFFSET_CAPTURE_ROOT=/project-local/artifacts/offset-capture {q(IMAGE)} python3 -m sglang.launch_server {SERVER}",
        "for i in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models >$a/server-health.json && break; sudo -n docker inspect -f '{{.State.Running}}' $c | grep -x true >/dev/null || { sudo -n docker logs $c >$a/server-fatal.log 2>&1 || true; exit 71; }; sleep 2; done",
        "curl -fsS http://127.0.0.1:30000/v1/models >$a/server-health-final.json", "sudo -n docker inspect -f '{{.State.Running}}' $c | grep -x true >/dev/null",
        "sudo -n docker exec $c bash -lc 'python3 - <<\"PY\"\nimport json,pathlib,time\np=pathlib.Path(\"/project-local/artifacts/offset-capture/science_started.json\")\np.parent.mkdir(parents=True,exist_ok=True)\nt=p.with_suffix(\".part\")\nt.write_text(json.dumps({\"science_started\":True,\"stage\":\"first_capture_request\",\"at_unix_s\":time.time()})+\"\\n\")\nt.replace(p)\nPY\nexec python3 /work/input/exact_runner.py --output /project-local/artifacts/offset-capture/requests --arm causal-offset-ar-c32 --concurrency 32'",
        "sudo -n docker stop $c >/dev/null || true", "test -s $a/offset-capture/CAPTURE_TERMINAL.json", "test -s $a/offset-capture/chunks.jsonl",
    ])

def train_script(root:str, checkpoint:str)->str:
    q=shlex.quote
    return f"set -Eeuo pipefail; sudo -n docker run --rm --gpus all --ipc=host -v {q(root)}/input:/work/input:ro -v {q(root)}/artifacts:/project-local/artifacts -v {q(checkpoint)}:/work/checkpoint:ro {q(IMAGE)} bash -lc 'cd /work/input && exec python3 train_and_evaluate.py --capture-root /project-local/artifacts/offset-capture --split /work/input/IMMUTABLE_SPLIT.json --cost-model /work/input/COST_MODEL.json --tied-weight /work/checkpoint/model-00001-of-00002.safetensors --artifact-root /project-local/artifacts/offset-head-train --batch-size 8 --epochs 1 --learning-rate 0.0003 --seed 20260726'; test -s {q(root)}/artifacts/offset-head-train/HOLDOUT_RESULT.json; test -s {q(root)}/artifacts/offset-head-train/head_checkpoint.pt"

def retrieve(ssh:list[str], root:str, relative:str, output:pathlib.Path, name:str)->pathlib.Path:
    target=output/name
    command=["scp",*ssh[1:-1],f"{ssh[-1]}:{root}/artifacts/{relative}",str(target)]
    r=subprocess.run(command,text=True,capture_output=True,timeout=900,check=False)
    (output/(name+".retrieve.stdout")).write_text(r.stdout)
    (output/(name+".retrieve.stderr")).write_text(r.stderr)
    if r.returncode or not target.is_file(): raise RuntimeError("retrieve_failed:"+relative)
    return target

def repair_wait(output:pathlib.Path, epoch:float, repair_id:str, kind:str, diagnostic:str, scope:str)->dict|None:
    if run([str(REPAIR),"ready","--root",str(output),"--repair-id",repair_id,"--deadline",deadline(epoch),"--failure-kind",kind,"--diagnostic",diagnostic,"--retry-scope",scope],30,output/f"{repair_id}.ready").returncode: raise RuntimeError("repair_ready_failed")
    if run([str(REPAIR),"wait","--root",str(output),"--repair-id",repair_id],max(1,epoch-time.time()),output/f"{repair_id}.wait").returncode: return None
    request=json.loads((output/".repair-handshakes"/repair_id/"REPAIR_REQUEST.json").read_text()); atomic(output/f"REPAIR_REQUEST.consumed.{repair_id}.json",request); return request

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--bench",required=True); ap.add_argument("--authorization",type=pathlib.Path,required=True); ap.add_argument("--checkpoint-source",type=pathlib.Path,required=True); ap.add_argument("--deadline-epoch",type=float,required=True); ap.add_argument("--output-dir",type=pathlib.Path,required=True); a=ap.parse_args(); out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    receipt=json.loads(a.authorization.read_text())
    if receipt.get("project")!=PROJECT_ID or receipt.get("reserved_usd")!=14.0 or receipt.get("ready_consumed") is not True: raise RuntimeError("director_consumption_receipt_required")
    os.environ["PYTHONPATH"]=str(FACTORY); claim=pool(["claim","--project",PROJECT_ID,"--bench",a.bench],out/"claim.stdout")
    if claim.returncode: raise RuntimeError("bench_claim_failed")
    stop=threading.Event()
    def beat():
        while not stop.wait(45): pool(["heartbeat","--project",PROJECT_ID],out/f"heartbeat-{int(time.time())}.stdout")
    thread=threading.Thread(target=beat,daemon=True);thread.start(); terminal=False
    try:
        host,user=access(a.bench); key=pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519");known=pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
        if not key.is_file() or not known.is_file():raise RuntimeError("established_ssh_identity_missing")
        ssh=["ssh","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",f"{user}@{host}"];root=f"/home/{user}/causal-offset-head"; repair=None; captured=False
        for generation in range(1,100):
            p,h=packet(out,repair); p_sha=sha(p); atomic(out/"COMMAND_GRAPH.json",{"generation":generation,"packet":h,"packet_sha256":p_sha,"server_entrypoint":"python3 -m sglang.launch_server","capture_path":"/work/input/exact_runner.py","endpoint_pairs":0,"predecessor_repair_id":None if generation==1 else f"repair-{generation-1}"})
            try:
                remote_checkpoint=stage_checkpoint(ssh,key,known,user,host,root,a.checkpoint_source.resolve(),out)
                if run([*ssh,f"mkdir -p {shlex.quote(root)}/input {shlex.quote(root)}/artifacts"],120,out/"stage.stdout").returncode: raise RuntimeError("remote_stage_prepare_failed")
                if run(["scp","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",str(p),f"{user}@{host}:{root}/{p.name}"],900,out/"stage-scp.stdout").returncode: raise RuntimeError("remote_packet_copy_failed")
                if run([*ssh,f"test \"$(sha256sum {shlex.quote(root)}/{p.name}|cut -d' ' -f1)\" = {p_sha}"],120,out/"stage-hash.stdout").returncode: raise RuntimeError("remote_packet_hash_mismatch")
                if run([*ssh,f"rm -rf {shlex.quote(root)}/input && mkdir -p {shlex.quote(root)}/input && tar -xzf {shlex.quote(root)}/{p.name} -C {shlex.quote(root)}/input"],240,out/"stage-unpack.stdout").returncode: raise RuntimeError("remote_packet_unpack_failed")
                if not captured:
                    atomic(out/"launch_attempted.json",{"generation":generation,"science_started":False,"at_unix_s":time.time()})
                    c=run([*ssh,"bash -s"],1800,out/"capture.stdout",capture_script(root,remote_checkpoint))
                    try:
                        terminal_path=retrieve(ssh,root,"offset-capture/CAPTURE_TERMINAL.json",out,"CAPTURE_TERMINAL.json"); manifest=retrieve(ssh,root,"offset-capture/chunks.jsonl",out,"chunks.jsonl")
                    except Exception: raise RuntimeError("capture_terminal_or_manifest_retrieval_failed")
                    capture=json.loads(terminal_path.read_text());
                    if c.returncode or capture.get("pass") is not True or not manifest.read_text().strip(): raise RuntimeError("capture_stage_not_interpretable")
                    atomic(out/"CAPTURE_STAGE.json",{"classification":"capture_complete_retrieved","terminal_sha256":sha(terminal_path),"manifest_sha256":sha(manifest),"rows":capture.get("rows"),"generation":generation});captured=True
                t=run([*ssh,"bash -s"],7200,out/"training.stdout",train_script(root,remote_checkpoint))
                holdout=retrieve(ssh,root,"offset-head-train/HOLDOUT_RESULT.json",out,"HOLDOUT_RESULT.json"); head=retrieve(ssh,root,"offset-head-train/head_checkpoint.pt",out,"head_checkpoint.pt")
                value=json.loads(holdout.read_text())
                if t.returncode or not value.get("checkpoint",{}).get("sha256") or value["checkpoint"]["sha256"]!=sha(head): raise RuntimeError("holdout_or_head_identity_invalid")
                atomic(out/"OWNER_TERMINAL.json",{"classification":"capture_train_holdout_complete","capture_stage":json.loads((out/"CAPTURE_STAGE.json").read_text()),"holdout_sha256":sha(holdout),"head_sha256":sha(head),"science_started":True});terminal=True;break
            except Exception as e:
                scope="training_holdout_consumer_only" if captured else "capture_pre_science_or_unclassified_retrieval"
                repair=repair_wait(out,a.deadline_epoch,f"repair-{generation}","later_consumer_failure" if captured else "capture_or_launch_failure",f"{type(e).__name__}:{e}",scope)
                if repair is None: raise RuntimeError("repair_deadline_expired")
        if not terminal: raise RuntimeError("no_terminal")
        pool(["release","--project",PROJECT_ID,"--condition","ready"],out/"release.stdout")
    finally: stop.set();thread.join(timeout=5)

if __name__=="__main__": raise SystemExit(main())
