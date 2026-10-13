from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

IMAGE = 'python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea'


class HostInitTests(unittest.TestCase):
    def test_waits_for_enrollment_and_recovers_exit_and_container_restart(self):
        container = 'host-init-test-' + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'start-ssh.sh').write_text(Path(__file__).with_name('start-ssh.sh').read_text())
            (root / 'fixture.sh').write_text("""#!/bin/bash
set -euo pipefail
mkdir -p /usr/sbin /etc/gradiated /opt/gradiated/kubelet /run/sshd
printf '#!/bin/sh\nexit 0\n' >/usr/local/bin/ssh-keygen
chmod +x /usr/local/bin/ssh-keygen
cat >/usr/sbin/sshd <<'SSH'
#!/usr/local/bin/python3
import signal,time
signal.signal(signal.SIGTERM,lambda *_:exit(0))
while True:time.sleep(1)
SSH
chmod +x /usr/sbin/sshd
cat >/opt/gradiated/kubelet/bootstrap.py <<'HOST'
import pathlib,time,signal
p=pathlib.Path('/run/host-starts')
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
if n==1:raise SystemExit(1)
signal.signal(signal.SIGTERM,lambda *_:exit(0))
while True:time.sleep(1)
HOST
exec bash /tests/start-ssh.sh
""")
            def command(*args):
                return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.STDOUT)
            def starts():
                return int(command('exec', container, 'bash', '-c', 'cat /run/host-starts 2>/dev/null || echo 0').strip())
            def wait_for(count):
                deadline = time.monotonic() + 12
                while starts() < count:
                    if time.monotonic() > deadline:self.fail('Installed supervisor did not restart')
                    time.sleep(.1)
            try:
                command('run', '-d', '--name', container, '--cpus=1', '--memory=256m',
                        '-e', 'PUBLIC_KEY=ssh-ed25519 synthetic-init-key', '-v', str(root) + ':/tests:ro',
                        IMAGE, 'bash', '/tests/fixture.sh')
                time.sleep(2.5)
                self.assertEqual(starts(), 0)
                command('exec', container, 'bash', '-c', 'touch /etc/gradiated/kubelet.json /opt/gradiated/kubelet/launch-ready')
                wait_for(2)
                command('restart', '-t', '5', container)
                wait_for(3)
                self.assertEqual(command('exec', container, 'test', '-f', '/run/gradiated/host-init'), '')
            finally:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':unittest.main()
