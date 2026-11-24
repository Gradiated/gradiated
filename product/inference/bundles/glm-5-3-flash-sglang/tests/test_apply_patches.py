import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "apply_patches", BUNDLE / "apply-patches.py"
)
apply_patches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_patches)

ADDED = "print('added')\n"
PATCH = "--- /dev/null\n+++ b/pkg/added.py\n@@ -0,0 +1 @@\n+print('added')\n"


class ApplyPatchesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.site = Path(temp.name) / "site"
        self.bundle = Path(temp.name) / "bundle"
        (self.site / "pkg").mkdir(parents=True)
        (self.bundle / "patches").mkdir(parents=True)
        (self.bundle / "patches/added.patch").write_text(PATCH)
        (self.bundle / "patches.json").write_text(
            json.dumps(
                {
                    "upstream_sha": apply_patches.REVISIONS["patches.json"],
                    "files": [
                        {
                            "path": "pkg/added.py",
                            "original_sha256": None,
                            "overlay_sha256": hashlib.sha256(
                                ADDED.encode()
                            ).hexdigest(),
                            "patch": "added.patch",
                        }
                    ],
                }
            )
        )

    def test_null_original_adds_a_new_file(self):
        apply_patches.apply(self.site, self.bundle)

        self.assertEqual((self.site / "pkg/added.py").read_text(), ADDED)

    def test_null_original_rejects_an_existing_file(self):
        (self.site / "pkg/added.py").write_text("upstream\n")

        with self.assertRaisesRegex(ValueError, "already exists"):
            apply_patches.apply(self.site, self.bundle)

    def test_every_cartridge_patch_is_registered_once(self):
        manifest = json.loads((BUNDLE / "patches.json").read_text())
        patches = {path.name for path in (BUNDLE / "patches").glob("cartridge_*.patch")}
        registered = [item["patch"] for item in manifest["files"]]

        self.assertEqual(patches, {name for name in registered if name in patches})
        self.assertEqual(len(registered), len(set(registered)))


if __name__ == "__main__":
    unittest.main()
