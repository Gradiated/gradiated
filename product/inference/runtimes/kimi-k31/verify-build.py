import importlib
import hashlib
import json
from pathlib import Path
import sys
import subprocess

from config import SGLANG_SOURCE, KIMI_OVERLAY_FINGERPRINT
from overlay_patches import verify as verify_overlay
from draft import verify as verify_draft


def verify(root):
    for path in root.rglob('*'):
        if path.is_symlink() and (not path.exists() or not path.resolve().is_relative_to(root)):
            raise ValueError('Runtime symlink leaves its verified bundle or is broken')
    provenance = json.loads((root / 'provenance.json').read_text())
    if provenance['sglang_source'] != SGLANG_SOURCE:
        raise ValueError('Kimi SGLang source identity differs from its launcher')
    if verify_draft(root / 'models/kimi-dflash') != provenance.get('kimi_dflash'):
        raise ValueError('Kimi draft checkpoint differs from its archive provenance')
    ninja = root / 'python/bin/ninja'
    if hashlib.sha256(ninja.read_bytes()).hexdigest() != '08639e194fffa7f08b259fc4abfa4803aff66b64de52549cee42ec527d55cea6':
        raise ValueError('Kimi JIT Ninja identity differs from its source image')
    result = subprocess.run([str(ninja), '--version'], capture_output=True, text=True, check=True, timeout=10)
    if result.stdout.strip() != '1.13.2.git.kitware.jobserver-pipe-1':
        raise ValueError('Kimi JIT Ninja version is unexpected')
    for name in ['torch', 'sglang', 'sglang.srt.mem_cache.rust_tree_core.extension', 'smg.smg_rs']:
        module = importlib.import_module(name)
        location = Path(module.__file__).resolve()
        if not location.is_relative_to(root):
            raise ValueError('Runtime imported a module outside its verified bundle')
    site = root / 'python/lib/python3.12/site-packages'
    verify_overlay(site, KIMI_OVERLAY_FINGERPRINT)
    if provenance.get('kimi_overlay_fingerprint') != KIMI_OVERLAY_FINGERPRINT:
        raise ValueError('Kimi overlay provenance differs from its launcher')
    header = site / 'flashinfer/data/include/flashinfer/trtllm/fused_moe/RoutingCustomPolicy.cuh'
    if 'DynBlockKernelMaxNumExperts = 1024;' not in header.read_text():
        raise ValueError('FlashInfer routing does not cover all Kimi experts')
    native = (site / 'sgl_kernel/flashmla_ops.abi3.so').read_bytes()
    if b'sparse_decode_num_sm_parts' not in native:
        raise ValueError('Kimi sparse decode native support is missing')
    from smg import smg_rs
    if getattr(smg_rs, 'GRADIATED_REFUSED_UPLOAD_DRAIN_VERSION', None) != 1:
        raise ValueError('SMG refused-upload drain fix is missing')
    print('Portable Kimi build verification passed')


if __name__ == '__main__':
    verify(Path(sys.argv[1]).resolve())
