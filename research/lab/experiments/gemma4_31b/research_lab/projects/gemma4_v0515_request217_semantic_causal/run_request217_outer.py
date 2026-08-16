#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import threading
import time

P = pathlib.Path(__file__).resolve().parent
LAB = P.parents[1]
FACTORY = pathlib.Path('/root/workspace/research/factory/src')
NEBIUS = pathlib.Path('/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius')
DETACHED = pathlib.Path('/root/workspace/research/factory/tools/detached-owner')
PROJECT = 'gemma4_v0515_request217_semantic_causal'
BENCH = 'h200-ngram-verifier-e00kcm9nfhwt7e7gbc'
REMOTE = '/home/glmrunner/gemma4-v0515-request217-semantic-causal'
KEY = pathlib.Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
KNOWN = pathlib.Path('/root/.config/nebius/glm-campaign/known_hosts')
DEADLINE = dt.datetime(2026, 7, 25, 7, 40, tzinfo=dt.timezone.utc)
RATE = 2.46
STATE = pathlib.Path(os.environ.get('REQUEST217_OWNER_STATE', str(P / 'OWNER_STATE.json')))
BASE_SPEND = float(json.loads((P / 'STATUS.json').read_text()).get('actual_spend_usd', 0.0))


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def atomic(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + '.part')
    partial.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    partial.replace(path)


def run(args, timeout=90, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)


def pool(*args):
    return run(['python3', '-m', 'grad_research.gpu_pool', '--lab', str(LAB), *args], env={**os.environ, 'PYTHONPATH': str(FACTORY)})


def ssh(host, command, timeout=90):
    return run(['ssh', '-i', str(KEY), '-o', 'BatchMode=yes', '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={KNOWN}', f'glmrunner@{host}', command], timeout)


