import json
from pathlib import Path
import subprocess
import time
import unittest
import uuid

GPU_BASE = Path(__file__).resolve().parents[1]
CONTEXT = GPU_BASE.parents[1]
HOST_BUNDLE = CONTEXT / 'bundles' / 'host' / 'Dockerfile'
# The same parent image as start_host_test.py, so both tests share build layers.
UBUNTU = 'ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac'
IMAGE = 'gradiated-gpu-base-enrollment-test'
ROOT = '/var/lib/gradiated-kubelet'
POD = '6a8f2a52-7b0e-4c1d-9a64-2f1d3c5b8e01'
GPUS = ['GPU-00000000-0000-0000-0000-000000000001', 'GPU-00000000-0000-0000-0000-000000000002']
CONTAINER = 'gpu-base-enrollment-' + uuid.uuid4().hex
RESULTS = {}


def docker(*args, check=True, **kwargs):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, timeout=1200, **kwargs)
    if check and result.returncode:
        raise AssertionError(f'docker {args[0]} failed: {result.stderr[-3000:]}')
    return result


def host_bundle_stage():
    lines = HOST_BUNDLE.read_text().replace('\\\n', ' ').splitlines()
    end = next(index for index, line in enumerate(lines[1:], 1) if line.startswith('FROM '))
    stage = [f'FROM {UBUNTU} AS host-bundle',
             'RUN apt-get update && apt-get install -y --no-install-recommends '
             'python3 pigz cmake g++ make libcurl4-openssl-dev']
    for line in lines[1:end]:
        # desmondd needs the whole inference engine (/src), so a placeholder replaces it.
        if not line.strip() or 'apt-get' in line or 'alpine' in line or ' /src' in line:
            continue
        if 'files.json' in line:
            stage.append("RUN printf '#!/bin/sh\\nexec sleep infinity\\n' >/bundle/desmondd && chmod 755 /bundle/desmondd")
        stage.append(line.replace('product/inference/', ''))
    if not any('files.json' in line for line in stage) or not any('runtime-launch ' in line for line in stage):
        raise AssertionError('The host bundle Dockerfile changed shape; update host_bundle_stage')
    return stage


def setUpModule():
    dockerfile = (GPU_BASE / 'Dockerfile').read_text().splitlines()
    if not dockerfile[0].startswith('FROM nvidia/cuda:'):
        raise AssertionError('Unexpected GPU base parent image')
    dockerfile[0:1] = [f'FROM {UBUNTU}', 'RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates']
    dockerfile += [
        'COPY --chmod=755 images/gpu-base/tests/fake-tailscale /opt/gradiated/tailscale/tailscale',
        # Task processes run with a PATH that leaves out /usr/local/bin.
        'COPY --chmod=755 images/gpu-base/tests/fake-nvidia-smi /usr/bin/nvidia-smi',
        'COPY gpu/host_state.py gpu/host_bundle.py gpu/supervise.py gpu/install-seed.py /opt/enrollment-test/installer/',
        'COPY images/gpu-base/tests/enrollment.py /opt/enrollment-test/enrollment.py',
        'COPY --from=host-bundle /runtime.tar.gz /opt/enrollment-test/host-bundle.tar.gz',
    ]
    docker('build', '-q', '--platform', 'linux/amd64', '-t', IMAGE, '-f', '-', str(CONTEXT),
           input='\n'.join(host_bundle_stage() + dockerfile) + '\n')
    # Runtime tasks move themselves into pod cgroups, which needs a writable cgroup tree.
    docker('run', '-d', '--platform', 'linux/amd64', '--privileged', '--network', 'none',
           '--name', CONTAINER, IMAGE)
    docker('exec', '-d', CONTAINER, 'python3', '/opt/enrollment-test/enrollment.py', 'serve')
    wait('test -e /opt/enrollment-test/serving')
    enrollment = docker('exec', CONTAINER, 'bash', '-c',
                        'umask 077 && exec python3 /opt/enrollment-test/enrollment.py enroll', check=False)
    output = docker('exec', CONTAINER, 'cat', '/opt/enrollment-test/result.json', check=False)
    if output.returncode:
        raise AssertionError(f'Enrollment did not run: {enrollment.stdout[-3000:]}{enrollment.stderr[-3000:]}')
    RESULTS.update(json.loads(output.stdout))


