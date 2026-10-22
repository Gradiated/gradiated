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
        return config

    def _write(self, path, data):
        files.write(path, data, 0o600, self.layout.account('root'))

    def join_as_bootstrap(self, pod, key):
        # A saved identity is never replaced.
        if self.layout.tailscale_config.exists() or (self.state / 'state').exists():
            return False
        if not POD_ID.fullmatch(pod) or not AUTH_KEY.fullmatch(key):
            raise ValueError('A new GPU pod needs RUNPOD_POD_ID and GRADIATED_TAILSCALE_BOOTSTRAP_KEY')
        files.directory(self.state, 0o700, self.layout.account(TAILSCALE))
        self._write(self.auth_key, key)
        self._write(self.layout.tailscale_config, json.dumps({'pod': pod}))
        return True

    def stage_promotion(self, instance_id, key):
        config = self.config()
        if config is None or config.get('instance_id', instance_id) != instance_id:
            raise ValueError('This pod is staged for another host identity')
        if not AUTH_KEY.fullmatch(key):
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
