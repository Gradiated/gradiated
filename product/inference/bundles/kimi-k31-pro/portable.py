import json
import hashlib
import os
from pathlib import Path
import shutil
import sys
import sysconfig

DESTINATION = Path('/bundle')
SOURCE = Path('/sgl-workspace/sglang')
EXPECTED_SOURCE = 'afcd7d6b487a9cbe73e25941971b4cc107e6f9ae'
IMAGE = 'lmsysorg/sglang@sha256:4a098ad7414702a2271296ac148854448d10710ec3554ac93b57ef194999305a'
NINJA_SHA256 = '08639e194fffa7f08b259fc4abfa4803aff66b64de52549cee42ec527d55cea6'


def copy(source, destination):
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))


def relocate_links(root, python_prefix):
    prefixes = {
        '/opt/sglang/': root / 'python',
        str(python_prefix).rstrip('/') + '/': root / 'python',
        '/usr/local/cuda-13.0/': root / 'cuda',
        '/sgl-workspace/sglang/python/sglang/': root / 'python/lib/python3.12/site-packages/sglang',
    }
    for path in root.rglob('*'):
        if not path.is_symlink():
            continue
        target = os.readlink(path)
        if not target.startswith('/'):
            continue
        for prefix, destination in prefixes.items():
            if target.startswith(prefix):
                relocated = destination / target[len(prefix):]
                path.unlink()
                path.symlink_to(os.path.relpath(relocated, path.parent))
                break
        else:
            raise ValueError(f'Runtime symlink leaves its bundle: {path.relative_to(root)}')


def package():
    actual = (SOURCE / '.k31-source-commit').read_text().strip()
    if actual != EXPECTED_SOURCE:
        raise ValueError('Kimi image source identity changed')
    python = DESTINATION / 'python'
    copy(Path(sys.base_prefix), python)
    ninja = Path('/opt/sglang/bin/ninja')
    if hashlib.sha256(ninja.read_bytes()).hexdigest() != NINJA_SHA256:
        raise ValueError('Kimi image Ninja identity changed')
    shutil.copy2(ninja, python / 'bin/ninja')
    site = python / 'lib/python3.12/site-packages'
    copy(Path(sysconfig.get_paths()['purelib']), site)
    for path in site.glob('__editable__*sglang*'):
        path.unlink()
    for path in site.glob('*.pth'):
        if '/sgl-workspace/sglang/python' in path.read_text():
            path.unlink()
    copy(SOURCE / 'python/sglang', site / 'sglang')
    copy(Path('/usr/local/cuda-13.0'), DESTINATION / 'cuda')
    relocate_links(DESTINATION, Path(sys.base_prefix))
    from overlay_patches import apply
    overlay = apply(site, Path('/k31-patches'), 'dflash-admitted-cache-accounting-fused-philox',
                    json.loads(Path('/manifest-pins.json').read_text()))
    from draft import package as package_draft
    draft_identity = package_draft(Path('/draft-manifest.json'), DESTINATION / 'models/kimi-dflash')
    (DESTINATION / 'provenance.json').write_text(json.dumps({
        'source_image': IMAGE, 'sglang_source': actual,
        'kimi_overlay_fingerprint': overlay['fingerprint'],
        'kimi_dflash': draft_identity,
        'python_version': sys.version.split()[0],
    }, sort_keys=True) + '\n')
    print('Portable Kimi stack copied', flush=True)


if __name__ == '__main__':
    package()
