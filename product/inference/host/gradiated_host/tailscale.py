import json
import re
import subprocess
import time
import uuid

from . import files
from .paths import PROXY_PORT, SERVE_PORT, TAILSCALE

BOOTSTRAP_TAG = 'tag:gpu-bootstrap'
INFERENCE_TAG = 'tag:gpu-inference'
POD_ID = re.compile(r'[a-z0-9]{1,40}')
AUTH_KEY = re.compile(r'tskey-auth-[A-Za-z0-9-]{1,200}')
# The end-to-end test's control server (headscale) issues these.
TEST_AUTH_KEY = re.compile(r'hskey-auth-[A-Za-z0-9_-]{1,200}')
# Production uses Tailscale's control server. Only an image carrying the test
# marker (Layout.test_control_server) may join another one; the setting is
# recorded at the first join so restarts and promotion use the same server.
LOGIN_SERVER = re.compile(r'https://[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?(?::[0-9]{1,5})?')
# Re-authentication drops the Tailscale SSH session that enrollment runs in, so it
# waits until enrollment has returned its result.
PROMOTION_DELAY = 10
RECONCILE_SECONDS = 2


def inference_hostname(instance_id):
    return 'gpu-' + str(uuid.UUID(instance_id))


def tags(status):
    if (status or {}).get('BackendState') != 'Running':
        return []
    return (status.get('Self') or {}).get('Tags') or []


