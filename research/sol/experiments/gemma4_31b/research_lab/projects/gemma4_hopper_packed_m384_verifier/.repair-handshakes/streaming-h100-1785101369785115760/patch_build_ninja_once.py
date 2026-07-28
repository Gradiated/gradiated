#!/usr/bin/env python3
"""Expose all pinned-image NVIDIA Python-wheel development headers to Ninja once."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import select
import sys
import time


root = Path(sys.argv[1])
target = root / "build" / "build.ninja"
includes = " ".join(
    f"-I{path}"
    for path in sorted(Path("/usr/local/lib/python3.12/dist-packages/nvidia").glob("*/include"))
    if path.is_dir()
)
if not includes:
    raise RuntimeError("pinned_image_nvidia_include_roots_missing")
libc = ctypes.CDLL("libc.so.6", use_errno=True)
fd = libc.inotify_init1(os.O_CLOEXEC)
if fd < 0:
    raise OSError(ctypes.get_errno(), "inotify_init1")
if libc.inotify_add_watch(fd, os.fsencode(root / "build"), 0x00000008) < 0:
    raise OSError(ctypes.get_errno(), "inotify_add_watch")
end = time.monotonic() + 180.0
while time.monotonic() < end:
    ready, _, _ = select.select([fd], [], [], 1.0)
    if not ready or not target.is_file():
        continue
    text = target.read_text()
    marker = "cuda_cflags = "
    if marker in text:
        target.write_text(text.replace(marker, marker + includes + " ", 1))
        print("patched", target, flush=True)
        raise SystemExit(0)
raise TimeoutError("generated_build_ninja_not_observed")
