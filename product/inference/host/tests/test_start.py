import os
import threading
import time
import unittest

from support import executable, temporary_root
from test_tailscale import CLI, DAEMON

from gradiated_host import start
from gradiated_host.start import Service, stop_all


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill 0; on Linux its state is Z.
    try:
        return open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return True


class Services(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.log = open(self.layout.logs / 'service.log', 'ab')
        self.addCleanup(self.log.close)
        self.wanted = False
        self.service = Service('sleeper', ['sleep', '30'], lambda: self.wanted, self.log)
        self.addCleanup(stop_all, [self.service])

    def test_starts_only_once_wanted(self):
        self.service.ensure()
        self.assertIsNone(self.service.process)
        self.wanted = True
        self.service.ensure()
        first = self.service.process
        self.assertIsNone(first.poll())
        self.service.ensure()
        self.assertIs(self.service.process, first)

    def test_restarts_a_process_that_exited(self):
        self.wanted = True
        self.service.ensure()
        first = self.service.process
        first.kill()
        first.wait()
        self.service.ensure()
        self.assertIsNot(self.service.process, first)
        self.assertIsNone(self.service.process.poll())

    def test_stopping_signals_every_service_before_waiting(self):
        # Each ignores SIGTERM for a second; stopped one at a time they would take two.
        script = 'trap "sleep 1; exit 0" TERM; while :; do sleep .1; done'
        services = [Service(f'slow {n}', ['bash', '-c', script], lambda: True, self.log) for n in range(2)]
        for service in services:
            service.ensure()
        time.sleep(.3)
        started = time.monotonic()
        stop_all(services)
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertTrue(all(service.process.poll() is not None for service in services))


class Entrypoint(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        executable(self.layout.tailscale_bin / 'tailscaled', DAEMON)
        executable(self.layout.tailscale_bin / 'tailscale', CLI)
        self.log = open(self.layout.logs / 'service.log', 'ab')
        self.addCleanup(self.log.close)

    def daemons(self):
        path = self.layout.tailscale_bin / 'daemons'
        return [int(pid) for pid in path.read_text().split()] if path.exists() else []

    def test_joins_as_bootstrap_supervises_and_stops_everything(self):
        environ = {'RUNPOD_POD_ID': 'abc123', 'GRADIATED_TAILSCALE_BOOTSTRAP_KEY': 'tskey-auth-bootstrap',
                   'PUBLIC_KEY': 'ssh-ed25519 AAAA', 'GRADIATED_BREAK_GLASS_SSH': '1'}
        stop = threading.Event()
        sleeper = Service('sleeper', ['sleep', '30'], lambda: True, self.log)
        thread = threading.Thread(target=start.main, args=(self.layout, environ, stop, [sleeper]), daemon=True)
        thread.start()
        self.addCleanup(stop.set)
        deadline = time.monotonic() + 15
        while not (self.daemons() and sleeper.process and not self.layout.tailscale_state.joinpath('auth-key').exists()):
            if time.monotonic() > deadline:
                self.fail('The entrypoint did not start Tailscale and its services')
            time.sleep(.05)
        self.assertEqual(environ, {'RUNPOD_POD_ID': 'abc123'})
        # Production sets no login server, so the pod uses Tailscale's.
        tailscale = start.Tailscale(self.layout)
        self.assertEqual(tailscale.config(), {'pod': 'abc123'})
        self.assertFalse(any(argument.startswith('--login-server') for argument in tailscale.up_arguments('x', key=True)))
        daemon, service = self.daemons()[0], sleeper.process.pid

        stop.set()
        thread.join(30)
        self.assertFalse(thread.is_alive())
        self.assertFalse(alive(service))
        deadline = time.monotonic() + 5
        while alive(daemon) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertFalse(alive(daemon), 'tailscaled must stop with the entrypoint')

    def record(self, environ):
        stop = threading.Event()
        thread = threading.Thread(target=start.main, args=(self.layout, environ, stop, []), daemon=True)
        thread.start()
        self.addCleanup(stop.set)
        deadline = time.monotonic() + 15
        while start.Tailscale(self.layout).config() is None:
            if time.monotonic() > deadline:
                self.fail('The entrypoint did not record the bootstrap identity')
            time.sleep(.05)
        stop.set()
        thread.join(30)
        return start.Tailscale(self.layout).config()

    def test_an_ec2_host_joins_under_its_provider_instance_id(self):
        # The AWS host launcher passes the EC2 instance ID; it wins over a RunPod pod ID.
        environ = {'GRADIATED_PROVIDER_INSTANCE_ID': 'i-0123456789abcdef0',
                   'GRADIATED_TAILSCALE_BOOTSTRAP_KEY': 'tskey-auth-bootstrap'}
        self.assertEqual(self.record(environ), {'pod': 'i-0123456789abcdef0'})
        self.assertEqual(environ, {'GRADIATED_PROVIDER_INSTANCE_ID': 'i-0123456789abcdef0'})
        self.assertEqual(start.provider_instance_id({'GRADIATED_PROVIDER_INSTANCE_ID': 'i-0123456789abcdef0',
                                                     'RUNPOD_POD_ID': 'abc123'}), 'i-0123456789abcdef0')
        self.assertEqual(start.provider_instance_id({'GRADIATED_PROVIDER_INSTANCE_ID': '',
                                                     'RUNPOD_POD_ID': 'abc123'}), 'abc123')
        self.assertEqual(start.provider_instance_id({}), '')

    def test_a_production_image_ignores_a_login_server_in_its_environment(self):
        environ = {'RUNPOD_POD_ID': 'abc123', 'GRADIATED_TAILSCALE_BOOTSTRAP_KEY': 'tskey-auth-bootstrap',
                   'GRADIATED_TAILSCALE_LOGIN_SERVER': 'https://attacker.example'}
        self.assertEqual(self.record(environ), {'pod': 'abc123'})
        self.assertEqual(environ, {'RUNPOD_POD_ID': 'abc123'})

    def test_a_test_control_server_is_recorded_and_not_passed_to_children(self):
        self.layout.test_control_server.write_text('')
        environ = {'RUNPOD_POD_ID': 'abc123', 'GRADIATED_TAILSCALE_BOOTSTRAP_KEY': 'hskey-auth-bootstrap_1',
                   'GRADIATED_TAILSCALE_LOGIN_SERVER': 'https://headscale'}
        stop = threading.Event()
        thread = threading.Thread(target=start.main, args=(self.layout, environ, stop, []), daemon=True)
        thread.start()
        self.addCleanup(stop.set)
        deadline = time.monotonic() + 15
        while start.Tailscale(self.layout).config() is None:
            if time.monotonic() > deadline:
                self.fail('The entrypoint did not record the bootstrap identity')
            time.sleep(.05)
        self.assertEqual(start.Tailscale(self.layout).config(), {'pod': 'abc123', 'login_server': 'https://headscale'})
        self.assertEqual(environ, {'RUNPOD_POD_ID': 'abc123'})
        stop.set()
        thread.join(30)

    def test_waits_for_a_bootstrap_key_without_starting_tailscale(self):
        stop = threading.Event()
        thread = threading.Thread(target=start.main, args=(self.layout, {'RUNPOD_POD_ID': 'abc123'}, stop, []),
                                  daemon=True)
        thread.start()
        time.sleep(1)
        stop.set()
        thread.join(10)
        self.assertEqual(self.daemons(), [])
        self.assertIsNone(start.Tailscale(self.layout).config())


if __name__ == '__main__':
    unittest.main()
