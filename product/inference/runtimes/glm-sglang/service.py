import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from config import MODEL, commands, detect_profile, validate_hardware


def backend_ready(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
        if response.status != 200:
            return False
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=2) as response:
        models = json.load(response)
    return MODEL in [row.get('id') for row in models.get('data', [])]


LIVETUNE_MODES = {'off', 'observe', 'act'}
CONTROLLER_BACKOFF_SECONDS = (30, 600)
CONTROLLER_CONFIG_ERROR = 78  # livetune.cli.CONFIG_ERROR


def livetune(environment, config):
    """The live-tuning controller command, or None, and the backend environment it needs.

    Off by default. observe records traffic and logs what the bundle's policy would change; act also
    applies it. The policy ships in the bundle per hardware profile, so a change to it is a reviewed
    bundle release; a profile without one records traffic and runs no controller.
    """
    mode = environment.get('LIVETUNE_MODE', 'off')
    if mode not in LIVETUNE_MODES:
        raise ValueError('LIVETUNE_MODE must be off, observe or act')
    if mode == 'off':
        return None, {}
    cache = Path(environment.get('XDG_CACHE_HOME') or Path(environment.get('HOME', '/home/runtime')) / '.cache')
    backend_environment = {'LIVETUNE_TRACE_DIR': str(cache / 'glm-sglang' / 'livetune' / 'trace')}
    policy = Path(config['root']) / 'glm-sglang' / 'livetune' / f"{config['profile']}.json"
    if not policy.is_file():
        return None, backend_environment
    command = [str(Path(config['root']) / 'python/bin/python3'), '-m', 'livetune.cli', 'control',
               '--url', f"http://127.0.0.1:{config['backend']}", '--policy', str(policy),
               '--mode', mode, '--log-every', '300']
    return command, backend_environment


class Controller:
    """Keeps the controller running beside serving; its exit never stops SGLang or SMG."""

    def __init__(self, command, clock=time.monotonic, start=subprocess.Popen):
        self.command, self.clock, self.start = command, clock, start
        self.child, self.failures, self.restart_at, self.started_at = None, 0, 0.0, 0.0

    def tick(self):
        if self.command is None:
            return
        now = self.clock()
        code = self.child.poll() if self.child is not None else None
        if code == CONTROLLER_CONFIG_ERROR:
            # The bundled policy does not fit this server; a restart would refuse it again.
            print('livetune controller refused its policy; not restarting it', file=sys.stderr, flush=True)
            self.command, self.child = None, None
            return
        if code is not None:
            # A controller that ran for a while had a transient failure; one that keeps dying backs off.
            self.failures = 1 if now - self.started_at > CONTROLLER_BACKOFF_SECONDS[1] else self.failures + 1
            delay = min(CONTROLLER_BACKOFF_SECONDS[0] * 2 ** (self.failures - 1), CONTROLLER_BACKOFF_SECONDS[1])
            print(f'livetune controller exited with {code}; restarting in {delay}s', file=sys.stderr, flush=True)
            self.child, self.restart_at = None, now + delay
        if self.child is None and now >= self.restart_at:
            self.child, self.started_at = self.start(self.command), now

    def children(self):
        return [self.child] if self.child is not None else []


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 20
    for child in children:
        try:
            child.wait(timeout=max(.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def run(environment=os.environ):
    environment = detect_profile(environment)
    config, backend, router = commands(environment)
    validate_hardware(environment)
    controller_command, backend_environment = livetune(environment, config)
    stopping = threading.Event()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda *_: stopping.set())
    children = []
    controller = Controller(controller_command)
    try:
        children.append(subprocess.Popen(backend, env={**environment, **backend_environment}) if backend_environment
                        else subprocess.Popen(backend))
        deadline = time.monotonic() + int(environment.get('RUNTIME_STARTUP_TIMEOUT_SECONDS', '3600'))
        while not stopping.is_set():
            if children[0].poll() is not None:
                raise RuntimeError('SGLang exited before router startup')
            if time.monotonic() >= deadline:
                raise TimeoutError('SGLang startup deadline')
            try:
                if backend_ready(config['backend']):
                    break
            except (OSError, TimeoutError):
                pass
            stopping.wait(1)
        if stopping.is_set():
            return 0
        children.append(subprocess.Popen(router))
        while not stopping.wait(.25):
            if any(child.poll() is not None for child in children):
                raise RuntimeError('SGLang or SMG exited')
            controller.tick()
        return 0
    finally:
        stop_children(controller.children() + children)


if __name__ == '__main__':
    raise SystemExit(run())
