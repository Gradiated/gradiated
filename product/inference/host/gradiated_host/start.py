import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback

from . import files
from .paths import TAILSCALE, Layout
from .tailscale import Tailscale

PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
# Removed from the environment so no child inherits a credential or a retired setting.
SECRETS = ('GRADIATED_TAILSCALE_BOOTSTRAP_KEY', 'GRADIATED_GPU_BOOTSTRAP', 'GRADIATED_BREAK_GLASS_SSH', 'PUBLIC_KEY')


class Service:

    def __init__(self, name, command, wanted, log, **options):
        self.name, self.command, self.wanted, self.log, self.options = name, command, wanted, log, options
        self.process = None

    def ensure(self):
        if self.process is not None and self.process.poll() is None:
            return
        if self.process is not None:
            print(f'{self.name} exited with status {self.process.returncode}', flush=True)
            self.process = None
        if self.wanted():
            self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL, stdout=self.log,
                                            stderr=self.log, **self.options)

    def terminate(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def wait(self, deadline):
        if self.process is None:
            return
        try:
            self.process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


# Signals every service first, so each gets the whole grace period to stop its children.
def stop_all(supervised, seconds=15):
    for service in supervised:
        service.terminate()
    deadline = time.monotonic() + seconds
    for service in supervised:
        service.wait(deadline)


def services(layout):
    package = str(Path(__file__).resolve().parents[1])
    supervisor = layout.install / 'supervise.py'
    return [
        # -P and cwd keep the working directory off the import path of a process that can use
        # the Tailscale LocalAPI.
        Service('control bridge', [sys.executable, '-B', '-P', '-m', 'gradiated_host', 'control'],
                layout.control_config.exists, files.log(layout.logs / 'gradiated-control.log'),
                env={'PATH': PATH, 'PYTHONPATH': package}, cwd='/', user=TAILSCALE, group=TAILSCALE,
                extra_groups=[]),
        Service('host agent launcher', [sys.executable, '-B', str(supervisor)],
                lambda: layout.config.exists() and supervisor.exists(),
                files.log(layout.logs / 'gradiated-kubelet.log'), env={'PATH': PATH}, cwd='/'),
    ]


def keep_running(action, stop, name):
    while not stop.is_set():
        try:
            action()
        except Exception:  # noqa: BLE001 - the supervisor must outlive any one failure
            print(f'{name} failed:\n{traceback.format_exc()}', flush=True)
        stop.wait(2)


def main(layout=Layout(), environ=os.environ, stop=None, supervised=None):
    key = environ.pop('GRADIATED_TAILSCALE_BOOTSTRAP_KEY', '')
    login_server = environ.pop('GRADIATED_TAILSCALE_LOGIN_SERVER', '')
    if login_server and not layout.test_control_server.exists():
        print('Ignoring GRADIATED_TAILSCALE_LOGIN_SERVER: this image joins only Tailscale.', flush=True)
        login_server = ''
    for name in SECRETS:
        environ.pop(name, None)
    if stop is None:
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())

    tailscale = Tailscale(layout)
    try:
        tailscale.join_as_bootstrap(environ.get('RUNPOD_POD_ID', ''), key, login_server)
    except ValueError as error:
        print(error, flush=True)
    del key
    if tailscale.config() is None:
        print('GPU enrollment requires GRADIATED_TAILSCALE_BOOTSTRAP_KEY from a RunPod secret.', flush=True)

    log = files.log(layout.logs / 'gradiated-tailscale.log')
    daemon = threading.Thread(target=keep_running, args=(lambda: tailscale.run(stop, log), stop, 'Tailscale'),
                              daemon=True)
    daemon.start()
    supervised = services(layout) if supervised is None else supervised
    while not stop.is_set():
        for service in supervised:
            try:
                service.ensure()
            except OSError as error:
                print(f'{service.name} could not start: {type(error).__name__}', flush=True)
        stop.wait(2)
    stop_all(supervised)
    daemon.join(timeout=15)
    log.close()
