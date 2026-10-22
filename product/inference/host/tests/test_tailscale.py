import json
import os
import signal
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

from support import executable, mode, temporary_root

from gradiated_host import tailscale as tailscale_module
from gradiated_host.tailscale import Tailscale

INSTANCE = '019d5a4a-0000-7000-8000-000000000001'
DAEMON = '''#!/usr/bin/env python3
import os, signal, socket, sys, time
path = next(a.split('=', 1)[1] for a in sys.argv if a.startswith('--socket='))
with open(os.path.join(os.path.dirname(sys.argv[0]), 'daemons'), 'a') as log:
    log.write(f'{os.getpid()}\\n')
listener = socket.socket(socket.AF_UNIX)
listener.bind(path)
listener.listen()
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True:
    time.sleep(1)
'''
# Records each call except status. Like the real CLI, `up` with a key logs the device in
# (as a bootstrap device, or with --force-reauth as an inference device) and `status`
# reports it. Flags in its directory make `up` or re-authentication fail.
CLI = '''#!/usr/bin/env bash
here=$(dirname "$0")
status="$here/status.json"
running() { printf '{"BackendState":"Running","TailscaleIPs":["100.64.0.9"],"Self":{"Tags":["%s"]}}' "$1" >"$status"; }
[[ "$2" == status ]] || printf '%s\\n' "$*" >>"$here/calls"
case "$2" in
status) if [[ -f "$status" ]]; then cat "$status"; else echo '{"BackendState":"NeedsLogin"}'; fi ;;
up)
  [[ ! -e "$here/fail-up" ]] || exit 1
  if [[ "$*" == *--force-reauth* ]]; then
    [[ ! -e "$here/fail-reauth" ]] || exit 1
    running tag:gpu-inference
  elif [[ "$*" == *--auth-key=* ]]; then
    running tag:gpu-bootstrap
  else
    [[ -f "$status" ]] || exit 1
  fi ;;
serve) ;;
*) exit 1 ;;
esac
'''


