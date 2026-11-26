"""The complete frozen public comparison, including questions and expected answers."""

import hashlib

JEVBENCH_SHA256 = "758521e9b09dbdb1adbcac469ff6e1b11e6830f9f396a8ea9cdc4be5741eb092"


def verify_benchmark(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != JEVBENCH_SHA256:
        raise ValueError("benchmark differs from the complete frozen public comparison")
    return digest
