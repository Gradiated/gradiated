import socket
import threading
import unittest

from support import executable, temporary_root

from gradiated_host import control

# Stands in for `tailscale nc`: echoes the connection and records its destination.
NC = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >>"$(dirname "$0")/calls"
exec cat
'''


class Endpoint(unittest.TestCase):
    def test_only_a_tailnet_api_address_is_accepted(self):
        self.assertEqual(control.target({'api': '100.64.0.1'}), '100.64.0.1')
        for config in ({'api': '203.0.113.1'}, {'api': '127.0.0.1'}, {'api': '10.40.1.1'}, {'api': 'fd7a::1'},
                       {'api': '100.64.0.1', 'database': '100.64.0.2'}, {}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                control.target(config)


class Bridge(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.cli = executable(self.layout.tailscale_bin / 'tailscale', NC)
        self.stop = threading.Event()
        ready = threading.Event()
        self.port = None

        def started(port):
            self.port = port
            ready.set()

        thread = threading.Thread(target=control.serve, kwargs={
            'config': {'api': '100.64.0.7'}, 'cli': self.cli, 'tailscale_socket': '/run/ts.sock',
            'address': ('127.0.0.1', 0), 'ready': started, 'stop': self.stop}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.stop.set)
        self.assertTrue(ready.wait(5))

    def test_forwards_bytes_unchanged_to_the_api_over_the_tailnet(self):
        payload = b'synthetic-control-bytes' * 5000
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as connection:
            connection.sendall(payload)
            connection.shutdown(socket.SHUT_WR)
            received = bytearray()
            while chunk := connection.recv(65536):
                received.extend(chunk)
        self.assertEqual(bytes(received), payload)
        self.assertEqual((self.cli.parent / 'calls').read_text(), '--socket=/run/ts.sock nc 100.64.0.7 3004\n')

    def test_listens_on_loopback_only(self):
        address = socket.gethostbyname(socket.gethostname())
        if address.startswith('127.'):
            self.skipTest('No non-loopback address to probe')
        with self.assertRaises(OSError):
            socket.create_connection((address, self.port), timeout=1)


if __name__ == '__main__':
    unittest.main()