class Identity(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.now = 1000.0
        self.tailscale = Tailscale(self.layout, clock=lambda: self.now)

    def test_a_new_pod_joins_with_its_bootstrap_key(self):
        self.assertTrue(self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap'))
        self.assertEqual(self.tailscale.config(), {'pod': 'abc123'})
        self.assertEqual(self.tailscale.auth_key.read_text(), 'tskey-auth-bootstrap')
        for path in (self.tailscale.auth_key, self.layout.tailscale_config):
            self.assertEqual(mode(path), 0o600)

    def test_a_production_image_ignores_a_login_server_and_test_keys(self):
        # A pod environment must never send the bootstrap key to another control server.
        self.assertTrue(self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap', 'https://attacker.example'))
        self.assertEqual(self.tailscale.config(), {'pod': 'abc123'})
        self.assertFalse(any(a.startswith('--login-server') for a in self.tailscale.up_arguments('x', key=True)))
        with self.assertRaises(ValueError):
            self.tailscale.stage_promotion(INSTANCE, 'hskey-auth-inference_1')
        # A recorded server is ignored too, should one ever reach a production image.
        self.layout.tailscale_config.write_text(json.dumps({'pod': 'abc123', 'login_server': 'https://attacker.example'}))
        self.assertIsNone(self.tailscale.login_server())
        self.assertFalse(any(a.startswith('--login-server') for a in self.tailscale.up_arguments('x', key=True)))

    def test_only_the_end_to_end_image_carries_the_test_marker(self):
        dockerfile = Path(__file__).resolve().parents[2] / 'images' / 'gpu-base' / 'Dockerfile'
        self.assertNotIn('test-control-server', dockerfile.read_text())

    def test_a_production_image_rejects_test_bootstrap_keys(self):
        with self.assertRaises(ValueError):
            self.tailscale.join_as_bootstrap('abc123', 'hskey-auth-bootstrap_1', 'https://headscale')

    def test_a_custom_login_server_is_recorded_and_used_for_every_login(self):
        self.layout.test_control_server.write_text('')
        self.assertTrue(self.tailscale.join_as_bootstrap('abc123', 'hskey-auth-bootstrap_1', 'https://headscale'))
        self.assertEqual(self.tailscale.config(), {'pod': 'abc123', 'login_server': 'https://headscale'})
        self.tailscale.stage_promotion(INSTANCE, 'hskey-auth-inference_1')
        for arguments in (self.tailscale.up_arguments('gpu-bootstrap-abc123'),
                          self.tailscale.up_arguments(f'gpu-{INSTANCE}', key=True, reauth=True)):
            self.assertIn('--login-server=https://headscale', arguments)

    def test_a_login_server_must_be_a_plain_https_origin(self):
        self.layout.test_control_server.write_text('')
        for server in ('http://headscale', 'https://headscale/path', 'https://user@headscale', 'https://-x',
                       'https://headscale:443 --ssh=false'):
            with self.subTest(server=server), self.assertRaises(ValueError):
                self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap', server)
        self.layout.tailscale_config.write_text(json.dumps({'pod': 'abc123', 'login_server': 'http://x'}))
        self.assertIsNone(self.tailscale.config())

    def test_a_saved_identity_is_never_replaced(self):
        (self.layout.tailscale_state / 'state').write_text('enrolled')
        self.assertFalse(self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap'))
        self.assertIsNone(self.tailscale.config())

    def test_a_new_pod_needs_a_valid_pod_id_and_key(self):
        for pod, key in (('', 'tskey-auth-x'), ('ABC', 'tskey-auth-x'), ('abc', ''), ('abc', 'ssh-ed25519 AAAA')):
            with self.subTest(pod=pod, key=key), self.assertRaises(ValueError):
                self.tailscale.join_as_bootstrap(pod, key)

    def test_promotion_is_staged_once_for_one_host_identity(self):
        with self.assertRaises(ValueError):
            self.tailscale.stage_promotion(INSTANCE, 'tskey-auth-inference')
        self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap')
        self.tailscale.stage_promotion(INSTANCE, 'tskey-auth-inference')
        self.assertEqual(self.tailscale.config(), {'pod': 'abc123', 'instance_id': INSTANCE})
        self.assertEqual(self.tailscale.auth_key.read_text(), 'tskey-auth-inference')
        self.assertFalse(self.tailscale.promotion_due())
        self.now += tailscale_module.PROMOTION_DELAY
        self.assertTrue(self.tailscale.promotion_due())
        with self.assertRaises(ValueError):
            self.tailscale.stage_promotion('019d5a4a-0000-7000-8000-000000000002', 'tskey-auth-other')

    def test_the_next_step_follows_the_live_tags(self):
        self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap')
        bootstrap = {'BackendState': 'Running', 'Self': {'Tags': ['tag:gpu-bootstrap']}}
        inference = {'BackendState': 'Running', 'Self': {'Tags': ['tag:gpu-inference']}}
        self.assertEqual(self.tailscale.next_step({'BackendState': 'NeedsLogin'}), ('bootstrap', 'gpu-bootstrap-abc123'))
        self.assertIsNone(self.tailscale.next_step({'BackendState': 'Starting'}))
        self.assertEqual(self.tailscale.next_step(bootstrap), ('bootstrap', 'gpu-bootstrap-abc123'))
        self.tailscale.stage_promotion(INSTANCE, 'tskey-auth-inference')
        self.assertEqual(self.tailscale.next_step(bootstrap), ('bootstrap', 'gpu-bootstrap-abc123'))
        self.now += tailscale_module.PROMOTION_DELAY
        self.assertEqual(self.tailscale.next_step(bootstrap), ('promote', f'gpu-{INSTANCE}'))
        self.assertEqual(self.tailscale.next_step(inference), ('inference', f'gpu-{INSTANCE}'))

    def test_the_key_is_passed_by_file(self):
        self.assertEqual(self.tailscale.up_arguments('gpu-bootstrap-abc'), [
            '--hostname=gpu-bootstrap-abc', '--accept-dns=false', '--accept-routes=false', '--ssh',
            '--operator=tailscale', '--timeout=30s'])
        self.assertEqual(self.tailscale.up_arguments('gpu-x', key=True, reauth=True)[-2:],
                         [f'--auth-key=file:{self.tailscale.auth_key}', '--force-reauth'])


class Supervision(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.now = 1000.0
        self.bin = self.layout.tailscale_bin
        executable(self.bin / 'tailscaled', DAEMON)
        executable(self.bin / 'tailscale', CLI)
        self.tailscale = Tailscale(self.layout, clock=lambda: self.now)
        self.stop = threading.Event()
        self.log = open(self.layout.logs / 'tailscale.log', 'ab')
        self.addCleanup(self.log.close)
        patcher = unittest.mock.patch.object(tailscale_module, 'RECONCILE_SECONDS', .1)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_supervisor(self):
        thread = threading.Thread(target=self.tailscale.run, args=(self.stop, self.log), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 20)
        self.addCleanup(self.stop.set)

    def calls(self, kind=''):
        path = self.bin / 'calls'
        lines = path.read_text().splitlines() if path.exists() else []
        return [line for line in lines if f' {kind} ' in line] if kind else lines

    def daemons(self):
        path = self.bin / 'daemons'
        return path.read_text().split() if path.exists() else []

    def wait(self, condition, seconds=15):
        deadline = time.monotonic() + seconds
        while not condition():
            if time.monotonic() > deadline:
                self.fail(f'Timed out; calls: {self.calls()}')
            time.sleep(.05)

    def joined(self):
        self.tailscale.join_as_bootstrap('abc123', 'tskey-auth-bootstrap')
        self.run_supervisor()
        self.wait(lambda: not self.tailscale.auth_key.exists())

    def promote(self):
        self.tailscale.stage_promotion(INSTANCE, 'tskey-auth-inference')
        self.now += tailscale_module.PROMOTION_DELAY

    def test_bootstrap_pod_joins_without_serving_and_consumes_its_key(self):
        self.joined()
        time.sleep(.5)
        self.assertEqual(self.calls('up'), [f'--socket={self.tailscale.socket} up --hostname=gpu-bootstrap-abc123 '
                                            '--accept-dns=false --accept-routes=false --ssh --operator=tailscale '
                                            f'--timeout=30s --auth-key=file:{self.tailscale.auth_key}'])
        self.assertEqual(self.calls('serve'), [])
        self.assertNotIn('tskey-auth', '\n'.join(self.calls()))

    def test_a_daemon_that_exits_is_restarted(self):
        self.joined()
        self.wait(lambda: len(self.daemons()) == 1)
        os.kill(int(self.daemons()[0]), signal.SIGKILL)
        self.wait(lambda: len(self.calls('up')) == 2)
        self.assertEqual(len(self.daemons()), 2)

    def test_promotion_waits_for_its_delay_then_serves_the_agent_proxy(self):
        self.joined()
        self.tailscale.stage_promotion(INSTANCE, 'tskey-auth-inference')
        time.sleep(1)
        self.assertEqual(len(self.calls('up')), 1, 'Promotion must wait for its delay')
        self.now += tailscale_module.PROMOTION_DELAY
        self.wait(lambda: self.calls('serve'))
        up = self.calls('up')
        self.assertTrue(up[1].endswith(f'--hostname=gpu-{INSTANCE} --accept-dns=false --accept-routes=false --ssh '
                                       f'--operator=tailscale --timeout=30s --auth-key=file:{self.tailscale.auth_key} '
                                       '--force-reauth'))
        self.assertIn(f'--hostname=gpu-{INSTANCE}', up[2])
        self.assertEqual(self.calls('serve')[0].split(' ', 1)[1], 'serve --bg --tcp=8888 tcp://127.0.0.1:8889')
        self.assertFalse(self.tailscale.auth_key.exists())
        self.assertFalse(self.tailscale.reauth.exists())

    def test_a_failed_promotion_returns_to_bootstrap_and_a_retry_succeeds(self):
        self.joined()
        (self.bin / 'fail-reauth').touch()
        self.promote()
        self.wait(lambda: any('--force-reauth' in call for call in self.calls('up')))
        self.wait(lambda: self.calls('up')[-1].endswith('--timeout=30s') and 'gpu-bootstrap-abc123' in self.calls('up')[-1])
        self.assertFalse(self.tailscale.auth_key.exists())
        self.assertFalse(self.tailscale.reauth.exists())
        self.assertEqual(self.calls('serve'), [], 'A bootstrap-tagged device never serves')

        (self.bin / 'fail-reauth').unlink()
        self.promote()
        self.wait(lambda: self.calls('serve'))
        self.assertIn(f'--hostname=gpu-{INSTANCE}', self.calls('up')[-1])

    def test_an_enrolled_host_resumes_as_itself_after_a_restart(self):
        self.joined()
        self.promote()
        self.wait(lambda: self.calls('serve'))
        self.stop.set()
        time.sleep(1)
        self.stop.clear()
        before = len(self.calls('up'))
        self.run_supervisor()
        self.wait(lambda: len(self.calls('serve')) == 2)
        self.assertEqual(self.calls('up')[before:], [
            f'--socket={self.tailscale.socket} up --hostname=gpu-{INSTANCE} --accept-dns=false '
            '--accept-routes=false --ssh --operator=tailscale --timeout=30s'])

    def test_an_invalid_configuration_never_starts_the_daemon(self):
        self.layout.tailscale_config.write_text(json.dumps({'pod': 'NOT VALID'}))
        self.run_supervisor()
        time.sleep(1)
        self.assertEqual(self.daemons(), [])


if __name__ == '__main__':
    unittest.main()
