#!/usr/bin/env python3
"""Apply the pinned-image cuSPARSE include repair to one generated Ninja file."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import select
import sys
import time


root = Path(sys.argv[1])
target = root / "build" / "build.ninja"
include = "-I/usr/local/lib/python3.12/dist-packages/nvidia/cusparse/include"
libc = ctypes.CDLL("libc.so.6", use_errno=True)
fd = libc.inotify_init1(os.O_CLOEXEC)
if fd < 0:
    raise OSError(ctypes.get_errno(), "inotify_init1")
watch = libc.inotify_add_watch(fd, os.fsencode(root / "build"), 0x00000008)
if watch < 0:
    raise OSError(ctypes.get_errno(), "inotify_add_watch")
end = time.monotonic() + 180.0
while time.monotonic() < end:
    ready, _, _ = select.select([fd], [], [], 1.0)
    if not ready or not target.is_file():
        continue
    text = target.read_text()
    marker = "cuda_cflags = "
    if marker not in text:
        continue
    replacement = marker + include + " "
    if replacement not in text:
        target.write_text(text.replace(marker, replacement, 1))
    print("patched", target, flush=True)
    raise SystemExit(0)
raise TimeoutError("generated_build_ninja_not_observed")
