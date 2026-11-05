from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from support import HOST, executable, host_bundle, mode, temporary_root

from gradiated_host import enroll
from gradiated_host.tailscale import Tailscale

INSTANCE = '019d5a4a-0000-7000-8000-000000000001'
TOKEN = 'management_' + 'x' * 40
# Two RTX PRO 6000 GPUs; compute processes listed in ./compute-apps.
NVIDIA_SMI = '''#!/usr/bin/env bash
here=$(dirname "$0")
case "$1" in
--query-gpu=uuid) printf '%s\\n' GPU-1 GPU-2 ;;
--query-gpu=name) printf '%s\\n' 'NVIDIA RTX PRO 6000 Blackwell Server Edition' 'NVIDIA RTX PRO 6000 Blackwell Server Edition' ;;
--query-compute-apps=pid) cat "$here/compute-apps" 2>/dev/null || true ;;
*) exit 1 ;;
esac
'''
TAILSCALE = '''#!/usr/bin/env bash
case "$2" in
status) cat "$(dirname "$0")/status.json" ;;
*) exit 1 ;;
esac
'''


class Agent(BaseHTTPRequestHandler):
    instance = INSTANCE

    def log_message(self, *_):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        if self.headers.get('Authorization') != f'Bearer {TOKEN}':
            self.send_error(403)
            return
        body = json.dumps({'instance_id': self.instance}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Enrollment(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.archive, self.digest = host_bundle()
        self.downloads = 0
        self.bin = executable(self.layout.root / 'bin' / 'nvidia-smi', NVIDIA_SMI).parent
        executable(self.layout.tailscale_bin / 'tailscale', TAILSCALE)
        self.set_status(['tag:gpu-bootstrap'])
        cgroup = self.layout.cgroup
        cgroup.mkdir(parents=True)
        (cgroup / 'cpu.max').write_text('3200000 100000\n')
        (cgroup / 'memory.max').write_text(str(250 * 1024 ** 3) + '\n')
        self.tailscale = Tailscale(self.layout)
        self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap')
        self.tailscale.auth_key.unlink()
        self.agent = ThreadingHTTPServer(('127.0.0.1', 0), Agent)
        threading.Thread(target=self.agent.serve_forever, daemon=True).start()
        self.addCleanup(self.agent.server_close)
        self.addCleanup(self.agent.shutdown)
        patcher = patch.dict(os.environ, {'PATH': f'{self.bin}:{os.environ["PATH"]}'})
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)

    def set_status(self, tags):
        (self.layout.tailscale_bin / 'status.json').write_text(json.dumps(
            {'BackendState': 'Running', 'TailscaleIPs': ['100.101.172.112', 'fd7a:115c:a1e0::1'],
             'Self': {'Tags': tags}}))

    def download(self, url, destination):
        self.downloads += 1
        Path(destination).write_bytes(self.archive)

    def payload(self, **changes):
        return {'version': 1, 'instance_id': INSTANCE, 'management_token': TOKEN,
                'auth_key': 'tskey-auth-inference', 'api_endpoint': '100.64.0.1',
                'host_bundle': {'sha256': self.digest, 'base_id': 'test-base', 'url': 'https://artifacts/host.tar.gz'},
                **changes}

    def enroll(self, payload=None, seconds=5):
        return enroll.enroll(payload or self.payload(), self.layout, self.download,
                             agent_port=self.agent.server_address[1], agent_seconds=seconds)

    def test_enrolls_a_bootstrap_pod_and_stages_its_promotion(self):
        result = self.enroll()
        self.assertEqual(result, {'version': 1, 'tailscale_ip': '100.101.172.112', 'gpu_count': 2,
                                  'gpu_product': 'RTX-PRO-6000', 'cpu': 28, 'memory_gib': 234, 'promotion': True})
        config = json.loads(self.layout.config.read_text())
        self.assertEqual(config, {'instance_id': INSTANCE, 'gpu_uuids': ['GPU-1', 'GPU-2'],
                                  'token_file': str(self.layout.management_token), 'runtimes': {}})
        self.assertEqual(self.layout.management_token.read_text(), TOKEN)
        self.assertEqual(json.loads(self.layout.control_config.read_text()), {'api': '100.64.0.1'})
        for path, expected in ((self.layout.config, 0o600), (self.layout.management_token, 0o600),
                               (self.layout.runtime_token, 0o600), (self.layout.control_config, 0o644)):
            self.assertEqual(mode(path), expected, path)
        self.assertTrue((self.layout.state / 'host' / self.digest / 'host-agent.py').is_file())
        self.assertEqual(mode(self.layout.state / 'bundles'), 0o755)
        self.assertEqual(self.tailscale.config(), {'pod': 'abc123', 'instance_id': INSTANCE})
        self.assertEqual(self.tailscale.auth_key.read_text(), 'tskey-auth-inference')
        self.assertGreater(json.loads(self.tailscale.reauth.read_text())['after'], 0)

    def test_running_enrollment_again_changes_nothing(self):
        self.enroll()
        token = self.layout.runtime_token.read_text()
        config = json.loads(self.layout.config.read_text())
        config['runtimes'] = {'a' * 64: {'image': 'staged'}}
        self.layout.config.write_text(json.dumps(config))
        self.enroll()
        self.assertEqual(self.downloads, 1)
        self.assertEqual(self.layout.runtime_token.read_text(), token)
        self.assertEqual(json.loads(self.layout.config.read_text())['runtimes'], config['runtimes'])

    def test_enrolls_two_h200_gpus(self):
        executable(self.bin / 'nvidia-smi', NVIDIA_SMI.replace(
            'NVIDIA RTX PRO 6000 Blackwell Server Edition', 'NVIDIA H200'))
        result = self.enroll()
        self.assertEqual(result['gpu_product'], 'H200')
        self.assertEqual(result['gpu_count'], 2)

    def test_rejects_mixed_gpu_products(self):
        executable(self.bin / 'nvidia-smi', NVIDIA_SMI.replace(
            'NVIDIA RTX PRO 6000 Blackwell Server Edition', 'NVIDIA H200', 1))
        with self.assertRaisesRegex(enroll.EnrollmentError, 'homogeneous'):
            self.enroll()

    def test_gh200_is_not_an_h200(self):
        executable(self.bin / 'nvidia-smi', NVIDIA_SMI.replace(
            'NVIDIA RTX PRO 6000 Blackwell Server Edition', 'NVIDIA GH200'))
        with self.assertRaisesRegex(enroll.EnrollmentError, 'homogeneous'):
            self.enroll()

    def test_a_retry_before_promotion_takes_effect_stages_the_new_key(self):
        self.enroll()
        # Still tagged as a bootstrap device: re-authentication has not happened yet.
        result = self.enroll(self.payload(auth_key='tskey-auth-retry'))
        self.assertTrue(result['promotion'])
        self.assertEqual(self.tailscale.auth_key.read_text(), 'tskey-auth-retry')
        self.assertEqual(self.downloads, 1)

    def test_after_a_failed_promotion_enrolling_again_promotes_the_pod(self):
        self.enroll()
        # Re-authentication failed: the supervisor discarded the key and the device is still bootstrap-tagged.
        self.tailscale.auth_key.unlink()
        self.tailscale.reauth.unlink()
        result = self.enroll(self.payload(auth_key='tskey-auth-retry'))
        self.assertTrue(result['promotion'])
        self.assertEqual(self.tailscale.auth_key.read_text(), 'tskey-auth-retry')
        self.assertTrue(self.tailscale.reauth.exists())

    def test_an_enrolled_inference_host_is_not_promoted_again(self):
        self.enroll()
        self.tailscale.auth_key.unlink()
        self.tailscale.reauth.unlink()
        self.set_status(['tag:gpu-inference'])
        result = self.enroll()
        self.assertFalse(result['promotion'])
        self.assertFalse(self.tailscale.auth_key.exists())

    def test_refuses_another_identity_or_token(self):
        self.enroll()
        for changes in ({'instance_id': '019d5a4a-0000-7000-8000-000000000002'},
                        {'management_token': 'another_' + 'y' * 40}):
            with self.subTest(changes=changes), self.assertRaisesRegex(enroll.EnrollmentError, 'different identity'):
                self.enroll(self.payload(**changes))

    def test_refuses_while_gpu_workloads_run_on_an_unenrolled_pod(self):
        (self.bin / 'compute-apps').write_text('4242\n')
        with self.assertRaisesRegex(enroll.EnrollmentError, 'drain'):
            self.enroll()
        self.assertFalse(self.layout.config.exists())

    def test_refuses_a_pod_whose_tailnet_identity_is_someone_else(self):
        self.layout.tailscale_config.write_text(json.dumps(
            {'pod': 'abc123', 'instance_id': '019d5a4a-0000-7000-8000-00000000ffff'}))
        with self.assertRaisesRegex(enroll.EnrollmentError, 'Tailscale'):
            self.enroll()

    def test_fails_when_the_host_agent_does_not_start(self):
        Agent.instance = 'another'
        self.addCleanup(setattr, Agent, 'instance', INSTANCE)
        with self.assertRaisesRegex(enroll.EnrollmentError, 'host agent'):
            self.enroll(seconds=1)
        self.assertFalse(self.tailscale.reauth.exists(), 'Promotion waits for a running host agent')

    def test_promotion_is_staged_only_after_the_result_is_ready(self):
        self.set_status([])
        with self.assertRaisesRegex(enroll.EnrollmentError, 'tailnet identity'):
            self.enroll()
        self.assertFalse(self.tailscale.reauth.exists())

    def test_reports_failures_without_credentials(self):
        payload = self.payload(management_token='short')
        environment = {**os.environ, 'PYTHONPATH': f'{HOST}:{HOST.parent / "gpu"}'}
        result = subprocess.run([sys.executable, '-m', 'gradiated_host', 'enroll'], env=environment,
                                input=json.dumps({**payload, 'auth_key': 'tskey-auth-SECRET'}),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('Enrollment failed', result.stderr)
        self.assertNotIn('SECRET', result.stderr)


if __name__ == '__main__':
    unittest.main()
