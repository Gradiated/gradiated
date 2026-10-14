import importlib.util
import unittest
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "forward_control", Path(__file__).parents[1] / "control-listener.py"
)
forward = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forward)


class ControlEndpointTests(unittest.TestCase):
    def test_refuses_public_cluster_endpoints(self):
        for value in ["203.0.113.1", "127.0.0.1", "10.40.1.1", "::1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                forward.routes({name: value for name in forward.ENDPOINTS})

    def test_requires_the_complete_known_endpoint_set(self):
        self.assertEqual(forward.routes({"api": "100.64.0.1"}), [(("127.0.0.1", 3004), "100.64.0.1")])
        with self.assertRaises(ValueError):
            forward.routes({**{name: "100.64.0.1" for name in forward.ENDPOINTS}, "database": "100.64.0.2"})


class ConnectionUpdateTests(unittest.TestCase):
    def test_new_connections_use_current_helper_and_existing_connections_survive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for version in ('a', 'b'):
                (root / version).write_text("import sys\nfor line in sys.stdin:\n print(" + repr(version + ':') + " + line.strip(), flush=True)\n")
            pointer = root / 'current'
            pointer.symlink_to(root / 'a')
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1', 0))
                port = reserve.getsockname()[1]
            process = subprocess.Popen([sys.executable, '-c',
                "import importlib.util,pathlib,sys; s=importlib.util.spec_from_file_location('listener',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "m.ENDPOINTS={'api':('127.0.0.1',int(sys.argv[3]))}; "
                "m.control_program=lambda:pathlib.Path(sys.argv[2]).resolve(strict=True); m.serve({'api':'100.64.0.1'})",
                str(Path(__file__).parents[1] / 'control-listener.py'), str(pointer), str(port)])
            try:
                deadline = time.monotonic() + 5
                while True:
                    try:
                        old = socket.create_connection(('127.0.0.1', port), timeout=1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:raise
                        time.sleep(.02)
                with old:
                    old.sendall(b'first\n')
                    self.assertEqual(old.recv(64), b'a:first\n')
                    replacement = root / 'next'
                    replacement.symlink_to(root / 'b')
                    replacement.replace(pointer)
                    with socket.create_connection(('127.0.0.1', port), timeout=1) as new:
                        new.sendall(b'second\n')
                        self.assertEqual(new.recv(64), b'b:second\n')
                    old.sendall(b'still-open\n')
                    self.assertEqual(old.recv(64), b'a:still-open\n')
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_worker_rejects_public_address_or_unexpected_port(self):
        spec = importlib.util.spec_from_file_location('worker', Path(__file__).parents[1] / 'forward-control.py')
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        for address, port in [('203.0.113.1', 3004), ('100.64.0.1', 5432)]:
            with self.assertRaises(ValueError):worker.forward(address, port)
        with patch.object(worker.os, 'execv') as execute:
            worker.forward('100.64.0.1', 3004)
            self.assertEqual(execute.call_args.args[1][-2:], ['100.64.0.1', '3004'])
