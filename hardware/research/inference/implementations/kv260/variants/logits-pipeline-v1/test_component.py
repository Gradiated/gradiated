"""Validate both exact matrix lanes against signed integer fixtures."""

import argparse
import json
from pathlib import Path
import random
import runpy
import time

from materialise import BASE_GENERATOR, materialise, pin
from test_model import DIV_TEST

SEED = 260005


def signed_hex(values, bits, path):
    path.write_text("".join(f"{value % (1 << bits):0{(bits + 3)//4}x}\n" for value in values))


def fixture(directory):
    rng = random.Random(SEED)
    draw = lambda: rng.randrange(-32768, 32768)
    inputs = [1, -32768, 32767, *[draw() for _ in range(29)]]
    weights = [[draw() for _ in inputs] for _ in range(320)]
    weights[:6] = [[tie, *[0] * 31] for tie in (128, -128, 384, -384, 640, -640)]
    weights[6] = [-32768 if value < 0 else 32767 for value in inputs]
    weights[7] = [32767 if value < 0 else -32768 for value in inputs]
    products, sums, rounded = [], [], []
    for row in weights:
        total = 0
        for x, w in zip(inputs, row, strict=True):
            product = x * w
            total += product
            products.append(product)
            sums.append(total)
        quotient, remainder = divmod(total, 256)
        rounded.append(quotient + int(remainder > 128 or (remainder == 128 and quotient % 2)))
    if rounded[:6] != [0, 0, 2, -2, 2, -2] or not rounded[6] > 32767 or not rounded[7] < -32768:
        raise ValueError("Expected signed rounding and clipping cases")
    signed_hex(inputs, 16, directory / "input.hex")
    signed_hex((value for row in weights for value in row), 16, directory / "weights.hex")
    signed_hex(products, 32, directory / "products.hex")
    signed_hex(sums, 48, directory / "sums.hex")
    for width in (16, 32):
        minimum, maximum = -(1 << (width - 1)), (1 << (width - 1)) - 1
        clipped = [((not minimum <= value <= maximum) << 32) |
                   (min(max(value, minimum), maximum) & 0xffffffff) for value in rounded]
        signed_hex(clipped, 33, directory / f"answers{width}.hex")


def main(args):
    deadline = min(time.monotonic() + 300, time.monotonic() + args.deadline_epoch - time.time())
    baseline = args.kv260 / "variants/scalar-div-v1"
    pin(baseline / "test_model.py", DIV_TEST)
    pin(baseline / "make_division.py", BASE_GENERATOR)
    helpers, _ = runpy.run_path(str(baseline / "test_model.py"))["prior"](args.kv260)
    env = helpers["simulator"](args.verilator.resolve(), args.kv260)
    run = helpers["run"]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    fixture(root)
    rtl = root / "rtl"
    materialise(args.kv260, rtl)
    bench = Path(__file__).resolve().with_name("logits_component_tb.sv")
    binary = root / "obj/simulation"
    run([str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
         "--top-module", "logits_component_tb", "-j", "2", "--Mdir", str(binary.parent), "-o", "simulation",
         str(rtl / "dense.sv"), str(rtl / "transformer.sv"), str(bench)],
        root, env, root / "compile.log", 150, deadline)
    run([str(binary), "+FIXTURES=" + str(root)], root, env, root / "simulation.log", 60, deadline)
    result = {"seed": SEED, "rows": 320, "ordered_pairs_per_arm": 10240, "result_widths": [32, 16],
              "reset_offsets_in_first_row": 41, "row_boundary_reset": True, "stalled_output_cycles": 11,
              "complete_projection_cycles_saved": 9920}
    (root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print((root / "simulation.log").read_text().strip(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kv260", "verilator", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--deadline-epoch", required=True, type=float)
    main(parser.parse_args())
