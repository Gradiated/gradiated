import base64
import datetime
import hashlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path('/root/workspace/research/lab/experiments/glm47flash')
SCRIPT = ROOT / 'glm47_awq_a40.sh'
RESULT = ROOT / 'attempt4-orchestrator.json'
LEDGER = ROOT / 'ledger.jsonl'
POD_NAME = 'glm47flash-awq-a40-attempt4-20260713'
GPU_TYPE = 'NVIDIA A40'
IMAGE = 'lmsysorg/sglang:v0.5.15-cu129'
RATE = 0.44
MACHINE_DEADLINE_SECONDS = 300
CONTAINER_DEADLINE_SECONDS = 1200
RESULT_DEADLINE_SECONDS = 3600


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def request(path, method='GET', payload=None, timeout=60):
    headers = {'Authorization': 'Bearer ' + os.environ['RUNPOD_API_KEY']}
    data = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(payload).encode()
    req = urllib.request.Request('https://rest.runpod.io/v1' + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
        return response.status, json.loads(body) if body else None


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read().strip()
    except (urllib.error.URLError, TimeoutError):
        return None


def append_ledger(row):
    with LEDGER.open('a') as handle:
        handle.write(json.dumps(row, separators=(',', ':')) + '\n')


def fetch(url, destination):
    with urllib.request.urlopen(url, timeout=120) as response, destination.open('wb') as handle:
        while chunk := response.read(8 * 1024 * 1024):
            handle.write(chunk)


def main():
    started_at = utc()
    started_monotonic = time.monotonic()
    _, pods = request('/pods')
    active = [p for p in pods if p.get('desiredStatus') in ('RUNNING', 'CREATED', 'RESTARTING')]
    if active:
        raise RuntimeError('Refusing to provision while an active pod exists: ' + json.dumps([p.get('id') for p in active]))

    command = 'printf %s "$CAMPAIGN_SCRIPT_B64" | base64 -d > /tmp/campaign.sh; chmod +x /tmp/campaign.sh; exec /tmp/campaign.sh'
    payload = {
        'name': POD_NAME,
        'imageName': IMAGE,
        'computeType': 'GPU',
        'gpuTypeIds': [GPU_TYPE],
        'gpuTypePriority': 'availability',
        'gpuCount': 1,
        'cloudType': 'SECURE',
        'containerDiskInGb': 40,
        'volumeInGb': 60,
        'volumeMountPath': '/workspace',
        'ports': ['8000/http'],
        'dockerEntrypoint': ['/bin/bash', '-lc'],
        'dockerStartCmd': [command],
        'env': {'CAMPAIGN_SCRIPT_B64': base64.b64encode(SCRIPT.read_bytes()).decode()},
    }
    _, pod = request('/pods', 'POST', payload, 120)
    pod_id = pod['id']
    record = {
        'attempt': 'attempt4',
        'pod_id': pod_id,
        'pod_name': POD_NAME,
        'gpu_type': GPU_TYPE,
        'image': IMAGE,
        'hourly_rate_usd': pod.get('costPerHr', RATE),
        'started_at': started_at,
        'machine_deadline_seconds': MACHINE_DEADLINE_SECONDS,
        'container_deadline_seconds': CONTAINER_DEADLINE_SECONDS,
        'result_deadline_seconds': RESULT_DEADLINE_SECONDS,
        'events': [{'at': utc(), 'event': 'pod_created'}],
    }
    append_ledger({'timestamp': utc(), 'event': 'pod_created', **record})
    RESULT.write_text(json.dumps(record, indent=2) + '\n')

    try:
        endpoint = f'https://{pod_id}-8000.proxy.runpod.net'
        deadline = time.monotonic() + MACHINE_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            _, state = request('/pods/' + pod_id, timeout=30)
            if state.get('machineId'):
                record['events'].append({'at': utc(), 'event': 'machine_assigned', 'machine_id': state['machineId']})
                break
            time.sleep(10)
        else:
            raise TimeoutError('Pod did not receive a machine before the deadline')

        deadline = time.monotonic() + CONTAINER_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            if probe(endpoint + '/LIVE') == b'live':
                record['events'].append({'at': utc(), 'event': 'container_live'})
                break
            _, state = request('/pods/' + pod_id, timeout=30)
            if state.get('desiredStatus') != 'RUNNING':
                raise RuntimeError('Pod left RUNNING before container became live: ' + str(state.get('desiredStatus')))
            time.sleep(15)
        else:
            raise TimeoutError('Container did not expose its live marker before the deadline')

        outcome = None
        deadline = time.monotonic() + RESULT_DEADLINE_SECONDS
        while time.monotonic() < deadline:
            if probe(endpoint + '/READY') == b'ready':
                outcome = 'ready'
                break
            if probe(endpoint + '/FAILED') == b'failed':
                outcome = 'failed'
                break
            _, state = request('/pods/' + pod_id, timeout=30)
            if state.get('desiredStatus') != 'RUNNING':
                raise RuntimeError('Pod left RUNNING before publishing a result: ' + str(state.get('desiredStatus')))
            time.sleep(15)
        if outcome is None:
            raise TimeoutError('Benchmark did not finish before the result deadline')

        artifact = ROOT / 'attempt4.tar.gz'
        checksum = ROOT / 'attempt4.tar.gz.sha256.remote'
        fetch(endpoint + '/glm-awq-a40.tar.gz', artifact)
        fetch(endpoint + '/glm-awq-a40.tar.gz.sha256', checksum)
        local_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        remote_hash = checksum.read_text().split()[0]
        if local_hash != remote_hash:
            raise ValueError(f'Artifact hash mismatch: {local_hash} != {remote_hash}')
        record['outcome'] = outcome
        record['artifact'] = {'path': str(artifact), 'bytes': artifact.stat().st_size, 'sha256': local_hash}
        record['events'].append({'at': utc(), 'event': 'artifact_verified', 'outcome': outcome})
        if outcome == 'failed':
            record['error'] = 'Campaign published a failed result'
    except Exception as error:
        record['error'] = repr(error)
        record['events'].append({'at': utc(), 'event': 'attempt_failed', 'error': repr(error)})
    finally:
        try:
            delete_status, _ = request('/pods/' + pod_id, 'DELETE', timeout=30)
        except urllib.error.HTTPError as error:
            delete_status = error.code
        try:
            request('/pods/' + pod_id, timeout=30)
            verification = 'present'
        except urllib.error.HTTPError as error:
            verification = f'http_{error.code}'
        elapsed = time.monotonic() - started_monotonic
        record['finished_at'] = utc()
        record['allocation_seconds'] = elapsed
        record['conservative_spend_usd'] = elapsed * float(record['hourly_rate_usd']) / 3600
        record['teardown'] = {'delete_http_status': delete_status, 'verification': verification}
        RESULT.write_text(json.dumps(record, indent=2) + '\n')
        append_ledger({'timestamp': utc(), 'event': 'attempt_finished', **record})
        print(json.dumps(record, indent=2), flush=True)


if __name__ == '__main__':
    main()
