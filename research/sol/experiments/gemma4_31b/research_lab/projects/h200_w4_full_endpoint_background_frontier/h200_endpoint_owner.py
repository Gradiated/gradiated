#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

P = Path(__file__).resolve().parent
N = Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
sys.path.insert(0, str(N))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, list_items, make_cloud_init, wait_ssh
from session_staging import checkpoint_files, transfer_checkpoint, transfer_timeout_seconds
from stock_control import run_ssh, scp_from, scp_to
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic
from mla_microbench_control import retained_development_window

IMAGE = 'docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
KEY = Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
PUB = KEY.with_suffix('.pub')
CK = (P / '../h100_w4_full_endpoint_background_frontier/artifacts/w4-checkpoint-owner-20260717T223754Z/checkpoint-repair-2').resolve()
RATE, DISK = 2.45, 0.0097222
MODEL = 'google/gemma-4-31B-it'


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def put(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.part')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temp.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(path: Path, phase: str, **values: object) -> None:
    with path.open('a') as handle:
        handle.write(json.dumps({'timestamp': now(), 'phase': phase, **values}, sort_keys=True) + '\n')


def manifest_ok() -> tuple[bool, int, int]:
    manifest = CK / 'model-files.sha256'
    try:
        rows = checkpoint_files(CK)
        listed = {row.path for row in rows}
        valid = manifest.is_file() and 'model-files.sha256' in listed and all(len(line.split(maxsplit=1)) == 2 and len(line.split(maxsplit=1)[0]) == 64 for line in manifest.read_text().splitlines() if line)
        return valid, len(rows), sum(row.bytes for row in rows)
    except Exception:
        return False, 0, 0


def bindings_check(name: str, deadline: float) -> dict[str, object]:
    bindings = json.loads((P / 'BINDINGS.json').read_text())
    old = P.parent / 'h100_w4_full_endpoint_background_frontier'
    lifecycle = P.parent / 'h200_bf16_exact_linear_floor/h200_linear_owner.py'
    frontier = P.parent / 'h100_w4_background_concurrency_frontier/artifacts/gemma-h100-w4-frontier-20260717t22121784319137z/RECONCILED_FRONTIER_TERMINAL.json'
    lease = Path(bindings['repair_lease_protocol']['path'])
    lease_test = Path(bindings['repair_lease_protocol']['test_path'])
    economic_gate = P.parent / 'h200_campaign_economic_gate_reconciliation/H200_ECONOMIC_GATE.json'
    ok_manifest, files, total = manifest_ok()
    prior_spend = float(json.loads((P / 'STATUS.json').read_text()).get('provider_spend_usd_derived', 0.0))
    requested_seconds = deadline - time.time()
    prior_seconds = float(json.loads((P / 'STATUS.json').read_text()).get('provider_exposure_seconds', 0.0))
    checks = {
        'bindings_declared_pass': bindings.get('pass') is True,
        'bound_terminal_digest': digest(old / 'W4_CHECKPOINT_TERMINAL.json') == bindings['w4_checkpoint']['terminal_sha256'],
        'bound_transfer_manifest_digest': digest(CK / 'model-files.sha256') == bindings['w4_checkpoint']['transfer_manifest_sha256'],
        'bound_lifecycle_digest': digest(lifecycle) == bindings['proven_h200_lifecycle']['sha256'],
        'bound_component_digest': digest(frontier) == bindings['source_component_frontier']['sha256'],
        'bound_economic_gate_digest': digest(economic_gate) == bindings['economic_gate']['sha256'],
        'bound_repair_lease_digest': digest(lease) == bindings['repair_lease_protocol']['sha256'],
        'bound_repair_lease_test_digest': digest(lease_test) == bindings['repair_lease_protocol']['test_sha256'],
        'flat_transfer_manifest_parses': ok_manifest,
        'checkpoint_terminal_pass': json.loads((old / 'W4_CHECKPOINT_TERMINAL.json').read_text()).get('pass') is True,
        'checkpoint_exists': CK.is_dir(),
        'runner_exists': (P / 'endpoint_runner.py').is_file(),
        'empty_authenticated_inventory': not list_items('instance') and not list_items('disk'),
        'keypair_present': KEY.is_file() and PUB.is_file(),
        'deadline_and_spend_bound': 1200 < requested_seconds <= 3680 and prior_spend + (RATE + DISK) * requested_seconds / 3600 <= 6.5 and prior_seconds + requested_seconds <= 8100,
        'h200_placement_bound': bindings['target_hardware']['provider_platform'] == 'gpu-h200-sxm' and bindings['target_hardware']['provider_preset'] == '1gpu-16vcpu-200gb' and bindings['target_hardware']['experimental_rate_usd_per_gpu_hour'] == RATE,
    }
    return {'type': 'h200_w4_endpoint_precreate', 'timestamp': now(), 'checks': checks, 'pass': all(checks.values()), 'prior_spend_usd_derived': prior_spend, 'prior_provider_seconds': prior_seconds, 'requested_provider_seconds': requested_seconds, 'transfer_files_total': files, 'transfer_bytes': total, 'transfer_timeout_seconds': transfer_timeout_seconds(total), 'runner_sha256': digest(P / 'endpoint_runner.py')}


def remote_stage(ip: str, out: Path, events: Path, phase: str, command: str, timeout: int) -> subprocess.CompletedProcess[str]:
    event(events, phase, state='start', timeout_seconds=timeout)
    result = run_ssh(ip, KEY, command, timeout=timeout)
    (out / f'{phase}.stdout.log').write_text(result.stdout)
    (out / f'{phase}.stderr.log').write_text(result.stderr)
    put(out / f'{phase}.json', {'phase': phase, 'returncode': result.returncode, 'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(), 'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest(), 'completed_at_utc': now()})
    event(events, phase, state='complete', returncode=result.returncode)
    if result.returncode:
        raise RuntimeError(f'{phase} failed with return code {result.returncode}')
    return result


def diagnostic_files(label: str) -> tuple[str, ...]:
    return (f'{label}.container.log', f'{label}.container-state.json', f'{label}.container-exit-code.txt', f'{label}.container-oom.txt', f'{label}.gpu.csv')


def diagnostic_contract(root: Path, label: str) -> dict[str, object]:
    paths = [root / name for name in diagnostic_files(label)]
    try:
        state = json.loads(paths[1].read_text()) if paths[1].is_file() else None
    except json.JSONDecodeError:
        state = None
    exit_text = paths[2].read_text().strip() if paths[2].is_file() else ''
    oom_text = paths[3].read_text().strip().lower() if paths[3].is_file() else ''
    return {'label': label, 'files': [path.name for path in paths], 'container_state': state, 'exit_code': exit_text, 'oom_killed': oom_text == 'true', 'pass': all(path.is_file() for path in paths) and isinstance(state, dict) and bool(exit_text) and oom_text in {'true', 'false'}}


def retrieve_container_diagnostics(ip: str, out: Path, events: Path, work: str, label: str) -> dict[str, object]:
    remote = f'''set +e
mkdir -p {work}/diagnostics
sudo docker logs --timestamps w4-endpoint >{work}/diagnostics/{label}.container.log 2>&1
sudo docker inspect -f '{{{{json .State}}}}' w4-endpoint >{work}/diagnostics/{label}.container-state.json 2>&1
sudo docker inspect -f '{{{{.State.ExitCode}}}}' w4-endpoint >{work}/diagnostics/{label}.container-exit-code.txt 2>&1
sudo docker inspect -f '{{{{.State.OOMKilled}}}}' w4-endpoint >{work}/diagnostics/{label}.container-oom.txt 2>&1
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits >{work}/diagnostics/{label}.gpu.csv 2>&1
exit 0'''
    remote_stage(ip, out, events, f'{label}_diagnostic_capture', remote, 120)
    local = out / 'diagnostics'
    local.mkdir(exist_ok=True)
    for name in diagnostic_files(label):
        scp_from(ip, KEY, f'{work}/diagnostics/{name}', local / name)
    contract = diagnostic_contract(local, label)
    put(out / f'{label}_diagnostic_terminal.json', contract)
    if not contract['pass']:
        raise RuntimeError(f'{label} container diagnostic retrieval is incomplete')
    event(events, label, state='diagnostic_retrieved', exit_code=contract['exit_code'], oom_killed=contract['oom_killed'])
    return contract


def start_arm(ip: str, out: Path, events: Path, work: str, c: int, deadline: float) -> None:
    remaining = int(deadline - time.time())
    if remaining < 750:
        raise RuntimeError('insufficient deadline reserve for endpoint arm and repair window')
    command = f"mkdir -p {work}/fp8-kv; nohup python3 {work}/endpoint_runner.py --tokenizer {work}/checkpoint --output {work}/fp8-kv/c{c}-run --concurrencies {c} >{work}/c{c}.runner.stdout.log 2>{work}/c{c}.runner.stderr.log & echo $! >{work}/c{c}.runner.pid"
    remote_stage(ip, out, events, f'c{c}_launch', command, 60)
    while time.time() < deadline - 660:
        state = run_ssh(ip, KEY, f"test -f {work}/fp8-kv/c{c}-run/TERMINAL.json && echo terminal || true; sudo docker inspect -f '{{{{.State.Running}}}}' w4-endpoint 2>/dev/null || echo server-exited; test -f {work}/c{c}.runner.pid && kill -0 $(cat {work}/c{c}.runner.pid) 2>/dev/null && echo runner-live || echo runner-exited", timeout=45)
        text = state.stdout
        (out / f'c{c}_monitor.log').open('a').write(f'{now()} {text}')
        if 'server-exited' in text:
            retrieve_container_diagnostics(ip, out, events, work, f'c{c}_server_exit')
            raise RuntimeError(f'c{c} server exited before typed terminal')
        if 'terminal' in text:
            remote_stage(ip, out, events, f'c{c}_result_bundle', f"tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf {work}/c{c}.tar.gz -C {work} fp8-kv/c{c}-run c{c}.runner.stdout.log c{c}.runner.stderr.log telemetry.csv machete-consumer.txt vllm-load.log; sha256sum {work}/c{c}.tar.gz >{work}/c{c}.tar.gz.sha256", 180)
            archive = out / f'c{c}.tar.gz'
            scp_from(ip, KEY, f'{work}/c{c}.tar.gz', archive)
            scp_from(ip, KEY, f'{work}/c{c}.tar.gz.sha256', out / f'c{c}.tar.gz.sha256')
            if digest(archive) != (out / f'c{c}.tar.gz.sha256').read_text().split()[0]:
                raise RuntimeError(f'c{c} artifact SHA-256 mismatch')
            with tarfile.open(archive) as bundle:
                bundle.extractall(out / f'c{c}', filter='data')
            terminal = json.loads((out / f'c{c}/fp8-kv/c{c}-run/TERMINAL.json').read_text())
            put(out / f'c{c}_typed_terminal.json', terminal)
            if not terminal.get('pass'):
                raise RuntimeError(f'c{c} typed endpoint terminal failed')
            event(events, f'c{c}', state='typed_success')
            return
        time.sleep(30)
    raise RuntimeError(f'c{c} endpoint did not produce a terminal before repair reserve')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--deadline-epoch', type=float, required=True)
    args = parser.parse_args()
    if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID') != str(os.getpid()):
        raise RuntimeError('durable user systemd owner required')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    events = out / 'events.jsonl'
    regression = subprocess.run([sys.executable, str(P / 'test_owner_regression.py')], capture_output=True, text=True, timeout=60)
    lease_regression = subprocess.run([sys.executable, '-m', 'unittest', 'test_nebius_mla_microbench.NebiusMlaMicrobenchTests.test_active_repair_can_extend_retention_within_absolute_deadline'], capture_output=True, text=True, timeout=60, env={**os.environ, 'PYTHONPATH': f'{N}:{N.parent / "tests"}'})
    put(out / 'OWNER_REGRESSION.json', {'returncode': regression.returncode, 'stdout': regression.stdout[-4000:], 'stderr': regression.stderr[-4000:], 'lease_returncode': lease_regression.returncode, 'lease_stdout': lease_regression.stdout[-4000:], 'lease_stderr': lease_regression.stderr[-4000:], 'pass': regression.returncode == 0 and lease_regression.returncode == 0})
    precreate = bindings_check(args.name, args.deadline_epoch)
    precreate['checks']['owner_observability_and_retention_regression_pass'] = regression.returncode == 0
    precreate['checks']['repair_lease_regression_pass'] = lease_regression.returncode == 0
    precreate['pass'] = all(precreate['checks'].values())
    put(out / 'PRECREATE_TERMINAL.json', precreate)
    if not precreate['pass']:
        return 1
    put(out / 'repair-decision.json', {'action': 'retain', 'until_epoch': args.deadline_epoch, 'reason': 'permit in-place discovery repair through the authenticated owner deadline'})
    event(events, 'repair_lease_preseeded', retained_until_epoch=args.deadline_epoch)
    status = json.loads((P / 'STATUS.json').read_text())
    status.update({'provider_mutation': 'exclusive_durable_owner_only', 'active_session': {'mode': 'development', 'unit': os.getenv('SYSTEMD_UNIT') or f'{args.name}.service', 'unit_manager': 'user', 'pid': os.getpid(), 'name': args.name, 'artifact_root': str(out), 'deadline_epoch': args.deadline_epoch, 'repair_lease': {'action': 'retain', 'until_epoch': args.deadline_epoch, 'required_event': 'repair_retention_extended'}, 'expected_terminal': 'typed c128 then c96 FP8-KV endpoint rows or typed provider/runtime failure with authenticated cleanup'}, 'summary': 'Retained H200 development owner staging W4 and running observable c128 then c96 FP8-KV endpoint.', 'next_action': 'Attach to the H200 development owner and repair any first-call defect in place.'})
    put(P / 'STATUS.json', status)
    iid = None
    watchdog = None
    classification = 'h200_w4_endpoint_typed_failure'
    code = 1
    work = '/home/glmrunner/h200-w4-endpoint'
    try:
        with VerifiedRetainedOwner(args.name, out / 'cleanup.json') as owner, retained_development_window(out, events, args.deadline_epoch, 600):
            create = subprocess.run(build_create_command(name=args.name, disk_name=args.name + '-boot', cloud_init=make_cloud_init(PUB.read_text()), disk_gib=250, platform='gpu-h200-sxm', preset='1gpu-16vcpu-200gb', preemptible=True), capture_output=True, text=True, timeout=180)
            write_create_diagnostic(out, create)
            if create.returncode:
                raise RuntimeError(f'provider create returned {create.returncode}')
            iid = extract_instance_id(json.loads(create.stdout))
            owner.bind_instance(iid)
            watchdog = start_independent_watchdog(iid, args.name + '-boot', args.deadline_epoch, args.name + '-watchdog', unit_manager='user')
            event(events, 'provider_create', instance_id=iid, watchdog=watchdog)
            ip = None
            while time.time() < min(args.deadline_epoch - 660, time.time() + 600):
                payload = get_instance(iid)
                ip = extract_public_ipv4(payload) if payload else None
                if ip:
                    break
                time.sleep(5)
            if not ip:
                raise RuntimeError('public IP readiness deadline exceeded')
            wait_ssh(ip, KEY, min(args.deadline_epoch - 660, time.time() + 600))
            remote_stage(ip, out, events, 'workspace', f'mkdir -p {work}', 60)
            scp_to(ip, KEY, [P / 'endpoint_runner.py'], work + '/')
            event(events, 'checkpoint_transfer', state='start')
            transfer = transfer_checkpoint(ip, KEY, CK, work + '/checkpoint', timeout_seconds=min(precreate['transfer_timeout_seconds'], int(args.deadline_epoch - time.time() - 1260)))
            put(out / 'checkpoint_transfer.json', transfer.__dict__)
            event(events, 'checkpoint_transfer', state='complete', **transfer.__dict__)
            remote_stage(ip, out, events, 'image_pull', f'sudo docker pull {IMAGE}', min(1800, int(args.deadline_epoch - time.time() - 960)))
            remote_stage(ip, out, events, 'server_launch', f"sudo docker rm -f w4-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name w4-endpoint --gpus all --ipc=host --shm-size=16g -p 8000:8000 -v {work}:{work} {IMAGE} {work}/checkpoint --served-model-name {MODEL} --quantization awq --dtype float16 --kv-cache-dtype fp8_e4m3 --enable-prefix-caching --max-model-len 5000 --max-num-seqs 128 --max-num-batched-tokens 8192 --limit-mm-per-prompt '{{\"image\":0,\"audio\":0}}' >{work}/container-id.txt", 180)
            remote_stage(ip, out, events, 'telemetry_start', f"nohup bash -c 'while sudo docker inspect -f '{{{{.State.Running}}}}' w4-endpoint 2>/dev/null | grep -qx true; do date -u +%FT%TZ; nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits; sleep 5; done' >{work}/telemetry.csv 2>&1 &", 60)
            ready_until = min(args.deadline_epoch - 900, time.time() + 1200)
            while time.time() < ready_until:
                probe = run_ssh(ip, KEY, f"curl --fail --silent http://127.0.0.1:8000/v1/models >{work}/models.json 2>{work}/readiness.stderr || true; sudo docker inspect -f '{{{{.State.Running}}}}' w4-endpoint 2>/dev/null || echo server-exited", timeout=45)
                if (probe.returncode == 0 and 'server-exited' not in probe.stdout and 'google/gemma-4-31B-it' in run_ssh(ip, KEY, f'cat {work}/models.json 2>/dev/null || true', timeout=30).stdout):
                    event(events, 'server_readiness', state='complete')
                    break
                time.sleep(10)
            else:
                retrieve_container_diagnostics(ip, out, events, work, 'readiness_failure')
                raise RuntimeError('server readiness timeout or server exit')
            remote_stage(ip, out, events, 'machete_assertion', f"sudo docker exec w4-endpoint python3 -c 'from vllm.model_executor.layers.quantization.machete import MacheteLinearKernel; print(MacheteLinearKernel.apply_weights)' >{work}/machete-consumer.txt", 90)
            remote_stage(ip, out, events, 'load_logs', f'sudo docker logs w4-endpoint >{work}/vllm-load.log 2>&1 || true', 90)
            start_arm(ip, out, events, work, 128, args.deadline_epoch)
            start_arm(ip, out, events, work, 96, args.deadline_epoch)
            owner.complete('h200_w4_fp8_kv_c128_c96_endpoint_complete')
            classification = 'h200_w4_fp8_kv_c128_c96_endpoint_complete'
            code = 0
    except Exception as error:
        put(out / 'failure.json', {'type': type(error).__name__, 'message': str(error)[:4000], 'instance_id': iid, 'watchdog': watchdog, 'timestamp': now()})
        event(events, 'failure', error_type=type(error).__name__, message=str(error)[:1000])
    put(out / 'SUMMARY.json', {'classification': classification, 'controller_returncode': code, 'instance_id': iid, 'watchdog': watchdog, 'completed_at_utc': now()})
    status = json.loads((P / 'STATUS.json').read_text())
    status.update({'active_session': None, 'reconciliation_pending': True, 'terminal_artifact': str(out / 'SUMMARY.json'), 'provider_mutation': 'forbidden_pending_reconciliation', 'summary': 'Retained H200 endpoint owner terminal requires typed reconciliation.', 'next_action': 'Reconcile retrieved c128/c96 endpoint rows and authenticated cleanup.'})
    put(P / 'STATUS.json', status)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
