import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from config import MODEL, commands, validate_hardware


def backend_ready(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
        if response.status != 200:
            return False
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=2) as response:
        models = json.load(response)
    return MODEL in [row.get('id') for row in models.get('data', [])]


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
    config, backend, router = commands(environment)
    validate_hardware(environment)
    stopping = threading.Event()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda *_: stopping.set())
    children = []
    try:
        children.append(subprocess.Popen(backend))
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
        return 0
    finally:
        stop_children(children)


if __name__ == '__main__':
    raise SystemExit(run())
