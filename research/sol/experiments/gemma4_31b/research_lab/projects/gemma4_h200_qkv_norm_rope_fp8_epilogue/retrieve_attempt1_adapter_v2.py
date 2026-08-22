#!/usr/bin/env python3
import hashlib
import os
import pathlib
import sys


PROJECT = pathlib.Path(__file__).resolve().parent
ORIGINAL = PROJECT / "endpoint_execution_packet.py"
ATTEMPT_ONE = PROJECT / "artifacts/cold-endpoint-owner/run/attempt-1"
ORIGINAL_SHA256 = "713c7ce46d60b105004bfab2c992bc533ec9be49804a6a7bab2e005a6cebcc5e"


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
