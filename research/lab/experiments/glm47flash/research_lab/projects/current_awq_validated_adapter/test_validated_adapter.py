import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).with_name("validated_adapter.py")
spec = importlib.util.spec_from_file_location("validated_adapter", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ValidatedAdapterTests(unittest.TestCase):
    def test_rejects_multiline_pem(self):
        with self.assertRaises(RuntimeError):
            module.one_line_ssh_ed25519_bytes(b"-----BEGIN CERTIFICATE-----\na\n-----END CERTIFICATE-----\n")

    def test_preflight_reports_hashes_not_key_material(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            private = root / "private"
            public = root / "public"
            private.write_text("placeholder")
            public.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixture fixture@example\n")
            with patch.object(module, "derived_public_key", return_value=public.read_bytes().strip()):
                report = module.validate_adapter(private, public)
        rendered = json.dumps(report)
        self.assertTrue(report["private_key_derives_selected_public_key"])
        self.assertEqual(report["authorized_key_scalars"], 1)
        self.assertTrue(report["negative_multiline_pem_rejected"])
        self.assertNotIn("AAAAC3Nza", rendered)


if __name__ == "__main__":
    unittest.main()
