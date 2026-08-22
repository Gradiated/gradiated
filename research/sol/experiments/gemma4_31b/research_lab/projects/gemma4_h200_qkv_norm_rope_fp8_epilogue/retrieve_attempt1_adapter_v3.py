#!/usr/bin/env python3
import hashlib
import os
import pathlib
import sys


PROJECT = pathlib.Path(__file__).resolve().parent
ORIGINAL = PROJECT / "endpoint_execution_packet.py"
ATTEMPT_ONE = PROJECT / "artifacts/cold-endpoint-owner/run/attempt-1"
ORIGINAL_SHA256 = "e1015a5b0101282dee95471484b77ec7355835782717f8eae9e240e5d90b8cdf"


def main() -> None:
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != ORIGINAL_SHA256:
        raise SystemExit("retrieval packet identity mismatch")
    arguments = sys.argv[1:]
    for index, argument in enumerate(arguments):
        if argument == "--prior-artifact-root":
            arguments[index + 1] = str(ATTEMPT_ONE)
            break
    else:
        raise SystemExit("retrieval adapter requires --prior-artifact-root")
    os.execv(sys.executable, [sys.executable, str(ORIGINAL), *arguments])


if __name__ == "__main__":
    main()
