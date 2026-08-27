#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess

from kda_reference import KDAReference, generate_tokens


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    args = parser.parse_args()
    head_dim = 16
    token_count = 3
    seed = 0x4B444131
    completed = subprocess.run(
        [
            args.executable,
            "--reference-only",
            "--head-dim",
            str(head_dim),
            "--tokens",
            str(token_count),
            "--seed",
            hex(seed),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    actual = json.loads(completed.stdout)
    reference = KDAReference(head_dim)
    expected = [reference.step(token) for token in generate_tokens(head_dim, token_count, seed)]
    if actual != {"head_dim": head_dim, "outputs": expected}:
        raise SystemExit("C and Python reference outputs differ")
    print(f"PASS host_reference head_dim={head_dim} tokens={token_count}")


if __name__ == "__main__":
    main()