def tearDownModule():
    subprocess.run(['docker', 'rm', '-f', CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait(script, seconds=60):
    deadline = time.monotonic() + seconds
    while docker('exec', CONTAINER, 'bash', '-c', script, check=False).returncode:
        if time.monotonic() > deadline:
            return False
        time.sleep(.5)
    return True


def shell(script, user='root'):
    return docker('exec', '-u', user, CONTAINER, 'bash', '-c', script, check=False)


def access(user, checks):
    script = f'''
import json, os, sys
failures = []
for path, mode in {checks!r}:
    if mode == 'list':
        try:
            os.listdir(path)
        except OSError as error:
            failures.append(f'{{path}}: {{error}}')
    elif not os.access(path, {{'read': os.R_OK, 'run': os.R_OK | os.X_OK, 'write': os.W_OK | os.X_OK}}[mode]):
        failures.append(f'{{path}}: cannot {{mode}}')
print(json.dumps(failures))
'''
    result = docker('exec', '-u', user, CONTAINER, 'python3', '-c', script)
    return json.loads(result.stdout)


class EnrollmentTests(unittest.TestCase):
    maxDiff = None

    def require(self, *steps):
        for step in steps:
            result = RESULTS.get(step)
            if not result:
                self.fail(f'Enrollment stopped before {step}')
            if not result['ok']:
                self.fail(f'{step} failed:\n{result["error"]}')

    def host(self):
        return f'{ROOT}/host/{RESULTS["host_bundle"]}'

    def runtime_started(self):
        log = f'{ROOT}/pods/{POD}/runtime.log'
        if not wait(f'grep -q "runtime started as runtime" {log}'):
            output = shell(f'cat {log} {ROOT}/pods/{POD}/task.log').stdout
            self.fail(f'The runtime task did not start:\n{output}')
        return shell(f'cat {log}').stdout

    def test_enrollment_runs_under_a_private_umask(self):
        self.assertEqual(RESULTS['umask'], '0o77')
        self.require('install_seed', 'enroll', 'stage', 'task')

    def test_service_users_can_read_the_installed_host(self):
        self.require('install_seed')
        host, recovery = self.host(), '/opt/gradiated/kubelet/recovery'
        first = RESULTS['runtimes'][0]
        expected = {
            'downloader': [(ROOT, 'list'), (f'{ROOT}/host', 'list'), (host, 'list'),
                           (f'{host}/fetch-runtime', 'run'), (f'{host}/download-runtime', 'read'),
                           (recovery, 'list'), (f'{recovery}/fetch-runtime', 'run'),
                           (f'{recovery}/download-runtime', 'read'), (f'{ROOT}/bundles', 'write')],
            'runtime': [(f'{host}/runtime-launch', 'run'), (f'{ROOT}/bundles', 'list'),
                        (f'{ROOT}/bundles/{first}', 'list'), (f'{ROOT}/bundles/{first}/entrypoint', 'run'),
                        ('/etc/gradiated/base-id', 'read')],
            'desmond': [(f'{host}/desmondd', 'run'), ('/etc/gradiated/runtime-access.token', 'read')],
        }
        for user, checks in expected.items():
            with self.subTest(user=user):
                self.assertEqual(access(user, checks), [])

    def test_downloader_fetches_a_runtime_with_the_host_bundle_tools(self):
        self.require('install_seed', 'enroll')
        third = RESULTS['runtimes'][2]
        source = ('s3::https://gradiated-prod-model-artifacts-873716897517.s3.us-east-1.amazonaws.com'
                  f'/bundles/sha256/{third}.tar.gz')
        result = shell(f'{self.host()}/fetch-runtime {source} {third} {ROOT}/bundles/{third}', user='downloader')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Bundle download completed', result.stdout)
        self.assertEqual(shell(f'cat {ROOT}/bundles/{third}/name', user='runtime').stdout, 'third')

    def test_agent_stages_runtimes_as_the_downloader(self):
        self.require('enroll', 'stage')
        self.assertEqual(sorted(RESULTS['runtimes'][:2]), RESULTS['stage']['value'])

    def test_runtime_writes_its_caches(self):
        self.require('task')
        log = self.runtime_started()
        for directory in ('torchinductor', 'triton', 'huggingface/hub'):
            with self.subTest(directory=directory):
                self.assertIn(f'cache writable: /home/runtime/.cache/{directory}\n', log)

    def test_runtime_user_opens_the_gpu_locks_the_agent_holds(self):
        self.require('task')
        self.runtime_started()
        script = f'''
import fcntl, json, os
results = {{}}
for device in {GPUS!r}:
    path = '/home/runtime/.cache/gradiated/gpu-locks/' + device
    try:
        descriptor = os.open(path, os.O_RDWR)
    except OSError as error:
        results[device] = str(error)
        continue
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results[device] = 'not held by the agent'
    except BlockingIOError:
        results[device] = 'held'
print(json.dumps(results))
'''
        result = docker('exec', '-u', 'runtime', CONTAINER, 'python3', '-c', script)
        self.assertEqual(json.loads(result.stdout), {device: 'held' for device in GPUS})


if __name__ == '__main__':
    unittest.main()
