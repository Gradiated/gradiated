#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time

P = pathlib.Path(__file__).resolve().parent
LAB = P.parents[1]
FACTORY = pathlib.Path('/root/workspace/research/factory/src')
NEBIUS = pathlib.Path('/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius')
POOL = [sys.executable, '-m', 'grad_research.gpu_pool', '--lab', str(LAB)]
PROJECT, BENCH = 'gemma4_upstream_ngram_runtime_rebase', 'h200-ngram-verifier-e00kcm9nfhwt7e7gbc'
REMOTE = '/home/glmrunner/gemma4-upstream-ngram-v0515'
KEY, KNOWN = '/root/.config/nebius/glm-campaign/ssh_ed25519', '/root/.config/nebius/glm-campaign/known_hosts'
PID, TICKS = 74086, 2174809
DEADLINE = dt.datetime.fromisoformat('2026-07-25T07:00:00+00:00')
ART = P / 'artifacts' / 'v0515-endpoint-20260725t062540z'
RETRIEVED = ART / 'retrieved-final'

def now(): return dt.datetime.now(dt.timezone.utc)
def run(cmd, timeout=90, env=None): return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
def write(name, data):
    ART.mkdir(parents=True, exist_ok=True)
    (ART/name).write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')
def pool(*args): return run(POOL+list(args),45,dict(os.environ,PYTHONPATH=str(FACTORY)))
def heartbeat():
    r=pool('heartbeat','--project',PROJECT)
    write('RETRIEVAL_HEARTBEAT.json',{'at_utc':now().isoformat(),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    return r.returncode==0
def release(condition, contents):
    r=pool('release','--project',PROJECT,'--condition',condition,'--contents',json.dumps(contents,sort_keys=True))
    write('RETRIEVAL_RELEASE.json',{'at_utc':now().isoformat(),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
def host():
    inv=json.loads((LAB/'runtime/gpus.json').read_text()); benches=inv['benches'].values() if isinstance(inv['benches'],dict) else inv['benches']; b=next(x for x in benches if x['id']==BENCH)
    sys.path.insert(0,str(NEBIUS)); from placement_control import extract_public_ipv4,get_instance
    return extract_public_ipv4(get_instance(b['resource']['instance_id']))
def ssh(h, cmd, timeout=60):
    return run(['ssh','-i',KEY,'-o','BatchMode=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{h}',cmd],timeout)
def scp(h, remote, local):
    local.parent.mkdir(parents=True,exist_ok=True)
    return run(['scp','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{h}:{remote}',str(local)],180)
def snapshot(h):
    cmd=(f'cd {shlex.quote(REMOTE)} || exit 20; echo OWNER_BEGIN; cat ENDPOINT_OWNER.json 2>/dev/null || true; echo OWNER_END; '
         'echo STATUS_BEGIN; ./detached-owner status --state ENDPOINT_OWNER.json 2>/dev/null || true; echo STATUS_END; '
         'for x in endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json endpoint-stage/out-endpoint/ATTEMPT_TERMINAL.json endpoint-stage/out-endpoint/INVOCATION_STATE.json; do test -f "$x" && { echo FILE:$x; cat "$x"; }; done')
    r=ssh(h,cmd); write('remote-snapshot.json',{'at_utc':now().isoformat(),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}); return r
def present(s, rel): return f'FILE:{rel}' in s
def owner_matches(s):
    try:
        raw=s.split('OWNER_BEGIN\n',1)[1].split('\nOWNER_END',1)[0]
        x=json.loads(raw); return x.get('pid')==PID and x.get('start_ticks')==TICKS
    except Exception: return False
def retrieve(h):
    files=['ENDPOINT_OWNER.json','ENDPOINT_OWNER.log','endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json','endpoint-stage/out-endpoint/ATTEMPT_TERMINAL.json','endpoint-stage/out-endpoint/INVOCATION_STATE.json','endpoint-stage/out-endpoint/requests.jsonl','endpoint-stage/out-endpoint/metrics.jsonl']
    result=[]
    for rel in files:
        r=scp(h,f'{REMOTE}/{rel}',RETRIEVED/rel)
        result.append({'path':rel,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    write('RETRIEVAL_COPY.json',{'at_utc':now().isoformat(),'files':result})
def score():
    path=RETRIEVED/'endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json'
    if not path.exists(): return None
    x=json.loads(path.read_text()); g=x.get('gates',{})
    keys=['normalized_semantics_exact','native_ngram_activation_observed','failures_zero','stable_release_timing','long_unaffected_trunks','peak_queue_at_most_30','final_queue_zero','planning_cost_at_most_0_14_per_million']
    result={'all_original_gates_pass':all(g.get(k) is True for k in keys),'missing_or_false':[k for k in keys if g.get(k) is not True],'gates':g,'requests':x.get('requests'),'candidate_sample_consumed':x.get('candidate_sample_consumed')}
    write('ENDPOINT_RETRIEVAL_SCORE.json',result); return result
def main():
    ART.mkdir(parents=True,exist_ok=True); RETRIEVED.mkdir(parents=True,exist_ok=True); h=host()
    write('RETRIEVAL_OWNER_STARTED.json',{'at_utc':now().isoformat(),'host':h,'pid':PID,'start_ticks':TICKS,'deadline_utc':DEADLINE.isoformat(),'scope':'read_only_retrieval_no_guest_or_server_mutation'})
    last=None
    while now()<DEADLINE:
        if last is None or (now()-last).total_seconds()>=45:
            if not heartbeat(): write('RETRIEVAL_TYPED_BOUNDARY.json',{'kind':'claim_heartbeat_failed','at_utc':now().isoformat()}); return
            last=now()
        s=snapshot(h); terminal=present(s.stdout,'endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json'); attempt=present(s.stdout,'endpoint-stage/out-endpoint/ATTEMPT_TERMINAL.json')
        if terminal or attempt:
            retrieve(h); result=score()
            state='v0515_endpoint_retrieved_scored' if result else 'endpoint_attempt_without_interpretable_terminal'
            release('maintenance',{'project':PROJECT,'result':state,'endpoint_gates_pass':result and result['all_original_gates_pass'],'artifact':'gemma4_upstream_ngram_runtime_rebase/artifacts/v0515-endpoint-20260725t062540z/retrieved-final'})
            return
        if not owner_matches(s.stdout):
            write('RETRIEVAL_TYPED_BOUNDARY.json',{'kind':'bound_guest_identity_missing_without_terminal','at_utc':now().isoformat()})
            release('maintenance',{'project':PROJECT,'result':'typed_endpoint_retrieval_identity_boundary'}); return
        time.sleep(20)
    s=snapshot(h); retrieve(h); result=score()
    release('maintenance',{'project':PROJECT,'result':'v0515_endpoint_retrieved_at_deadline' if result else 'endpoint_retrieval_deadline_boundary','artifact':'gemma4_upstream_ngram_runtime_rebase/artifacts/v0515-endpoint-20260725t062540z/retrieved-final'})
if __name__=='__main__':
    try: main()
    except Exception as e:
        write('RETRIEVAL_EXCEPTION.json',{'at_utc':now().isoformat(),'type':type(e).__name__,'detail':str(e)})
        raise
