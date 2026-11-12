import shutil
import sys
import tempfile
from pathlib import Path

from torch.utils.cpp_extension import load

import sglang.srt.mem_cache.cpp_utils.native_hash as native_hash


def build():
    directory = Path(native_hash.__file__).parent
    with tempfile.TemporaryDirectory() as build_directory:
        # Matches the runtime JIT flags on AVX2 hosts; the overlay loads it only there.
        load(name='hicache_hash_cpp', sources=[str(directory / 'hash_binding.cpp')],
             extra_cflags=['-O3', '-std=c++17', '-DNDEBUG', '-mavx2'], extra_ldflags=['-lcrypto'],
             build_directory=build_directory, with_cuda=False)
        shutil.copy2(Path(build_directory) / 'hicache_hash_cpp.so', directory / 'hicache_hash_cpp.so')


if __name__ == '__main__':
    sys.exit(build())
