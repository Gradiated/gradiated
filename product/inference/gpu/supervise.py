#!/usr/bin/env python3
import fcntl
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
FILES = {'host-agent.py', 'desmondd', 'base-id'}


def read(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(path, value):
    temporary = path.with_suffix('.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        sync(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
        if (directory / '.bundle-sha256').read_text().strip() != digest or (directory / 'base-id').read_text().strip() != base_id:
            return False
        hashes = read(directory / 'files.json')
        if (not FILES.issubset(hashes) or len(hashes) > 64 or
                {path.name for path in directory.iterdir()} != set(hashes) | {'files.json', '.bundle-sha256'} or
                any(not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name) or
                    not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
                    for name, value in hashes.items())):
            return False
        return all(hashlib.sha256((directory / name).read_bytes()).hexdigest() == value
                   for name, value in hashes.items())
    except (OSError, ValueError, TypeError):
        return False


class Launcher:
    def __init__(self, root=ROOT, base=BASE, base_id=None):
        self.root, self.base = root, base
        try:
            self.base_id = base_id if base_id is not None else BASE_ID.read_text().strip()
        except OSError:
            self.base_id = ''
        self.state = read(root / 'status.json')
        if self.state.get('schema') != 2:
            # Migrate selections written by the symlink-based launcher once.
            for name in ('current', 'previous'):
                path = root / name
                try:
                    self.state[name] = os.readlink(path) if path.is_symlink() else self.state.get(name, '')
                except OSError:
                    self.state[name] = ''
        try:
            birth = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError:
            birth = ''
        self.state.update({'schema': 2, 'launcher_pid': os.getpid(), 'launcher_birth': birth})
        for name in ('current', 'previous', 'trial', 'failed', 'running'):
            if not isinstance(self.state.get(name), str):
                self.state[name] = ''
        self.exits = []
        self.deadline = time.monotonic() + 120
        current = self.state.get('current', '')
        if self.state['trial'] or self.state['running'] or (current and not verified(root, current, self.base_id)):
            # An interrupted trial is rejected before executing it again.
            self.rollback('Unclean launcher exit, interrupted trial or invalid host bundle')
        else:
            self.state['current'] = current
            self.state['running'] = current
            self.publish()

    @property
    def current(self):
        return self.state['current']

    @property
    def previous(self):
        return self.state['previous']

    @property
    def trial(self):
        return bool(self.state['trial'])

    def directory(self):
        if self.current and not self.dirty:
            return self.root / self.current
        recovery = self.base / 'recovery'
        return recovery if recovery.is_dir() else self.base

    def publish(self):
        self.dirty = True
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            write(self.root / 'status.json', self.state)
            self.dirty = False
            return True
        except OSError as error:
            print(f'Launcher state unavailable: {type(error).__name__}', flush=True)
            return False

    def update(self):
        fd = os.open(self.root.parent / 'config.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self.update_locked()

    def update_locked(self):
        if self.dirty and not self.publish():
            return False
        pending = self.root / 'pending'
        if not pending.exists() or self.trial:
            return False
        request = read(pending)
        digest = request.get('sha256')
        if 'epoch' in request and request['epoch'] != read(self.root.parent / 'fence.json').get('epoch'):
            pending.unlink(missing_ok=True)
            return False
        if digest == self.current or digest == self.state.get('failed'):
            pending.unlink(missing_ok=True)
            return False
        if not verified(self.root, digest, self.base_id):
            self.state.update({'failed': digest, 'error': 'Host bundle verification failed'})
            if self.publish():
                pending.unlink(missing_ok=True)
            return False
        candidate = {**self.state, 'previous': self.current, 'current': digest, 'trial': digest, 'running': digest}
        # A new bundle runs only after its rollback decision is durable.
        write(self.root / 'status.json', candidate)
        self.state = candidate
        self.deadline = time.monotonic() + 120
        self.exits = []
        try:
            pending.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def rollback(self, error):
        previous = self.previous
        self.state.update({'failed': self.state.get('current', ''), 'error': error,
                           'current': previous if verified(self.root, previous, self.base_id) else '',
                           'previous': '', 'trial': ''})
        self.state['running'] = self.current
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
            self.state['trial'] = ''
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
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def main():
    os.umask(0o022)
    stopping, reload = threading.Event(), threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.signal(signal.SIGHUP, lambda *_: reload.set())
    launcher = Launcher()
    while not stopping.is_set():
        running_digest = launcher.current if not launcher.dirty else ''
        try:
            process = subprocess.Popen(['/usr/bin/setpriv', '--pdeathsig=TERM', 'python3', str(launcher.directory() / 'host-agent.py')])
        except OSError as error:
            print(f'Agent start unavailable: {type(error).__name__}', flush=True)
            stopping.wait(2)
            continue
        while not stopping.wait(1):
            exited = process.poll() is not None
            try:
                restart = (launcher.check(not exited and ping(launcher.current), exited) or launcher.update() or
                           (running_digest != launcher.current and not launcher.dirty))
            except OSError as error:
                print(f'Launcher update unavailable: {type(error).__name__}', flush=True)
                restart = False
            if reload.is_set() or restart or exited:
                break
        reload.clear()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        try:
            launcher.cleanup()
        except OSError as error:
            print(f'Launcher cleanup unavailable: {type(error).__name__}', flush=True)
        stopping.wait(2)
    launcher.state['running'] = ''
    launcher.publish()


if __name__ == '__main__':
    main()
