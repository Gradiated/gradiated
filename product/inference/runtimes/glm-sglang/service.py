import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from config import backend_environment, commands, detect_profile, hicache_directory, hold_hicache, prune_hicache, validate_hardware


def backend_ready(port, model):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
        if response.status != 200:
            return False
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=2) as response:
        models = json.load(response)
    return model in [row.get('id') for row in models.get('data', [])]


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
    directory = hicache_directory(environment, config) if config.get('hicache') else None
    hicache_lock = hold_hicache(directory) if directory else None
    stopping = threading.Event()
    if directory:
        prune_hicache(environment, directory)

        def keep_pruning():
            # Leaves go idle after this start too (other replicas stop, rollouts finish).
            while not stopping.wait(600):
                prune_hicache(environment, directory)
        threading.Thread(target=keep_pruning, daemon=True).start()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, lambda *_: stopping.set())
    children = []
    adapters = None
    try:
        engine_environment = environment
        if config['lora']:
            # The adapter service runs beside the engine: SGLang calls its resolver for an
            # unknown adapter name, and it preloads production adapters after warmup.
            from adapter_service import start
            adapters, engine_environment = start(
                environment, config['model'], config['revision'], config.get('tp', 2), config['backend'],
                # Not started yet counts as alive: the watcher may run before the engine is published.
                lambda: not children or children[0].poll() is None)
        children.append(subprocess.Popen(backend, env=backend_environment(engine_environment, config)))
        deadline = time.monotonic() + int(environment.get('RUNTIME_STARTUP_TIMEOUT_SECONDS', '3600'))
        while not stopping.is_set():
            if children[0].poll() is not None:
                raise RuntimeError('SGLang exited before router startup')
            if time.monotonic() >= deadline:
                raise TimeoutError('SGLang startup deadline')
            try:
                if backend_ready(config['backend'], config['served_model_name']):
                    break
            except (OSError, TimeoutError):
                pass
            stopping.wait(1)
        if stopping.is_set():
            return 0
        # SMG forwards adapter names, which no worker advertises, to the engine's resolver.
        router_environment = {**environment, 'SMG_ROUTE_UNKNOWN_MODELS': '1'} if config['lora'] else None
        children.append(subprocess.Popen(router, env=router_environment))
        while not stopping.wait(.25):
            if any(child.poll() is not None for child in children):
                raise RuntimeError('SGLang or SMG exited')
        return 0
    finally:
        stop_children(children)
        if adapters is not None:
            adapters.stop()


if __name__ == '__main__':
    raise SystemExit(run())
