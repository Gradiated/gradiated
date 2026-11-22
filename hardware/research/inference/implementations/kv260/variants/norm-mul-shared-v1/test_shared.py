"""Verify ownership, reset, holding and full signed products against Python integers."""

import argparse
from pathlib import Path
import random
import time

from replay_shared import run, tool_environment


def write_vectors(path):
    low, high = -(1 << 63), (1 << 63) - 1
    rng = random.Random(2026111921)
    vectors = [(0, low), (1, low), (-1, low), (low, low), (high, 1), (high, -1), (high, 2),
               (-(1 << 31), 1 << 31), (0, high), (-1, -1), (1 << 32, 1 << 32), (65535, 65535)]
    vectors += [(rng.randrange(-(1 << 31), 1 << 31), rng.randrange(-(1 << 31), 1 << 31))
                for _ in range(192)]
    vectors += [(rng.randrange(low, high+1), rng.randrange(low, high+1)) for _ in range(192)]
    assert len(vectors) % 3 == 0
    with path.open("x") as out:
        for a, b in vectors:
            product = a * b
            error = abs(product) > high
            result = 0 if error else product
            mask = (1 << 64) - 1
            print(f"{a&mask:016x} {b&mask:016x} {result&mask:016x} {int(error):x}", file=out)
    return len(vectors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("shared", "verilator", "output"):
        parser.add_argument("--"+name, type=lambda p: Path(p).resolve(), required=True)
    args = parser.parse_args()
    output = args.output
    output.mkdir()
    env = tool_environment(args.verilator)
    vectors = output/"vectors.txt"
    count = write_vectors(vectors)
    binary = output/"obj/scalar-test"
    deadline = time.monotonic()+300
    run([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
         "-j", "2", "--top-module", "shared_scalar_tb", "--Mdir", str(binary.parent),
         "-o", binary.name, str(args.shared/"rmsnorm.sv"),
         str(Path(__file__).parent/"shared_scalar_tb.sv")],
        output, env, output/"compile.log", 150, deadline)
    run([str(binary), f"+TEST_VECTORS={vectors}", f"+TEST_BATCHES={count//3}"],
        output, env, output/"simulation.log", 120, deadline)
    log = (output/"simulation.log").read_text()
    expected = f"PASS shared scalar: {count} exact signed products, 4 blocked response clocks, five reset points"
    if expected not in log:
        raise ValueError("Missing directed completion receipt")
    print(expected)


if __name__ == "__main__":
    main()
