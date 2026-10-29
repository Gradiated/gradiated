"""Builds the GPU base Dockerfile and checks its entrypoint in a real container.

The CUDA parent image is replaced with Ubuntu 24.04. Most tests also replace the
Tailscale CLI, which would contact the control server; the entrypoint and the
real tailscaled run unchanged.
"""

from pathlib import Path
import subprocess
import time
import unittest
import uuid

from image_build import build_image

GPU_BASE = Path(__file__).resolve().parents[1]
CONTEXT = GPU_BASE.parents[1]
UBUNTU = 'ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac'
IMAGE = 'gradiated-gpu-base-entrypoint-test'
REAL_TAILSCALE_IMAGE = 'gradiated-gpu-base-entrypoint-test-real-tailscale'
SSH_LISTENERS = "awk '$4==\"0A\" && $2 ~ /:0016$/' /proc/net/tcp /proc/net/tcp6"
KEY = 'tskey-auth-synthetic'
# Prints the processes descended from the entrypoint whose arguments or environment hold a value.
DESCENDANT_LEAKS = """
import os, sys
needle = (sys.argv[1] + sys.argv[2]).encode()
parents, found = {}, []
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        parents[pid] = open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[1]
    except OSError:
        pass
command = lambda pid: open(f'/proc/{pid}/cmdline', 'rb').read()
# The Python entrypoint; tini's own arguments also name gradiated-host start.
roots = {pid for pid in parents if command(pid).startswith(b'/usr/bin/python3') and b'gradiated-host\\0start' in command(pid)}
for pid in parents:
    ancestor = parents.get(pid)
    while ancestor and ancestor not in roots:
        ancestor = parents.get(ancestor)
    if ancestor:
        for name in ('cmdline', 'environ'):
            try:
                if needle in open(f'/proc/{pid}/{name}', 'rb').read():
                    found.append(f'{pid}/{name}')
            except OSError:
                pass
print(' '.join(found))
"""


def docker(*args, **kwargs):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, timeout=900, **kwargs)
    if result.returncode:
        raise AssertionError(f'docker {args[0]} failed: {result.stderr[-3000:]}')
    return result.stdout


def build(tag, extra):
    dockerfile = (GPU_BASE / 'Dockerfile').read_text().splitlines()
    if not dockerfile[0].startswith('FROM nvidia/cuda:'):
        raise AssertionError('Unexpected GPU base parent image')
    # The CUDA parent ships CA certificates, which the HTTPS apt sources need.
    dockerfile[0:1] = [f'FROM {UBUNTU}', 'RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates']
    entrypoint = dockerfile.pop()
    build_image(tag, dockerfile + extra + [entrypoint], CONTEXT)


def setUpModule():
    build(REAL_TAILSCALE_IMAGE, [])
    build(IMAGE, ['COPY --chmod=755 images/gpu-base/tests/fake-tailscale /opt/gradiated/tailscale/tailscale'])


