#!/usr/bin/env python3
"""Durable claim owner for the sole calibrated immutable-corpus candidate."""
import datetime as dt, hashlib, json, os, shlex, subprocess, sys, threading, time
from pathlib import Path

P=Path(__file__).resolve().parent; LAB=P.parents[1]; FACTORY=Path("/root/workspace/research/factory/src"); NEBIUS=Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius"); KEY=Path("/root/.config/nebius/glm-campaign/ssh_ed25519"); KNOWN=Path("/root/.config/nebius/glm-campaign/known_hosts")
PROJECT="gemma4_ngram_calibration_freeze"; BENCH="h200-ngram-verifier-e00kcm9nfhwt7e7gbc"; REMOTE=Path("/home/glmrunner/gemma4-calibration-freeze"); CONTAINER="gemma4-ngram-tail-overlap"; CONTAINER_OUT=Path("/home/glmrunner/gemma4-ngram-tail-overlap/out"); DEADLINE=dt.datetime(2026,7,25,6,0,tzinfo=dt.timezone.utc); RATE=2.46
def now(): return dt.datetime.now(dt.timezone.utc)
def atomic(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+".part");q.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n");q.replace(p)
def run(a,timeout=None,**k): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=timeout,**k)
def pool(*a): return run(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),*a],env={**os.environ,"PYTHONPATH":str(FACTORY)})
def ssh(ip,c,t=900): return run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","ServerAliveInterval=20","-o","ServerAliveCountMax=3","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ip}",c],t)
def scp(ip,s,t,reverse=False):
    remote=f"glmrunner@{ip}:{t}";args=["scp","-p","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}"]
    return run(args+([remote,str(s)] if reverse else [str(s),remote]),600)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ip():
    sys.path.insert(0,str(NEBIUS));from placement_control import extract_public_ipv4,get_instance
    value=extract_public_ipv4(get_instance("computeinstance-e00kcm9nfhwt7e7gbc"))
    if not value:raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value
def update_status(**extra):
    s=json.loads((P/"STATUS.json").read_text());s.update(extra);atomic(P/"STATUS.json",s)
def stage(ip,artifact):
    packet=artifact/"PACKET.tar"; members=["inputs","DIRECTOR_BINDING.json","DIRECTOR_BINDING_VERIFIED.json","calibration_freeze_sitecustomize.py","remote_calibration_freeze.py"]
    r=run(["tar","-cf",str(packet),"-C",str(P),*members]);
    if r.returncode:raise RuntimeError("packet_build:"+r.stderr[-600:])
    h=digest(packet); target=REMOTE/"PACKET.tar"; r=ssh(ip,f"mkdir -p {shlex.quote(str(REMOTE))} && rm -f {shlex.quote(str(target))}.{h}.part",60)
    if r.returncode:raise RuntimeError("remote_directory:"+r.stderr[-600:])
    r=scp(ip,packet,str(target)+f".{h}.part")
    if r.returncode:raise RuntimeError("packet_transfer:"+r.stderr[-600:])
    r=ssh(ip,f"test \"$(sha256sum {shlex.quote(str(target))}.{h}.part | cut -d' ' -f1)\" = {h} && mv {shlex.quote(str(target))}.{h}.part {shlex.quote(str(target))} && cd {shlex.quote(str(REMOTE))} && tar -xf PACKET.tar",240)
    if r.returncode:raise RuntimeError("packet_extract:"+r.stderr[-600:])
    atomic(artifact/"PACKET.json",{"sha256":h,"remote":str(REMOTE)})
def activate(ip,artifact):
    command=f"if test -e {shlex.quote(str(CONTAINER_OUT/'calibration-freeze-ngram.jsonl'))}; then mv {shlex.quote(str(CONTAINER_OUT/'calibration-freeze-ngram.jsonl'))} {shlex.quote(str(CONTAINER_OUT/f'calibration-freeze.before-{artifact.name}.jsonl'))}; fi; rm -f {shlex.quote(str(CONTAINER_OUT/'OVERLAY_STATE.json'))} {shlex.quote(str(CONTAINER_OUT/'ACTIVATION_STATE.json'))}; sudo docker cp {shlex.quote(str(REMOTE/'calibration_freeze_sitecustomize.py'))} {CONTAINER}:/usr/lib/python3.12/sitecustomize.py && sudo docker restart {CONTAINER} >/dev/null"
    r=ssh(ip,command,240);(artifact/"activation.stdout").write_text(r.stdout);(artifact/"activation.stderr").write_text(r.stderr)
    if r.returncode:raise RuntimeError("activation_restart:"+r.stderr[-1000:])
    r=ssh(ip,f"for i in $(seq 1 180); do if test -s {shlex.quote(str(CONTAINER_OUT/'OVERLAY_STATE.json'))} && grep -q worker_initialized {shlex.quote(str(CONTAINER_OUT/'calibration-freeze-ngram.jsonl'))} && curl -fsS http://127.0.0.1:30000/v1/models >/dev/null; then cat {shlex.quote(str(CONTAINER_OUT/'OVERLAY_STATE.json'))}; exit 0; fi; sleep 2; done; sudo docker logs --tail 120 {CONTAINER} >&2;exit 1",420);(artifact/"activation-proof.stdout").write_text(r.stdout);(artifact/"activation-proof.stderr").write_text(r.stderr)
    if r.returncode:raise RuntimeError("activation_proof:"+r.stderr[-1200:])
