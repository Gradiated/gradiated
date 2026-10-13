#!/usr/bin/env python3
import signal
import subprocess
import threading

stopping = threading.Event()
reload = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stopping.set())
signal.signal(signal.SIGINT, lambda *_: stopping.set())
signal.signal(signal.SIGHUP, lambda *_: reload.set())
while not stopping.is_set():
    process = subprocess.Popen(['python3', '/opt/gradiated/kubelet/host-agent.py'])
    while not stopping.wait(1) and not reload.is_set() and process.poll() is None:
        pass
    reload.clear()
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    stopping.wait(2)