class EntrypointTests(unittest.TestCase):
    def start(self, *environment, image=IMAGE, network='none'):
        container = 'gpu-base-entrypoint-' + uuid.uuid4().hex
        self.addCleanup(subprocess.run, ['docker', 'rm', '-f', container],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        arguments = [value for item in environment for value in ('-e', item)]
        docker('run', '-d', '--platform', 'linux/amd64', '--network', network, '--name', container, *arguments, image)
        return container

    def shell(self, container, script):
        return docker('exec', container, 'bash', '-c', script)

    def wait(self, container, script, seconds=30):
        deadline = time.monotonic() + seconds
        while subprocess.run(['docker', 'exec', container, 'bash', '-c', script],
                             capture_output=True).returncode:
            if time.monotonic() > deadline:
                self.fail(f'Timed out waiting for: {script}\n{subprocess.run(["docker", "logs", container], capture_output=True, text=True).stdout}')
            time.sleep(.5)

    def processes(self, container, name):
        """Lists "UID PID arguments" for processes whose program name contains name."""
        return self.shell(container, f'''for p in /proc/[0-9]*; do
  program=$(tr '\\0' '\\n' <$p/cmdline 2>/dev/null | head -1) || continue
  case "$program" in *{name}*) echo "$(stat -c %u $p) ${{p#/proc/}} $(tr '\\0' ' ' <$p/cmdline)" ;; esac
done; true''').splitlines()

    def test_bootstrap_pod_runs_root_tailscale_ssh_and_no_public_ssh(self):
        # Retired settings for public SSH are present but have no effect.
        container = self.start('PUBLIC_KEY=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw== synthetic',
                               'GRADIATED_BREAK_GLASS_SSH=1', 'RUNPOD_POD_ID=abc123',
                               f'GRADIATED_TAILSCALE_BOOTSTRAP_KEY={KEY}')
        self.wait(container, 'grep -q " up " /var/log/fake-tailscale-calls')
        self.wait(container, 'test ! -e /var/lib/gradiated-tailscale/auth-key')
        calls = self.shell(container, 'cat /var/log/fake-tailscale-calls').splitlines()
        self.assertEqual(calls[0], '0 --socket=/var/lib/gradiated-tailscale/socket up --hostname=gpu-bootstrap-abc123 '
                         '--accept-dns=false --accept-routes=false --ssh --operator=tailscale --timeout=30s '
                         '--auth-key=file:/var/lib/gradiated-tailscale/auth-key')
        self.assertFalse(any(' serve ' in call for call in calls), 'A bootstrap pod must not serve inference')
        daemons = [line for line in self.processes(container, '/opt/gradiated/tailscale/tailscaled')
                   if '--tun=userspace-networking' in line]
        self.assertEqual(len(daemons), 1, daemons)
        self.assertTrue(daemons[0].startswith('0 '), 'tailscaled must run as root for Tailscale SSH')
        self.shell(container, 'test ! -e /usr/sbin/sshd && test ! -e /root/.ssh/authorized_keys')
        self.assertEqual(self.shell(container, SSH_LISTENERS), '')
        # The key never reaches the command line or environment of anything the entrypoint
        # starts. (The container's own processes keep the environment Docker gave them.)
        leaks = docker('exec', container, 'python3', '-c', DESCENDANT_LEAKS, KEY[:-3], KEY[-3:]).split()
        self.assertEqual(leaks, [])

        pid = daemons[0].split()[1]
        self.shell(container, f'kill -KILL {pid}')
        deadline = time.monotonic() + 30
        while not [line for line in self.processes(container, '/opt/gradiated/tailscale/tailscaled')
                   if '--tun=' in line and line.split()[1] != pid]:
            if time.monotonic() > deadline:
                self.fail('The supervisor did not restart tailscaled')
            time.sleep(.5)
        self.assertEqual(self.shell(container, SSH_LISTENERS), '')

    def test_a_pod_without_a_bootstrap_key_waits_for_one(self):
        container = self.start('RUNPOD_POD_ID=abc123')
        self.wait(container, 'pgrep -f "gradiated-host start" >/dev/null')
        time.sleep(3)
        self.assertEqual(self.processes(container, 'tailscaled'), [])
        self.shell(container, 'test ! -e /etc/gradiated/tailscale.json')
        self.assertIn('GPU enrollment requires GRADIATED_TAILSCALE_BOOTSTRAP_KEY',
                      subprocess.run(['docker', 'logs', container], capture_output=True, text=True).stdout)

    def test_real_tailscaled_creates_root_only_ssh_host_keys(self):
        # Without SSH host keys Tailscale SSH is advertised as disabled. The real CLI runs
        # `up` against the control server, which needs network access.
        container = self.start(image=REAL_TAILSCALE_IMAGE, network='bridge')
        self.shell(container, 'echo \'{"pod":"testpod"}\' >/etc/gradiated/tailscale.json')
        key = '/var/lib/gradiated-tailscale/ssh/ssh_host_ed25519_key'
        self.wait(container, f'test -f {key}', seconds=60)
        owner, permissions = self.shell(container, f'stat -c "%u %a" {key}').split()
        self.assertEqual(owner, '0')
        self.assertEqual(int(permissions, 8) & 0o077, 0, 'SSH host keys must be readable by root only')
        log = self.shell(container, 'cat /var/log/gradiated-tailscale.log')
        self.assertNotIn('unable to get SSH host keys', log)


if __name__ == '__main__':
    unittest.main()