class Tailscale:
    # tailscale.json holds the pod ID and, once promotion is staged, the instance ID. The live
    # tags decide bootstrap or inference, so a failed promotion leaves a retryable bootstrap device.
    def __init__(self, layout, clock=time.time):
        self.layout = layout
        self.clock = clock
        self.state = layout.tailscale_state
        self.socket = self.state / 'socket'
        self.auth_key = self.state / 'auth-key'
        self.reauth = self.state / 'reauth'
        self.cli = layout.tailscale_bin / 'tailscale'
        self.daemon = layout.tailscale_bin / 'tailscaled'

    def config(self):
        try:
            config = json.loads(self.layout.tailscale_config.read_text())
        except (FileNotFoundError, ValueError):
            return None
        if not isinstance(config, dict) or not POD_ID.fullmatch(str(config.get('pod', ''))):
            return None
        if 'instance_id' in config and config['instance_id'] != str(uuid.UUID(str(config['instance_id']))):
            return None
        if 'login_server' in config and not LOGIN_SERVER.fullmatch(str(config['login_server'])):
            return None
        return config

    def login_server(self):
        # A recorded server counts only on an image built for the end-to-end test.
        if not self.layout.test_control_server.exists():
            return None
        return (self.config() or {}).get('login_server')

    def _valid_key(self, key, login_server):
        return bool(AUTH_KEY.fullmatch(key) or (login_server and TEST_AUTH_KEY.fullmatch(key)))

    def _write(self, path, data):
        files.write(path, data, 0o600, self.layout.account('root'))

    def join_as_bootstrap(self, pod, key, login_server=''):
        # A saved identity is never replaced.
        if self.layout.tailscale_config.exists() or (self.state / 'state').exists():
            return False
        if login_server and not self.layout.test_control_server.exists():
            # A production image always joins Tailscale's control server.
            login_server = ''
        if login_server and not LOGIN_SERVER.fullmatch(login_server):
            raise ValueError('GRADIATED_TAILSCALE_LOGIN_SERVER must be https://<host>[:<port>]')
        if not POD_ID.fullmatch(pod) or not self._valid_key(key, login_server):
            raise ValueError('A new GPU pod needs RUNPOD_POD_ID and GRADIATED_TAILSCALE_BOOTSTRAP_KEY')
        files.directory(self.state, 0o700, self.layout.account(TAILSCALE))
        self._write(self.auth_key, key)
        self._write(self.layout.tailscale_config,
                    json.dumps({'pod': pod, **({'login_server': login_server} if login_server else {})}))
        return True

    def stage_promotion(self, instance_id, key):
        config = self.config()
        if config is None or config.get('instance_id', instance_id) != instance_id:
            raise ValueError('This pod is staged for another host identity')
        if not self._valid_key(key, self.login_server()):
            raise ValueError('Invalid Tailscale auth key')
        self._write(self.auth_key, key)
        self._write(self.reauth, json.dumps({'after': self.clock() + PROMOTION_DELAY}))
        self._write(self.layout.tailscale_config, json.dumps({**config, 'instance_id': instance_id}))

    def promotion_due(self):
        try:
            return json.loads(self.reauth.read_text())['after'] <= self.clock()
        except FileNotFoundError:
            return False
        except (ValueError, KeyError, TypeError):
            return True

    def status(self):
        result = subprocess.run([str(self.cli), f'--socket={self.socket}', 'status', '--json'],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode:
            return None
        try:
            return json.loads(result.stdout)
        except ValueError:
            return None

    def next_step(self, status):
        config = self.config()
        if config is None:
            return None
        current = tags(status)
        if INFERENCE_TAG in current:
            return ('inference', inference_hostname(config['instance_id'])) if 'instance_id' in config else None
        if (status or {}).get('BackendState') != 'NeedsLogin' and BOOTSTRAP_TAG not in current:
            return None
        if BOOTSTRAP_TAG in current and 'instance_id' in config and self.reauth.exists() \
                and self.auth_key.exists() and self.promotion_due():
            return ('promote', inference_hostname(config['instance_id']))
        return ('bootstrap', f'gpu-bootstrap-{config["pod"]}')

    def up_arguments(self, hostname, key=False, reauth=False):
        # --ssh enables Tailscale SSH, the only shell access; the tailnet policy limits it.
        # The tailscale account gets LocalAPI access for the control bridge.
        arguments = [f'--hostname={hostname}', '--accept-dns=false', '--accept-routes=false',
                     '--ssh', f'--operator={TAILSCALE}', '--timeout=30s']
        login_server = self.login_server()
        if login_server:
            arguments.append(f'--login-server={login_server}')
        if key:
            arguments.append(f'--auth-key=file:{self.auth_key}')
        if reauth:
            arguments.append('--force-reauth')
        return arguments

    def _cli(self, *arguments, log):
        return subprocess.run([str(self.cli), f'--socket={self.socket}', *arguments],
                              stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=60, check=False).returncode

    def apply(self, step, status, log):
        kind, hostname = step
        if kind == 'promote':
            succeeded = not self._cli('up', *self.up_arguments(hostname, key=True, reauth=True), log=log)
            if not succeeded:
                log.write(b'Tailscale re-authentication failed; staying a bootstrap device\n')
            self.auth_key.unlink(missing_ok=True)
            self.reauth.unlink(missing_ok=True)
            return succeeded
        if kind == 'inference':
            # Only a tag:gpu-inference device serves the host agent proxy.
            return not self._cli('up', *self.up_arguments(hostname), log=log) and not self._cli(
                'serve', '--bg', f'--tcp={SERVE_PORT}', f'tcp://127.0.0.1:{PROXY_PORT}', log=log)
        login = status.get('BackendState') == 'NeedsLogin' and self.auth_key.exists() and not self.reauth.exists()
        if self._cli('up', *self.up_arguments(hostname, key=login), log=log):
            return False
        if login:
            self.auth_key.unlink(missing_ok=True)
        return True

    def _wait_for_socket(self, daemon, stop, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and daemon.poll() is None and not stop.is_set():
            if self.socket.is_socket():
                return True
            stop.wait(.2)
        return False

    def _reconcile(self, daemon, stop, log):
        applied = None
        while daemon.poll() is None and not stop.is_set():
            status = self.status() or {}
            step = self.next_step(status)
            if step is not None and step != applied:
                applied = step if self.apply(step, status, log) else None
            stop.wait(RECONCILE_SECONDS)

    def run(self, stop, log):
        # tailscaled runs as root so that Tailscale SSH can open administrator shells.
        while not stop.is_set():
            if self.config() is None:
                stop.wait(2)
                continue
            self.socket.unlink(missing_ok=True)
            # --statedir keeps the SSH host keys; without it Tailscale SSH stays off.
            daemon = subprocess.Popen(
                [str(self.daemon), '--tun=userspace-networking', f'--state={self.state / "state"}',
                 f'--statedir={self.state}', f'--socket={self.socket}', '--port=41641'],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            try:
                if self._wait_for_socket(daemon, stop):
                    self._reconcile(daemon, stop, log)
            finally:
                daemon.terminate()
                try:
                    daemon.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait()
            stop.wait(2)
