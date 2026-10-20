import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).parents[1] / "install-tailscale.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
INSTANCE = "00000000-0000-4000-8000-000000000001"


class RegisteredIdentityTests(unittest.TestCase):

    def test_renewal_identity_is_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root / "identity.json"
            identity.write_text(json.dumps({"instance_id": INSTANCE}))
            self.assertEqual(
                installer.registered_instance_id(identity), INSTANCE
            )
            identity.write_text(json.dumps({"instance_id": "invalid"}))
            with self.assertRaises(ValueError):
                installer.registered_instance_id(identity)


class PromotionTests(unittest.TestCase):
    def test_finds_only_the_tailscale_supervisor_owned_by_the_given_uid(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            for pid, args in [(10, b"bash\0/opt/gradiated/bin/run-tailscale\0"),
                              (11, b"bash\0/opt/gradiated/bin/run-control\0"),
                              (12, b"python3\0/opt/gradiated/bin/run-tailscale\0")]:
                (proc / str(pid)).mkdir()
                (proc / str(pid) / "cmdline").write_bytes(args)
            self.assertEqual(installer.supervisors(proc, os.getuid()), [10])
            self.assertEqual(installer.supervisors(proc, os.getuid() + 1), [])
