"""`gradctl env build`: which secrets feed .env and which values win."""

import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _path  # noqa: F401
from gradctl import envfile

SECRETS = {
    envfile.SECRET_ID: {"SHARED_KEY": "dev", "DEV_ONLY": "d"},
    envfile.FDE_SECRET_ID: {"SHARED_KEY": "fde", "FDE_ONLY": "f"},
}


class EnvBuild(unittest.TestCase):
    def build(self, with_fde, existing=""):
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo)
        if existing:
            (repo / ".env").write_text(existing)
        ctx = SimpleNamespace(args=SimpleNamespace(profile="test", with_fde=with_fde), repo=lambda: repo)
        with mock.patch.object(envfile.shutil, "which", return_value="/usr/bin/aws"), \
                mock.patch.object(envfile, "read_secret", side_effect=lambda profile, secret_id=envfile.SECRET_ID: dict(SECRETS[secret_id])):
            result = envfile.build(ctx)
        return result, (repo / ".env")

    def test_default_reads_only_the_dev_secret(self):
        result, path = self.build(with_fde=False)
        text = path.read_text()
        self.assertIn("SHARED_KEY='dev'", text)
        self.assertNotIn("FDE_ONLY", text)
        self.assertEqual(result.data["sources"], [envfile.SECRET_ID])
        self.assertEqual(result.data["fde_overrides"], [])
        self.assertIn("`gradctl env build`; rerun it", text)

    def test_with_fde_adds_its_keys_and_its_values_win(self):
        result, path = self.build(with_fde=True, existing="LOCAL_ONLY=1\n")
        text = path.read_text()
        self.assertIn("SHARED_KEY='fde'", text)
        self.assertIn("FDE_ONLY='f'", text)
        self.assertIn("DEV_ONLY='d'", text)
        self.assertIn("LOCAL_ONLY=1", text)
        self.assertEqual(result.data["fde_overrides"], ["SHARED_KEY"])
        # The refresh command in the header keeps the FDE keys on rerun.
        self.assertIn("`gradctl env build --with-fde`; rerun it", text)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        # Names only, never values.
        self.assertNotIn("'fde'", result.text)


if __name__ == "__main__":
    unittest.main()
