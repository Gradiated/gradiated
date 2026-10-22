# Forwards 127.0.0.1:3004 to the control API over the tailnet, one `tailscale nc` per connection.
import ipaddress
import json
import selectors
import signal
import socket
import subprocess
import threading

from .paths import CONTROL_PORT, TAILNET


def target(config):
    if set(config) != {'api'}:
        raise ValueError('The control configuration names exactly the api endpoint')
    address = ipaddress.ip_address(config['api'])
    if address.version != 4 or address not in TAILNET:
        raise ValueError('The control endpoint must be a tailnet address')
    return str(address)


def serve(config, cli, tailscale_socket, address=('127.0.0.1', CONTROL_PORT), slots=64, ready=None, stop=None):
    destination = target(config)
    available = threading.BoundedSemaphore(slots)
    children = set()
    lock = threading.Lock()
    stop = stop or threading.Event()

    def forward(connection):
        try:
            with connection:
                child = subprocess.Popen([str(cli), f'--socket={tailscale_socket}', 'nc', destination, str(CONTROL_PORT)],
                                         stdin=connection, stdout=connection, stderr=subprocess.DEVNULL)
                with lock:
                    children.add(child)
                child.wait()
                with lock:
                    children.discard(child)
        finally:
            available.release()

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(address)
    listener.listen(64)
    selector = selectors.DefaultSelector()
    selector.register(listener, selectors.EVENT_READ)
    if ready is not None:
        ready(listener.getsockname()[1])
    try:
        while not stop.is_set():
            if not selector.select(timeout=.5):
                continue
            connection, _ = listener.accept()
            if not available.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(target=forward, args=(connection,), daemon=True).start()
    finally:
        selector.close()
        listener.close()
        with lock:
            for child in children:
                child.terminate()


def main(layout):
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    config = json.loads(layout.control_config.read_text())
    serve(config, layout.tailscale_bin / 'tailscale', layout.tailscale_state / 'socket', stop=stop)
