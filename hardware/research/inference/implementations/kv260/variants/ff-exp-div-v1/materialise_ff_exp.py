"""Generate the adopted eight-lane sources with one feed-forward scalar substitution."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL = "variants/logits-8-lanes-v1"
CONTROL_PINS = {
    "materialise_eight.py": "cb877d288638ddabb90f9aab626d547951f2d077bd127116658bde0d55c38bb9",
    "manifest.json": "5236089e0455414df2aa095e153667cda0e6615987f3884bef479bc9cda9545f",
}
SOURCE_PINS = {
    "fixed_scalar": "bb15ed311fd921e4c26b059272f2393cc5ca2249849aa3bebd6ffc1f730166e7",
    "feedforward": "030f2917a8c6df23e18da1d2ef5e3394833c070a22a0a676f4aace705d1253d0",
    "transformer": "dc5851764926a6b5e3638aea760eb025d86da844241497a175e125c6210d0e2d",
}


def pinned(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Artifact changed: {path}")
    return data


def replace_one(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source match: {old}")
    return text.replace(old, new)


def specialise(feedforward, scalar, helper):
    clone = scalar
    for old, new in (
        ("module fixed_scalar (", "module fixed_scalar_ff_exp ("),
        ("    task automatic multiply_start", helper + "    task automatic multiply_start"),
        ("divide_start(-cmd_a,64'd45426,0,EXP_POWER)", "exp_divide_start(-cmd_a,0,EXP_POWER)"),
        ("divide_start($signed({remainder[55:0],8'd0}),64'd45426,0,EXP_INDEX)",
         "exp_divide_start($signed({remainder[55:0],8'd0}),0,EXP_INDEX)"),
        ("divide_start(math_value,64'd45426,1,EXP_DONE)", "exp_divide_start(math_value,1,EXP_DONE)"),
    ):
        clone = replace_one(clone, old, new)
    return replace_one(feedforward, "    fixed_scalar scalar (", "    fixed_scalar_ff_exp scalar (") + "\n" + clone


def materialise(kv260, output, candidate):
    control = kv260 / CONTROL
    for name, expected in CONTROL_PINS.items():
        pinned(control / name, expected)
    generator = runpy.run_path(str(control / "materialise_eight.py"))["materialise"]
    names = generator(kv260, output, 8)
    for name, expected in SOURCE_PINS.items():
        pinned(output / (name + ".sv"), expected)
    if candidate:
        manifest = json.loads((HERE / "manifest.json").read_bytes())
        snippet = pinned(HERE / "exp_divide_start.svh", manifest["helper_sha256"]).decode()
        feed = output / "feedforward.sv"
        generated = specialise(feed.read_text(), (output / "fixed_scalar.sv").read_text(), snippet).encode()
        expected = manifest["feedforward_sha256"]
        if sha256(generated).hexdigest() != expected:
            raise ValueError("New feed-forward RTL closure differs")
        feed.write_bytes(generated)
        ledger = output / "source-manifest.json"
        hashes = json.loads(ledger.read_bytes())
        hashes["feedforward"] = expected
        ledger.write_text(json.dumps(hashes, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