def retrieve(ip,remote,artifact):
    archive=Path("/home/glmrunner")/(remote.name+".tar.gz");r=ssh(ip,f"tar -czf {shlex.quote(str(archive))} -C {shlex.quote(str(remote.parent))} {shlex.quote(remote.name)} && sha256sum {shlex.quote(str(archive))}",300)
    if r.returncode:raise RuntimeError("retrieval_archive:"+r.stderr[-800:])
    local=artifact/archive.name;r2=scp(ip,local,str(archive),True)
    if r2.returncode:raise RuntimeError("retrieval_copy:"+r2.stderr[-800:])
    if digest(local)!=r.stdout.split()[0]:raise RuntimeError("retrieval_hash")
    r3=run(["tar","-xzf",str(local),"-C",str(artifact)])
    if r3.returncode:raise RuntimeError("retrieval_extract")
    return artifact/remote.name
def main():
    artifact=P/"artifacts"/now().strftime("calibration-freeze-%Y%m%dt%H%M%Sz");artifact.mkdir(parents=True);prior=float(json.loads((P/"STATUS.json").read_text()).get("actual_spend_usd",0));claimed=False;start=time.monotonic();stop=threading.Event();terminal=None
    claim=pool("claim","--project",PROJECT,"--bench",BENCH,"--lease-seconds","300");(artifact/"claim.stdout").write_text(claim.stdout);(artifact/"claim.stderr").write_text(claim.stderr)
    if claim.returncode:raise RuntimeError("typed_pool_boundary:claim:"+claim.stderr[-600:])
    claimed=True
    def beat():
        while not stop.wait(45):
            r=pool("heartbeat","--project",PROJECT);atomic(P/"OWNER_HEARTBEAT.json",{"at_utc":now().isoformat(),"returncode":r.returncode,"stderr":r.stderr[-500:]})
    t=threading.Thread(target=beat,daemon=True);t.start()
    try:
        host=ip();stage(host,artifact);activate(host,artifact);remote=REMOTE/f"out-discriminator-32-790-{artifact.name}"; r=ssh(host,f"cd {shlex.quote(str(REMOTE))} && test ! -e {shlex.quote(str(remote))} && env CALIBRATION_FREEZE_ROOT={shlex.quote(str(REMOTE))} CALIBRATION_FREEZE_RESULT_OUT={shlex.quote(str(remote))} CALIBRATION_FREEZE_CONTAINER_OUT={shlex.quote(str(CONTAINER_OUT))} python3 remote_calibration_freeze.py",max(60,int((DEADLINE-now()).total_seconds())));(artifact/"worker.stdout").write_text(r.stdout);(artifact/"worker.stderr").write_text(r.stderr);local=retrieve(host,remote,artifact);final=local/"FINAL_TERMINAL.json"
        if not final.exists():raise RuntimeError("worker_without_final:"+(local/"ATTEMPT_TERMINAL.json").read_text()[-1000:])
        terminal=json.loads(final.read_text());spent=prior+(time.monotonic()-start)/3600*RATE;update_status(summary="Measured calibrated immutable-corpus discriminator retrieved.",actual_spend_usd=spent,active_session=None,candidate_sample_consumed=True,terminal={"artifact_root":str(artifact.relative_to(P)),"decision":terminal["decision"],"conditional_endpoint_admitted":terminal["conditional_endpoint_admitted"]})
        contents={"schema_version":1,"project":PROJECT,"result":terminal["result"],"artifacts":str(artifact.relative_to(P)),"candidate_sample_consumed":True,"activation_proved":terminal["decision"]["positive_activation_identity"],"discriminator_semantics_exact":terminal["decision"]["normalized_semantics_exact"],"discriminator_unaffected_long_trunks":terminal["decision"]["unaffected_long_trunks"],"conditional_full_endpoint_consumed":False,"server_state":"Healthy calibrated-freeze-patched SGLang server remains loaded; director disposition required before incompatible reuse.","checkpoint":"/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.","runtime":"Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM."};atomic(P/"BENCH_CONTENTS.json",contents);rel=pool("release","--project",PROJECT,"--condition","maintenance","--contents",str(P/"BENCH_CONTENTS.json"));(artifact/"release.stdout").write_text(rel.stdout);(artifact/"release.stderr").write_text(rel.stderr)
    except Exception as e:
        spent=prior+(time.monotonic()-start)/3600*RATE;diag={"classification":"recoverable_integration_or_consumer_defect","error":repr(e),"candidate_science_consumed":bool(terminal),"artifact_root":str(artifact.relative_to(P)),"repair_deadline_utc":DEADLINE.isoformat()};atomic(artifact/"OWNER_EXCEPTION.json",diag);atomic(P/"REPAIR_READY.json",diag);update_status(summary="Recoverable defect retained under claimed bench; repair evidence is ready.",actual_spend_usd=spent,terminal=diag)
    finally:
        stop.set();t.join(2);atomic(P/"OWNER_TERMINAL.json",{"at_utc":now().isoformat(),"conservative_provider_spend_usd":prior+(time.monotonic()-start)/3600*RATE,"terminal_retrieved":terminal is not None,"claim_retained_for_repair":claimed and terminal is None})
if __name__=="__main__":main()
