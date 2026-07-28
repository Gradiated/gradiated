"""Same-claim compatibility shim for the frozen queue-gauge parser."""

import re as _re


_findall = _re.findall


def findall(pattern, string, flags=0):
    if pattern == r"sglang:(?:num_running_reqs|num_queue_reqs)\s+([0-9.]+)":
        values = []
        for line in string.splitlines():
            if line.startswith("sglang:num_running_reqs") or line.startswith(
                "sglang:num_queue_reqs"
            ):
                values.append(line.rsplit(" ", 1)[-1])
        return values
    return _findall(pattern, string, flags)


_re.findall = findall
