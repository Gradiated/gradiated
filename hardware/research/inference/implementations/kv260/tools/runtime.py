"""Pinned, offline macOS runtime. Selected weights and source are read-only."""
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
RUNTIME = next(p for p in PROJECT.parents if (p / "product").is_dir() and (p / ".git").exists()) / '.agents/runtime/hardware/inference'
MODEL = PROJECT / 'model'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def clean_environment(runtime, source):
    permitted = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TERM')
    env = {key: source[key] for key in permitted if key in source}
    env.update(PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(runtime / 'tmp'), MLX_ENABLE_TF32='0')
    return env


def verify_environment(project=PROJECT, runtime=RUNTIME):
    import tomllib
    normalize = lambda name: name.lower().replace('_', '-').replace('.', '-')
    locked = {normalize(p['name']): p['version']
              for p in tomllib.loads((project / 'uv.lock').read_text())['package'] if 'registry' in p['source']}
    installed = {}
    for directory in (runtime / 'venv/lib/python3.12/site-packages').glob('*.dist-info'):
        data = Parser().parsestr((directory / 'METADATA').read_text())
        installed[normalize(data['Name'])] = data['Version']
    if not {'mlx', 'mlx-lm', 'numpy', 'transformers'} <= installed.keys() or any(locked.get(n) != v for n, v in installed.items()):
        raise ValueError('Installed environment differs from uv.lock; refusing to run.')


def launch_arguments(arguments, project=PROJECT, runtime=RUNTIME):
    if not Path('/usr/bin/sandbox-exec').is_file():
        raise RuntimeError('macOS sandbox-exec required; refusing unrestricted execution.')
    locations = {'TINY_TMP': runtime / 'tmp', 'TINY_CACHE': runtime / 'cache', 'TINY_OUTPUTS': runtime / 'outputs'}
    profile = '(version 1)(allow default)(deny network*)(deny file-write*)'
    profile += '(allow file-write* (literal "/dev/null")' + ''.join(f' (subpath (param "{n}"))' for n in locations) + ')'
    command = ['/usr/bin/sandbox-exec']
    for name, path in locations.items():
        command += ['-D', f'{name}={path}']
    return [*command, '-p', profile, str(runtime / 'venv/bin/python'), '-I', '-B',
            str(project / 'tools/generative.py'), *arguments]


def supervise(arguments, timeout_seconds):
    """One absolute wall timeout covers the worker; always reap it."""
    verify_environment()
    for name in ('tmp', 'cache', 'outputs'):
        (RUNTIME / name).mkdir(parents=True, exist_ok=True)
    folder = RUNTIME / 'outputs/tiny' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    folder.mkdir(parents=True, exist_ok=False)
    receipt = {'started_at': now(), 'timeout_seconds': timeout_seconds}
    command = launch_arguments([*arguments, '--inside', '--output', str(folder)])
    started = time.monotonic()
    child = subprocess.Popen(command, start_new_session=True, env=clean_environment(RUNTIME, os.environ))
    receipt['pid'] = child.pid
    try:
        receipt['exit_code'] = child.wait(timeout=timeout_seconds)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(child.pid, signal.SIGKILL)
        receipt['exit_code'] = child.wait()
        receipt['watchdog_stopped'] = True
    finally:
        # Reap owned compiler/simulator descendants even when the worker errors.
        try:os.killpg(child.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        child.wait()
        try:
            os.killpg(child.pid,0)
            receipt['process_group_absent'] = False
        except ProcessLookupError:
            receipt['process_group_absent'] = True
        receipt.update(completed_at=now(), elapsed_seconds=time.monotonic()-started, child_reaped=child.poll() is not None)
        try:
            os.kill(child.pid, 0)
            receipt['child_absent'] = False
        except ProcessLookupError:
            receipt['child_absent'] = True
        save(folder / 'watchdog.json', receipt)
    return receipt['exit_code']
