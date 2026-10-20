"""Builds the GPU base Dockerfile and checks its entrypoint in a real container.

Only the CUDA parent image (Ubuntu 24.04 is used instead) and the Tailscale CLI,
which would contact the control server, are replaced. The entrypoint, Tailscale
supervisor scripts, real tailscaled and real OpenSSH run unchanged.
"""

from pathlib import Path
import subprocess
import time
import unittest
import uuid

GPU_BASE = Path(__file__).resolve().parents[1]
CONTEXT = GPU_BASE.parents[1]
UBUNTU = 'ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac'
IMAGE = 'gradiated-gpu-base-entrypoint-test'
SSH_LISTENERS = "awk '$4==\"0A\" && $2 ~ /:0016$/' /proc/net/tcp /proc/net/tcp6"


def docker(*args, **kwargs):
    result = subprocess.run(['docker', *args], text=True, capture_output=True, timeout=900, **kwargs)
    if result.returncode:
        raise AssertionError(f'docker {args[0]} failed: {result.stderr[-3000:]}')
    return result.stdout


def setUpModule():
    dockerfile = (GPU_BASE / 'Dockerfile').read_text().splitlines()
    if not dockerfile[0].startswith('FROM nvidia/cuda:'):
        raise AssertionError('Unexpected GPU base parent image')
    # The CUDA parent ships CA certificates, which the HTTPS apt sources need.
    dockerfile[0:1] = [f'FROM {UBUNTU}', 'RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates']
    dockerfile.append('COPY --chmod=755 images/gpu-base/tests/fake-tailscale /opt/gradiated/tailscale/tailscale')
    docker('build', '-q', '--platform', 'linux/amd64', '-t', IMAGE, '-f', '-', str(CONTEXT), input='\n'.join(dockerfile) + '\n')


class EntrypointTests(unittest.TestCase):
    def start(self, *environment):
        container = 'gpu-base-entrypoint-' + uuid.uuid4().hex
        self.addCleanup(subprocess.run, ['docker', 'rm', '-f', container],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        arguments = [value for item in environment for value in ('-e', item)]
        docker('run', '-d', '--platform', 'linux/amd64', '--name', container, *arguments, IMAGE)
        return container

    def shell(self, container, script):
        return docker('exec', container, 'bash', '-c', script)

    def wait(self, container, script, seconds=30):
        deadline = time.monotonic() + seconds
        while subprocess.run(['docker', 'exec', container, 'bash', '-c', script],
                             capture_output=True).returncode:
            if time.monotonic() > deadline:
                self.fail(f'Timed out waiting for: {script}')
            time.sleep(.5)

    def processes(self, container, name):
        """Lists "UID PID arguments" for processes whose program name contains name."""
        return self.shell(container, f'''for p in /proc/[0-9]*; do
  program=$(tr '\\0' '\\n' <$p/cmdline 2>/dev/null | head -1) || continue
  case "$program" in *{name}*) echo "$(stat -c %u $p) ${{p#/proc/}} $(tr '\\0' ' ' <$p/cmdline)" ;; esac
done; true''').splitlines()

    def test_bootstrap_pod_runs_root_tailscale_ssh_and_no_public_ssh(self):
        container = self.start('PUBLIC_KEY=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw== synthetic',
                               'RUNPOD_POD_ID=abc123', 'GRADIATED_TAILSCALE_BOOTSTRAP_KEY=tskey-auth-synthetic')
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
        self.assertEqual(self.processes(container, 'sshd'), [])
        self.assertEqual(self.shell(container, SSH_LISTENERS), '')
        self.shell(container, 'test ! -e /root/.ssh/authorized_keys')
        self.assertNotIn('tskey-auth', ''.join(self.processes(container, 'tailscale')))

        pid = daemons[0].split()[1]
        self.shell(container, f'kill -KILL {pid}')
        deadline = time.monotonic() + 30
        while not [line for line in self.processes(container, '/opt/gradiated/tailscale/tailscaled')
                   if '--tun=' in line and line.split()[1] != pid]:
            if time.monotonic() > deadline:
                self.fail('The supervisor did not restart tailscaled')
            time.sleep(.5)
        self.assertEqual(self.shell(container, SSH_LISTENERS), '')

    def test_break_glass_starts_openssh_with_the_public_key(self):
        container = self.start('GRADIATED_BREAK_GLASS_SSH=1', 'PUBLIC_KEY=placeholder')
        self.shell(container, '''ssh-keygen -q -t ed25519 -N "" -f /tmp/key
cp /tmp/key.pub /root/.ssh/authorized_keys''')
        self.wait(container, f'{SSH_LISTENERS} | grep -q .')
        self.assertEqual(self.shell(container, 'ssh -i /tmp/key -o BatchMode=yes -o StrictHostKeyChecking=no '
                                               'root@127.0.0.1 echo reached').strip(), 'reached')
        self.shell(container, 'test ! -e /etc/gradiated/tailscale.json')

    def test_public_key_alone_does_not_start_openssh(self):
        container = self.start('PUBLIC_KEY=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw== synthetic')
        self.wait(container, 'test -e /run/gradiated/host-init')
        time.sleep(3)
        self.assertEqual(self.processes(container, 'sshd'), [])
        self.assertEqual(self.shell(container, SSH_LISTENERS), '')


if __name__ == '__main__':
    unittest.main()
