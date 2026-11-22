"""Reproduce the pinned prefill-skip RTL and replace only its scalar multiplier."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASELINE_MANIFEST = "c3fc573062521eb1f0e43e6b744afeaa6199b754dc36946f0a8a6c5645c814a1"
BASELINE_GENERATOR = "d5e4f11b07d71f06b9fc2ebfac2683690855f23953284cc0853045d8dc561b7c"


def pin(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Source hash differs: {path}")
    return data


def scalar(text):
    substitutions = (
        ("// No floating point, division operator, or wide combinational multiplier.",
         "// Integer helpers with a 64-by-4 digit multiplier and bit-serial division."),
        ("logic [127:0] multiplicand, product_sum, next_product;\n    logic [63:0] multiplier;",
         """logic [63:0] multiplicand;
    logic [127:0] product_sum, next_product;
    logic [67:0] digit_product, upper_sum;"""),
        ("next_product=product_sum+(multiplier[0] ? multiplicand : 128'd0);",
         """// Consume one base-16 digit. The lower half initially contains |b|.
        // Add the digit product into an extended upper half before shifting.
        digit_product=68'(multiplicand)*product_sum[3:0];
        upper_sum={4'd0,product_sum[127:64]}+digit_product;
        next_product={upper_sum,product_sum[63:4]};"""),
        ("negative<=a[63]^b[63];multiplicand<={64'd0,magnitude(a)};\n"
         "            multiplier<=magnitude(b);product_sum<=0;remaining<=64;",
         "negative<=a[63]^b[63];multiplicand<=magnitude(a);\n"
         "            product_sum<={64'd0,magnitude(b)};remaining<=16;"),
        ("multiplicand<=0;multiplier<=0;product_sum<=0;",
         "multiplicand<=0;product_sum<=0;"),
        ("product_sum<=next_product;multiplicand<=multiplicand<<1;multiplier<=multiplier>>1;",
         "product_sum<=next_product;"),
    )
    for original, replacement in substitutions:
        if text.count(original) != 1:
            raise ValueError(f"Expected exactly one pinned scalar fragment: {original}")
        text = text.replace(original, replacement)
    return text


def materialise(kv260, output):
    baseline = kv260 / "variants/prefill-skip-v1"
    manifest = json.loads(pin(baseline / "manifest.json", BASELINE_MANIFEST))
    generate = baseline / "materialise.py"
    pin(generate, BASELINE_GENERATOR)
    previous = runpy.run_path(str(generate))
    previous["materialise"](kv260, output)
    name = "fixed_scalar"
    path = output / f"{name}.sv"
    modified = scalar(pin(path, manifest[name]).decode()).encode()
    manifest[name] = sha256(modified).hexdigest()
    if manifest != json.loads((HERE / "manifest.json").read_bytes()):
        raise ValueError("Generated scalar variant differs from its pinned closure")
    path.write_bytes(modified)
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return list(manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output)
