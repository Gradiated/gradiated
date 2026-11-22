#!/usr/bin/env python3
"""Control the fixed-matrix KV260 DDR4 fixture via its Linux arm64 driver."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

DEVICE = "/dev/kv260-ddr4-weights"
MATRIX_BYTES = 2048
MATRIX_SHA256 = "a470ed9570d1ebf01a5431fda805d02e0e11b88dcb0e06785e324bdd37c57e89"
COUNTERS = (
    "useful_bytes", "reads", "beats", "faults", "extra_clocks", "ar_stalls",
    "response_wait", "projection_count", "projection_clocks", "magic",
)
STATE = struct.Struct("=" + "I" * (4 + len(COUNTERS)))

# Linux arm64 uses asm-generic/ioctl.h. Mirrors kv260_ddr4_uapi.h.
IO_TYPE = ord("W") << 8
STATE_IOCTL = (2 << 30) | (STATE.size << 16) | IO_TYPE
COMMANDS = {"bram": IO_TYPE | 1, "ddr": IO_TYPE | 2, "clear": IO_TYPE | 3}


def read_matrix(path):
    with path.open("rb") as image:
        data = image.read(MATRIX_BYTES + 1)
    if len(data) != MATRIX_BYTES:
        raise ValueError(f"expected {MATRIX_BYTES} matrix bytes")
    if hashlib.sha256(data).hexdigest() != MATRIX_SHA256:
        raise ValueError("matrix SHA-256 does not match the frozen bank 4 image")
    return data


def read_state(fd):
    raw = fcntl.ioctl(fd, STATE_IOCTL, bytes(STATE.size))
    dma_base, dma_bytes, hardware_base, status, *counters = STATE.unpack(raw)
    return {
        "dma_base": f"0x{dma_base:08x}",
        "dma_bytes": dma_bytes,
        "hardware_base": f"0x{hardware_base:08x}",
        "status_raw": f"0x{status:08x}",
        "mode": "ddr" if status & 1 else "bram",
        "transport_busy": bool(status & 2),
        "fault": bool(status & 4),
        "safe_release": bool(status & 8),
        "counter_saturated": bool(status & 16),
        **dict(zip(COUNTERS, counters)),
    }


class Fixture:
    """Own one control fd. Only clear() permits the kernel to free the page."""

    def __enter__(self):
        self.fd = os.open(DEVICE, os.O_RDWR | os.O_CLOEXEC)
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def load(self, path):
        data = read_matrix(Path(path))
        if os.write(self.fd, data) != len(data):
            raise OSError("driver returned a short matrix upload")
        return {**self.state(), "matrix_sha256": MATRIX_SHA256}

    def select(self, mode):
        if mode not in ("bram", "ddr"):
            raise ValueError(f"unknown weight source {mode!r}")
        fcntl.ioctl(self.fd, COMMANDS[mode])

    def clear(self):
        fcntl.ioctl(self.fd, COMMANDS["clear"])

    def state(self):
        return read_state(self.fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    load = subparsers.add_parser("load", help="authenticate and pin the frozen matrix")
    load.add_argument("image", type=Path)
    for command in ("status", "bram", "ddr", "clear"):
        subparsers.add_parser(command)
    args = parser.parse_args()

    try:
        with Fixture() as fixture:
            if args.command == "load":
                state = fixture.load(args.image)
            else:
                if args.command == "clear":
                    fixture.clear()
                elif args.command in ("bram", "ddr"):
                    fixture.select(args.command)
                state = fixture.state()
        print(json.dumps(state, sort_keys=True))
    except (OSError, ValueError) as error:
        print(f"{args.command}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
