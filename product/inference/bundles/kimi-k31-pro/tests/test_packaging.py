import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('overlay', ROOT / 'apply-kimi-patches.py')
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)
PATCHES = Path(os.environ['KIMI_PATCH_DIRECTORY'])
SOURCE = Path(os.environ['KIMI_ORIGINAL_SOURCE'])
PINS = json.loads((ROOT / 'manifest-pins.json').read_text())


class Packaging(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        site, patches = root / 'site', root / 'patches'
        shutil.copytree(PATCHES, patches)
        for name in overlay.ORDER:
            manifest = json.loads((patches / name).read_text())
            paths = {item['path'] for item in manifest['files']} | set(manifest.get('oracle_sources', {}))
            for relative in paths - {overlay.NEW_FILE}:
                target = site / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((SOURCE / relative).read_bytes())
        return site, patches

    def test_profiles_and_output_tamper(self):
        for profile in overlay.PROFILES:
            with self.subTest(profile=profile):
                site, patches = self.fixture()
                identity = overlay.apply(site, patches, profile, PINS)
                overlay.verify(site, identity['fingerprint'])
                path = site / next(iter(identity['files']))
                path.write_bytes(path.read_bytes() + b'\n')
                with self.assertRaises(ValueError):
                    overlay.verify(site, identity['fingerprint'])

    def test_five_incumbent_profiles_keep_exact_fingerprints(self):
        expected = {
            'correctness': 'ec72a95440d2e6122d0b2ce31fbdccd2d23ad4a422561cee863ef4b66ac10e18',
            'baseline-seeded': '625f52c71b7ed70fedce00c07107eea3b5537f5368980edac2dda668c61f3b62',
            'dflash-seeded': '9265dbd54de1fb2a57f00c18ae82ba50282efa890ea20014ed0cccfca628487b',
            'dflash-experiment-admitted': 'a3d9cf9d86ee6d11cc126237d6f3cad8389ebff7f7e935db7a4a88ae9e9dfc4a',
            'dflash-admitted-cache-accounting': 'd6c38e3e664102833122799a245830fa254376fb5f4896110d256c64706a77a4',
        }
        for profile, fingerprint in expected.items():
            with self.subTest(profile=profile):
                site, patches = self.fixture()
                identity = overlay.apply(site, patches, profile, PINS)
                self.assertEqual(identity['fingerprint'], fingerprint)
                self.assertNotIn('fused-philox-manifest.json', identity['manifests'])

    def test_fused_profile_changes_only_the_qualified_helper(self):
        site, patches = self.fixture()
        incumbent = overlay.apply(site, patches, 'dflash-admitted-cache-accounting', PINS)
        site, patches = self.fixture()
        fused = overlay.apply(site, patches, 'dflash-admitted-cache-accounting-fused-philox', PINS)
        self.assertEqual(set(incumbent['files']), set(fused['files']))
        self.assertEqual(len(fused['files']), 8)
        changed = [path for path in fused['files'] if incumbent['files'][path] != fused['files'][path]]
        self.assertEqual(changed, [overlay.NEW_FILE])
        self.assertEqual(fused['files'][overlay.NEW_FILE], '902384372b6a59676c425f5faf4ea427878bb04c408d249efc0263e2daa0d802')
        self.assertEqual(fused['fingerprint'], '6509efad47e02e681caa9cdb49bb9b9375fb94aa30276fcfa5a082e9bfcdab3e')
        marker = json.loads((site / overlay.MARKER).read_text())
        self.assertEqual(marker, fused)
        overlay.verify(site, fused['fingerprint'])
        helper = site / overlay.NEW_FILE
        helper.write_bytes(helper.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            overlay.verify(site, fused['fingerprint'])

    def test_fused_layer_tamper_never_publishes_prior_layers(self):
        for mutation in ('patch', 'input-hash'):
            with self.subTest(mutation=mutation):
                site, patches = self.fixture()
                before = {str(path.relative_to(site)): path.read_bytes() for path in site.rglob('*') if path.is_file()}
                pins = dict(PINS)
                manifest_path = patches / 'fused-philox-manifest.json'
                if mutation == 'patch':
                    patch = patches / 'dflash-fused-philox.patch'
                    patch.write_bytes(patch.read_bytes() + b'\n')
                else:
                    manifest = json.loads(manifest_path.read_text())
                    manifest['files'][0]['original_sha256'] = '0' * 64
                    manifest_path.write_text(json.dumps(manifest))
                    pins[manifest_path.name] = overlay.digest(manifest_path.read_bytes())
                with self.assertRaises(ValueError):
                    overlay.apply(site, patches, 'dflash-admitted-cache-accounting-fused-philox', pins)
                after = {str(path.relative_to(site)): path.read_bytes() for path in site.rglob('*') if path.is_file()}
                self.assertEqual(before, after)
                self.assertFalse((site / overlay.NEW_FILE).exists())
                self.assertFalse((site / overlay.MARKER).exists())

    def test_late_lineage_mismatch_does_not_publish_early_layer(self):
        site, patches = self.fixture()
        early = site / 'sglang/srt/speculative/dflash_utils.py'
        original = early.read_bytes()
        late = site / 'sglang/srt/layers/sampler.py'
        late.write_bytes(late.read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            overlay.apply(site, patches, 'dflash-seeded', PINS)
        self.assertEqual(early.read_bytes(), original)
        self.assertFalse((site / overlay.MARKER).exists())

    def test_patch_and_manifest_tamper(self):
        for relative in ('manifest.json', 'dflash-prefix-penalties.patch'):
            with self.subTest(relative=relative):
                site, patches = self.fixture()
                path = patches / relative
                path.write_bytes(path.read_bytes() + b'\n')
                with self.assertRaises(ValueError):
                    overlay.apply(site, patches, 'dflash-seeded', PINS)

    def test_new_helper_must_be_absent(self):
        site, patches = self.fixture()
        (site / overlay.NEW_FILE).write_bytes(b'')
        with self.assertRaises(ValueError):
            overlay.apply(site, patches, 'dflash-seeded', PINS)


if __name__ == '__main__':
    unittest.main()