def scp_to(host, source, destination):
    return run(['scp', '-p', '-i', str(KEY), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={KNOWN}', str(source), f'glmrunner@{host}:{destination}'], 900)


def scp_from(host, source, destination):
    return run(['scp', '-p', '-i', str(KEY), '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={KNOWN}', f'glmrunner@{host}:{source}', str(destination)], 900)


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def host():
    inventory = json.loads((LAB / 'runtime/gpus.json').read_text())
    bench = inventory['benches'][BENCH]
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance
    value = extract_public_ipv4(get_instance(bench['resource']['instance_id']))
    if not value:
        raise RuntimeError('typed_provider_boundary:no_public_ip')
    return value


def status(session, summary, spend=None, terminal=None):
    value = json.loads((P / 'STATUS.json').read_text())
    value['active_session'] = session
    value['summary'] = summary
    if spend is not None:
        value['actual_spend_usd'] = round(BASE_SPEND + spend, 6)
    if terminal is not None:
        value['terminal'] = terminal
    atomic(P / 'STATUS.json', value)


def stage(remote_host, artifact):
    packet = artifact / 'PACKET.tar'
    created = run(['tar', '-cf', str(packet), '-C', str(P), 'DIRECTOR_BINDING.json', 'DIRECTOR_EXECUTION_BINDING.json', 'PACKET_MANIFEST.json', 'DISCRIMINATOR_PACKET.json', 'LOCALIZATION.json', 'REPAIR_CANDIDATE.json', 'analyze_localization.py', 'remote_request217_discriminator.py', 'remote_request217_worker.sh', 'verify_packet.py', 'inputs', 'source'])
    if created.returncode:
        raise RuntimeError('typed_staging_boundary:packet_tar')
    packet_hash, owner_hash = digest(packet), digest(DETACHED)
    mkdir = ssh(remote_host, f'install -d {shlex.quote(REMOTE)} {shlex.quote(REMOTE + "/out")}')
    if mkdir.returncode:
        raise RuntimeError('typed_staging_boundary:remote_mkdir')
    for source, destination, expected in ((packet, REMOTE + '/PACKET.tar', packet_hash), (DETACHED, REMOTE + '/detached-owner', owner_hash)):
        valid = ssh(remote_host, f'test -f {shlex.quote(destination)} && test "$(sha256sum {shlex.quote(destination)} | cut -d\" \" -f1)" = {expected}')
        if valid.returncode:
            copied = scp_to(remote_host, source, destination + '.part')
            if copied.returncode:
                (artifact / (source.name + '.scp.stderr')).write_text(copied.stderr)
                raise RuntimeError('typed_staging_boundary:scp')
            verified = ssh(remote_host, f'test "$(sha256sum {shlex.quote(destination + ".part")} | cut -d\" \" -f1)" = {expected} && mv -f {shlex.quote(destination + ".part")} {shlex.quote(destination)}')
            if verified.returncode:
                raise RuntimeError('typed_staging_boundary:remote_hash')
    extracted = ssh(remote_host, f'cd {shlex.quote(REMOTE)} && tar -xf PACKET.tar && chmod 0555 detached-owner remote_request217_worker.sh remote_request217_discriminator.py && python3 verify_packet.py')
    (artifact / 'remote-stage.stdout').write_text(extracted.stdout)
    (artifact / 'remote-stage.stderr').write_text(extracted.stderr)
    if extracted.returncode:
        raise RuntimeError('typed_staging_boundary:extract_or_verify')
    atomic(artifact / 'STAGING_MANIFEST.json', {'packet_sha256': packet_hash, 'detached_owner_sha256': owner_hash, 'remote_root': REMOTE})


def launch(remote_host, artifact):
    command = f'cd {shlex.quote(REMOTE)} && ./detached-owner start --state GUEST_OWNER.json --log GUEST_OWNER.log --cwd {shlex.quote(REMOTE)} --unit-manager remote-shell -- env REQUEST217_ROOT={shlex.quote(REMOTE)} REQUEST217_OUT={shlex.quote(REMOTE + "/out")} REQUEST217_CONTAINER=gemma4-v0515-request217-decode ./remote_request217_worker.sh'
    launched = ssh(remote_host, command, 60)
    (artifact / 'guest-launch.stdout').write_text(launched.stdout)
    (artifact / 'guest-launch.stderr').write_text(launched.stderr)
    if launched.returncode:
        raise RuntimeError('typed_remote_owner_boundary:launch')


def remote_state(remote_host):
    checked = ssh(remote_host, f'cd {shlex.quote(REMOTE)} && ./detached-owner status --state GUEST_OWNER.json 2>/dev/null; test -f out/FINAL_TERMINAL.json && echo FINAL || true; test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT || true; cat out/INVOCATION_STATE.json 2>/dev/null || true', 45)
    return {'at_utc': now(), 'stdout': checked.stdout, 'stderr': checked.stderr, 'returncode': checked.returncode, 'final': 'FINAL' in checked.stdout, 'attempt': 'ATTEMPT' in checked.stdout, 'live': '"live": true' in checked.stdout}


def retrieve(remote_host, artifact):
    packed = ssh(remote_host, f'cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz GUEST_OWNER.json GUEST_OWNER.log out 2>/dev/null && sha256sum compact.tar.gz > compact.tar.gz.sha256', 180)
    (artifact / 'retrieval.stdout').write_text(packed.stdout)
    (artifact / 'retrieval.stderr').write_text(packed.stderr)
    if packed.returncode:
        raise RuntimeError('recoverable_retrieval_defect:archive')
    for remote, local in [('compact.tar.gz', 'compact.tar.gz'), ('compact.tar.gz.sha256', 'compact.tar.gz.sha256')]:
        copied = scp_from(remote_host, REMOTE + '/' + remote, artifact / local)
        if copied.returncode:
            (artifact / (local + '.scp.stderr')).write_text(copied.stderr)
            raise RuntimeError('recoverable_retrieval_defect:scp')
    if digest(artifact / 'compact.tar.gz') != (artifact / 'compact.tar.gz.sha256').read_text().split()[0]:
        raise RuntimeError('recoverable_retrieval_defect:hash')
    target = artifact / 'retrieved'
    target.mkdir(exist_ok=True)
    unpacked = run(['tar', '-xzf', str(artifact / 'compact.tar.gz'), '-C', str(target)])
    if unpacked.returncode:
        raise RuntimeError('recoverable_retrieval_defect:unpack')


def release(condition, contents):
    content_path = P / 'BENCH_CONTENTS.json'
    atomic(content_path, contents)
    return pool('release', '--project', PROJECT, '--condition', condition, '--contents', str(content_path))


def main():
    verified = run(['python3', str(P / 'verify_packet.py')])
    if verified.returncode:
        raise RuntimeError('typed_preclaim_binding_boundary:packet_hash')
    claimed = pool('claim', '--project', PROJECT, '--bench', BENCH)
    if claimed.returncode:
        raise RuntimeError('typed_claim_boundary:' + claimed.stderr[-1000:])
    artifact = P / 'artifacts' / ('request217-decode-' + dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%Sz'))
    artifact.mkdir(parents=True, exist_ok=False)
    started = time.time()
    remote_host = host()
    stop = threading.Event()
    state_data = json.loads(STATE.read_text())
    session = {'unit': str(STATE), 'unit_manager': 'pid', 'pid': state_data['pid'], 'start_ticks': state_data['start_ticks'], 'deadline_utc': '2026-07-25T07:40:00Z', 'artifact_root': str(artifact), 'bench_id': BENCH, 'remote_root': REMOTE, 'expected_terminal': 'FINAL_TERMINAL.json'}
    status(session, 'Bound H200 request-217 discriminator is controlled by durable outer owner.')
    def heartbeat():
        while not stop.wait(45):
            beat = pool('heartbeat', '--project', PROJECT)
            atomic(P / 'OWNER_HEARTBEAT.json', {'at_utc': now(), 'returncode': beat.returncode, 'stderr': beat.stderr[-2000:]})
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        identity = ssh(remote_host, 'hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker ps -a --format "{{.Names}} {{.Image}} {{.Status}}"', 45)
        (artifact / 'remote-identity.stdout').write_text(identity.stdout)
        (artifact / 'remote-identity.stderr').write_text(identity.stderr)
        if identity.returncode:
            raise RuntimeError('typed_remote_boundary:ssh')
        stage(remote_host, artifact)
        launch(remote_host, artifact)
        while dt.datetime.now(dt.timezone.utc) < DEADLINE:
            time.sleep(20)
            observed = remote_state(remote_host)
            atomic(artifact / 'REMOTE_STATE.json', observed)
            if observed['final']:
                retrieve(remote_host, artifact)
                terminal = json.loads((artifact / 'retrieved' / 'out' / 'FINAL_TERMINAL.json').read_text())
                spent = (time.time() - started) / 3600 * RATE
                contents = {'project': PROJECT, 'result': terminal['result'], 'candidate_sample_consumed': True, 'artifacts': str(artifact.relative_to(P)), 'image': 'docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd', 'checkpoint': '/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.', 'server_state': 'Official v0.5.15 decode-attention NGRAM candidate remains loaded on port 30000; maintenance disposition required before unrelated reuse.'}
                released = release('maintenance', contents)
                (artifact / 'release.stdout').write_text(released.stdout)
                (artifact / 'release.stderr').write_text(released.stderr)
                status(None, 'Request-217 discriminator terminal retrieved and H200 released to maintenance.', spent, {'classification': 'measured_request217_discriminator', 'artifact_root': str(artifact.relative_to(P)), 'candidate_sample_consumed': True, 'repair_admitted': terminal['repair_admitted']})
                return
            if observed['attempt'] and not observed['live']:
                retrieve(remote_host, artifact)
                ready = run(['/root/workspace/research/factory/tools/repair-handshake', 'ready', '--root', str(artifact), '--deadline', '2026-07-25T07:38:00Z', '--failure-kind', 'recoverable_remote_consumer_or_setup_defect', '--diagnostic', str(artifact / 'retrieved' / 'out' / 'ATTEMPT_TERMINAL.json'), '--retry-scope', 'only the invalidated launch, staging, or consumer operation on the same H200; no replay after FINAL_TERMINAL'])
                (artifact / 'repair-ready.stdout').write_text(ready.stdout)
                (artifact / 'repair-ready.stderr').write_text(ready.stderr)
                status(session, 'Recoverable remote defect retrieved; H200 remains claimed during repair handshake.')
                waited = run(['/root/workspace/research/factory/tools/repair-handshake', 'wait', '--root', str(artifact)], timeout=max(1, int((DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds())))
                (artifact / 'repair-wait.stdout').write_text(waited.stdout)
                (artifact / 'repair-wait.stderr').write_text(waited.stderr)
                if waited.returncode:
                    raise RuntimeError('typed_repair_boundary:deadline_or_unbound_request')
                archived = ssh(remote_host, f'cd {shlex.quote(REMOTE)} && mv out out.pre_repair_$(date +%s) && mkdir out && rm -f ATTEMPT_TERMINAL.json', 45)
                if archived.returncode:
                    raise RuntimeError('recoverable_repair_archive_defect')
                stage(remote_host, artifact)
                launch(remote_host, artifact)
        raise RuntimeError('typed_deadline_boundary:absolute')
    except Exception as exc:
        atomic(artifact / 'OWNER_EXCEPTION.json', {'at_utc': now(), 'error': repr(exc)})
        try:
            retrieve(remote_host, artifact)
        except Exception as retrieval:
            atomic(artifact / 'RETRIEVAL_EXCEPTION.json', {'at_utc': now(), 'error': repr(retrieval)})
        spent = (time.time() - started) / 3600 * RATE
        released = release('maintenance', {'project': PROJECT, 'result': 'typed_owner_or_remote_boundary', 'candidate_sample_consumed': False, 'error': repr(exc), 'artifacts': str(artifact.relative_to(P)), 'server_state': 'Requires director inspection; remote diagnostic retrieval was attempted before release.'})
        (artifact / 'release.stdout').write_text(released.stdout)
        (artifact / 'release.stderr').write_text(released.stderr)
        status(None, 'Request-217 owner reached a typed boundary after retrieval attempt; H200 released to maintenance.', spent, {'classification': 'typed_boundary', 'artifact_root': str(artifact.relative_to(P)), 'candidate_sample_consumed': False})
    finally:
        stop.set()
        thread.join(5)
        atomic(P / 'OWNER_TERMINAL.json', {'at_utc': now(), 'artifact_root': str(artifact), 'claimed_seconds': max(0, time.time() - started), 'conservative_provider_spend_usd': max(0, time.time() - started) / 3600 * RATE})


if __name__ == '__main__':
    main()
