#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
import urllib.request

ROOT = Path('/var/lib/gradiated-kubelet/host')
BASE = Path('/opt/gradiated/kubelet')
CONFIG = Path('/etc/gradiated/kubelet.json')
BASE_ID = Path('/etc/gradiated/base-id')


def write(path, value):
    temporary = path.with_suffix('.new')
    with temporary.open('w') as output:
        json.dump(value, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    sync(path.parent)


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def select(root, name, digest):
    temporary = root / (name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(digest)
    temporary.replace(root / name)
    sync(root)


def verified(root, digest, base_id):
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        return False
    directory = root / digest
    try:
        if directory.is_symlink() or directory.stat().st_uid != os.geteuid() or directory.stat().st_mode & 0o022:
            return False
        if any(path.is_symlink() or path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o022
               for path in directory.iterdir()):
            return False
        if (directory / '.bundle-sha256').read_text().strip() != digest:
            return False
        if (directory / 'base-id').read_text().strip() != base_id:
            return False
        hashes = json.loads((directory / 'files.json').read_text())
        if set(hashes) != {'host-agent.py', 'host_state.py', 'host_bundle.py', 'desmondd', 'start-desmond', 'base-id'}:
            return False
        return all(not (directory / name).is_symlink() and
                   hashlib.sha256((directory / name).read_bytes()).hexdigest() == value
                   for name, value in hashes.items())
    except (OSError, ValueError, TypeError):
        return False


def linked(root, name, base_id):
    path = root / name
    if path.is_symlink():
        digest = os.readlink(path)
        if verified(root, digest, base_id):
            return digest
    return ''


class Launcher:
    def __init__(self, root=ROOT, base=BASE, base_id=None):
        self.root = root
        self.base = base / "recovery" if (base / "recovery").is_dir() else base
        self.base_id = base_id if base_id is not None else BASE_ID.read_text().strip()
        root.mkdir(parents=True, exist_ok=True)
        self.current = linked(root, 'current', self.base_id)
        self.previous = linked(root, 'previous', self.base_id)
        try:
            self.state = json.loads((root / 'status.json').read_text())
            if not isinstance(self.state, dict):
                self.state = {}
        except (OSError, ValueError):
            self.state = {}
        if not self.current:
            self.current = self.previous
            if self.current:
                select(root, 'current', self.current)
        self.trial = self.state.get('trial') == self.current and bool(self.current)
        self.deadline = time.monotonic() + 120
        self.exits = []
        self.publish()

    def publish(self):
        self.state.update({'current': self.current, 'previous': self.previous,
                           'trial': self.current if self.trial else ''})
        write(self.root / 'status.json', self.state)

    def update(self):
        pending = self.root / 'pending'
        if not pending.exists() or self.trial:
            return False
        try:
            digest = json.loads(pending.read_text())['sha256']
        except (OSError, ValueError, KeyError, TypeError):
            pending.unlink(missing_ok=True)
            sync(self.root)
            return False
        if digest == self.current or digest == self.state.get('failed'):
            pending.unlink()
            sync(self.root)
            return False
        if not verified(self.root, digest, self.base_id):
            self.state.update({'failed': digest, 'error': 'Host bundle verification failed'})
            pending.unlink()
            self.publish()
            return False
        self.previous = self.current
        self.current = digest
        self.trial = True
        self.deadline = time.monotonic() + 120
        self.exits = []
        # Persist the trial before switching so an interrupted update is health-gated again.
        self.publish()
        if self.previous:
            select(self.root, 'previous', self.previous)
        else:
            (self.root / 'previous').unlink(missing_ok=True)
        select(self.root, 'current', digest)
        pending.unlink()
        sync(self.root)
        return True

    def rollback(self, error):
        self.state.update({'failed': self.current, 'error': error})
        self.current = self.previous if verified(self.root, self.previous, self.base_id) else ''
        if self.current:
            select(self.root, 'current', self.current)
        else:
            (self.root / 'current').unlink(missing_ok=True)
        self.trial = False
        self.exits = []
        self.publish()

    def check(self, healthy, exited, now=None):
        now = time.monotonic() if now is None else now
        if exited:
            self.exits = [stamp for stamp in self.exits if now - stamp < 600] + [now]
        if self.current and (len(self.exits) >= 3 or (self.trial and now >= self.deadline)):
            self.rollback('Agent health gate failed')
            return True
        if self.trial and healthy:
            self.trial = False
            self.publish()
        return False

    def cleanup(self):
        protected = {self.current, self.previous}
        # Live task/proxy workers retain their original code across agent updates.
        for command in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                for argument in command.read_bytes().split(b'\0'):
                    path = Path(os.fsdecode(argument))
                    if path.parent.parent == self.root:
                        protected.add(path.parent.name)
            except (OSError, ValueError):
                pass
        unused = sorted((path for path in self.root.iterdir() if path.name not in protected
                         and verified(self.root, path.name, self.base_id)),
                        key=lambda path: path.stat().st_mtime, reverse=True)
        for path in unused[1:]:
            shutil.rmtree(path)


def ping(digest):
    try:
        config = json.loads(CONFIG.read_text())
        token = Path(config['token_file']).read_text().strip()
        request = urllib.request.Request('http://127.0.0.1:8887/_kubelet',
            data=b'{"operation":"ping"}', headers={'Authorization': 'Bearer ' + token,
                                                   'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.load(response)
        return result.get('host_bundle_sha256') == digest and result.get('instance_id') == config['instance_id']
    except (OSError, ValueError, KeyError):
        return False


def main():
    stopping, reload = threading.Event(), threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGHUP, lambda *_: reload.set())
    launcher = Launcher()
    pid = os.getpid()
    birth = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    write(ROOT.parent / "launcher.json", {"pid": pid, "birth": birth})
    while not stopping.is_set():
        directory = launcher.root / launcher.current if launcher.current else launcher.base
        process = subprocess.Popen(['python3', str(directory / 'host-agent.py')])
        while not stopping.wait(1):
            exited = process.poll() is not None
            if launcher.check(not exited and ping(launcher.current), exited):
                break
            if reload.is_set() or launcher.update() or exited:
                break
        reload.clear()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        launcher.cleanup()
        stopping.wait(2)


if __name__ == '__main__':
    main()
