"""Check experiment boot HP0 AFI and SMMU readback words from a bounded /dev/mem reader."""

import argparse
from pathlib import Path
import json
import mmap
import struct

REGISTERS = {
    "hp0_read": 0xFD380000,
    "hp0_write": 0xFD380014,
    "fpd_reset": 0xFD1A0100,
    "smmu_nonsecure_scr0": 0xFD800000,
    "smmu_id0": 0xFD800020,
}

def readback(path):
    registers = {}
    with path.open("rb", buffering=0) as device:
        for name, address in REGISTERS.items():
            base = address - address % mmap.PAGESIZE
            with mmap.mmap(device.fileno(), mmap.PAGESIZE, access=mmap.ACCESS_READ, offset=base) as view:
                registers[name] = struct.unpack_from("<I", view, address-base)[0]
    return registers

def verify(registers, previous=None, stage="baseline"):
    if registers["smmu_id0"] != 0x7C013E30 or registers["smmu_nonsecure_scr0"] & 1 != 1:
        raise SystemExit("Expected the live nonsecure SMMU bank in CLIENTPD bypass")
    if stage == "baseline":
        if any(registers[name] != 0x3B0 for name in ("hp0_read", "hp0_write")):
            raise SystemExit("The width-zero restore overlay requires the captured 0x3b0 baseline")
        return
    if previous is None:
        raise SystemExit("Candidate and restored checks require the baseline snapshot")
    if stage == "candidate":
        for name in ("hp0_read", "hp0_write"):
            previous[name] = (previous[name] & ~3) | 1
    if registers != previous:
        raise SystemExit("Readbacks differ from the expected stage state")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("baseline", "candidate", "restored"))
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    snapshot = readback(Path("/dev/mem"))
    print(json.dumps(snapshot, sort_keys=True), flush=True)
    prior = json.loads(args.baseline.read_text()) if args.baseline else None
    verify(snapshot, prior, args.stage)
