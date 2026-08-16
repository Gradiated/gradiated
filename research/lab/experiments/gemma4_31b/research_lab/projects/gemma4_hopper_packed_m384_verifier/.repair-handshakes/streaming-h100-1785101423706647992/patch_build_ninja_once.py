#!/usr/bin/env python3
import ctypes
import os
from pathlib import Path
import select
import sys
import time

root = Path(sys.argv[1])
target = root / "build" / "build.ninja"
packages = "cublas cuda_cupti cuda_nvrtc cuda_runtime cudnn cufft cufile curand cusolver cusparse cusparselt nccl nvjitlink nvshmem nvtx".split()
includes = " ".join(f"-I/usr/local/lib/python3.12/dist-packages/nvidia/{name}/include" for name in packages)
libc = ctypes.CDLL("libc.so.6", use_errno=True)
fd = libc.inotify_init1(os.O_CLOEXEC)
if fd < 0 or libc.inotify_add_watch(fd, os.fsencode(root / "build"), 0x00000008) < 0:
    raise OSError(ctypes.get_errno(), "inotify_setup")
end = time.monotonic() + 180.0
while time.monotonic() < end:
    ready, _, _ = select.select([fd], [], [], 1.0)
    if ready and target.is_file():
        marker = "cuda_cflags = "
        text = target.read_text()
        if marker in text:
            target.write_text(text.replace(marker, marker + includes + " ", 1))
            print("patched", target, flush=True)
            raise SystemExit(0)
raise TimeoutError("generated_build_ninja_not_observed")
