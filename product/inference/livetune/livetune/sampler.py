"""A sampling profiler for one thread of this process, for hosts where py-spy cannot attach.

Containers without ptrace (CAP_SYS_PTRACE) refuse py-spy. This samples the target thread's Python
stack from a background thread with sys._current_frames and writes collapsed stacks in py-spy's raw
format, one "outer;...;inner count" line per distinct stack. Each sample holds the GIL briefly, so a
10 ms interval costs the target thread well under 1% while it runs.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import Counter
from pathlib import Path


def _frame_name(frame) -> str:
    code = frame.f_code
    return f"{code.co_name} ({os.path.basename(code.co_filename)}:{frame.f_lineno})"


def collapse(frame) -> str:
    names = []
    while frame is not None:
        names.append(_frame_name(frame))
        frame = frame.f_back
    return ";".join(reversed(names))


class StackSampler:
    def __init__(self, thread_id: int, seconds: float, path: str | Path, interval_s: float = 0.01) -> None:
        self.thread_id, self.seconds, self.path, self.interval_s = thread_id, seconds, Path(path), interval_s
        self.samples = 0
        self.done = threading.Event()
        self._thread = threading.Thread(target=self._run, name="livetune-sampler", daemon=True)

    def start(self) -> "StackSampler":
        self._thread.start()
        return self

    def _run(self) -> None:
        stacks: Counter[str] = Counter()
        deadline = time.monotonic() + self.seconds
        try:
            while time.monotonic() < deadline:
                frame = sys._current_frames().get(self.thread_id)
                if frame is not None:
                    stacks[collapse(frame)] += 1
                    self.samples += 1
                del frame
                time.sleep(self.interval_s)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as handle:
                handle.writelines(f"{stack} {count}\n" for stack, count in stacks.most_common())
        finally:
            self.done.set()
