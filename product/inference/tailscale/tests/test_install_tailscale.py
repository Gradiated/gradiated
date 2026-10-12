import importlib.util
import json
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
    def test_legacy_nomad_metadata_without_renewal_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "node.hcl"
            config.write_text(
                f'client {{\n meta {{\n gradiated_instance_id = "{INSTANCE}"\n }}\n}}\n'
            )
            self.assertEqual(
                installer.registered_instance_id(root / "identity.json", config),
                INSTANCE,
            )
            config.write_text(
                config.read_text() + f'gradiated_instance_id = "{INSTANCE}"\n'
            )
            with self.assertRaises(ValueError):
                installer.registered_instance_id(root / "identity.json", config)

    def test_renewal_identity_is_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = root / "identity.json"
            identity.write_text(json.dumps({"instance_id": INSTANCE}))
            self.assertEqual(
                installer.registered_instance_id(identity, root / "missing"), INSTANCE
            )
            identity.write_text(json.dumps({"instance_id": "invalid"}))
            with self.assertRaises(ValueError):
                installer.registered_instance_id(identity, root / "missing")
