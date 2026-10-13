#!/usr/bin/env python3
import ipaddress
import json
import selectors
import signal
import socket
import subprocess
import threading
from pathlib import Path

ENDPOINTS = {
    "api": ("127.0.0.1", 3004),
}
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def routes(config):
    if set(config) != set(ENDPOINTS):
        raise ValueError("Missing private control endpoint")
    result = []
    for name, address in config.items():
        local = ENDPOINTS[name]
        address = ipaddress.ip_address(address)
        if address not in TAILNET:
            raise ValueError("Control endpoints must be tailnet addresses")
        result.append((local, str(address)))
    return result


def serve(config):
    targets = routes(config)
    children = set()
    lock = threading.Lock()
    slots = threading.BoundedSemaphore(64)
    selector = selectors.DefaultSelector()

    def stop(signum, frame):
        with lock:
            for child in children:
                child.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def forward(connection, target, port):
        child = None
        try:
            with connection:
                child = subprocess.Popen(
                    [
                        "/opt/gradiated/tailscale/tailscale",
                        "--socket=/var/lib/gradiated-tailscale/socket",
                        "nc",
                        target,
                        str(port),
                    ],
                    stdin=connection,
                    stdout=connection,
                    stderr=subprocess.DEVNULL,
                )
                with lock:
                    children.add(child)
                child.wait()
        finally:
            if child:
                with lock:
                    children.discard(child)
            slots.release()

    try:
        for (address, port), target in targets:
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((address, port))
            listener.listen(64)
            selector.register(listener, selectors.EVENT_READ, (target, port))
        while True:
            for key, _ in selector.select():
                connection, _ = key.fileobj.accept()
                if not slots.acquire(blocking=False):
                    connection.close()
                    continue
                threading.Thread(
                    target=forward, args=(connection, *key.data), daemon=True
                ).start()
    finally:
        for key in list(selector.get_map().values()):
            key.fileobj.close()
        selector.close()


if __name__ == "__main__":
    serve(json.loads(Path("/etc/gradiated/tailscale-control.json").read_text()))
