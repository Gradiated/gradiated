"""Specialise the fixed exponential divider in the adopted attention circuit."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CACHE = "variants/attention-cache-pipeline-v1"
FF = "variants/ff-exp-div-v1"


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def specialise(kv260, rtl, spec):
    root = kv260 / FF
    generator = root / "materialise_ff_exp.py"
    checked(generator, spec["feedforward_generator_sha256"])
    snippet = checked(root / "exp_divide_start.svh", spec["helper_sha256"]).decode()
    scalar = checked(rtl / "fixed_scalar.sv", spec["generic_scalar_sha256"]).decode()
    attention = checked(rtl / "attention.sv", spec["control_attention_sha256"]).decode()
    clone = runpy.run_path(str(generator))["specialise"](attention, scalar, snippet)
    if clone.count("fixed_scalar_ff_exp") != 2:
        raise ValueError("Unexpected clone identifiers")
    return clone.replace("fixed_scalar_ff_exp", "fixed_scalar_attention_exp").encode()


def materialise(kv260, output, candidate):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    control = kv260 / CACHE
    generator = control / "materialise_attention.py"
    checked(generator, spec["control_generator_sha256"])
    checked(control / "manifest.json", spec["control_manifest_sha256"])
    names = runpy.run_path(str(generator))["materialise"](kv260, output, True)
    if candidate:
        proof = specialise(kv260, output, spec)
        pin = spec["candidate_attention_sha256"]
        if sha256(proof).hexdigest() != pin:
            raise ValueError("Generated attention source does not match its manifest")
        (output / "attention.sv").write_bytes(proof)
        manifest = output / "source-manifest.json"
        hashes = json.loads(manifest.read_bytes())
        hashes["attention"] = pin
        manifest.write_text(json.dumps(hashes, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
