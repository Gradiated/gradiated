import datetime
import hashlib
import json
import os
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path('/root/workspace/research/sol/experiments/glm47flash')
RESULT = ROOT / 'attempt3-orchestrator.json'
LEDGER = ROOT / 'ledger.jsonl'
POD_ID = 'opjyegxeh32tqu'
ENDPOINT = f'https://{POD_ID}-8000.proxy.runpod.net'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fetch(path, destination):
    request = urllib.request.Request(ENDPOINT + path, headers={'User-Agent': 'curl/8.0'})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open('wb') as handle:
        while chunk := response.read(8 * 1024 * 1024):
            handle.write(chunk)


def delete_pod():
    request = urllib.request.Request(
        'https://rest.runpod.io/v1/pods/' + POD_ID,
        headers={'Authorization': 'Bearer ' + os.environ['RUNPOD_API_KEY']},
        method='DELETE',
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def main():
    record = json.loads(RESULT.read_text())
    artifact = ROOT / 'attempt3.tar.gz'
    checksum = ROOT / 'attempt3.tar.gz.sha256.remote'
    fetch('/glm-attempt1.tar.gz', artifact)
    fetch('/glm-attempt1.tar.gz.sha256', checksum)
    local_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    remote_hash = checksum.read_text().split()[0]
    if local_hash != remote_hash:
        raise ValueError(f'Artifact hash mismatch: {local_hash} != {remote_hash}')
    finished_at = datetime.datetime.now(datetime.timezone.utc)
    started_at = datetime.datetime.fromisoformat(record['started_at'])
    elapsed = (finished_at - started_at).total_seconds()
    delete_status = delete_pod()
    record['events'].extend([
        {'at': utc(), 'event': 'benchmark_ready'},
        {'at': utc(), 'event': 'artifact_verified'},
    ])
    record['artifact'] = {'path': str(artifact), 'bytes': artifact.stat().st_size, 'sha256': local_hash}
    record['finished_at'] = finished_at.isoformat()
    record['allocation_seconds'] = elapsed
    record['conservative_spend_usd'] = elapsed * float(record['hourly_rate_usd']) / 3600
    record['teardown'] = {'delete_http_status': delete_status, 'verification': 'delete_requested'}
    RESULT.write_text(json.dumps(record, indent=2) + '\n')
    with LEDGER.open('a') as handle:
        handle.write(json.dumps({'timestamp': utc(), 'event': 'attempt_finished_manual_harvest', **record}, separators=(',', ':')) + '\n')
    print(json.dumps(record, indent=2), flush=True)


if __name__ == '__main__':
    main()
