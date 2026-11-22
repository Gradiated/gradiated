"""Shorten only the probability division in the selected Exp13 attention controller."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ADOPTED = "variants/attention-exp-pair-v2"


def digest(data):
    return sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or digest(data) != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def specialise(source):
    replacements = (
        (
            "    fixed_scalar_attention_exp scalar (",
            "    fixed_scalar_attention_exp #(.SHORT_PROBABILITY_DIVISION(1'b1)) scalar (",
        ),
        (
            "module fixed_scalar_attention_exp (",
            """module fixed_scalar_attention_exp #(
    parameter bit SHORT_PROBABILITY_DIVISION = 1'b0
) (""",
        ),
        (
            "                            else divide_start(cmd_a,$unsigned(cmd_b),1,SIMPLE_DONE);",
            """                            else begin
                                divide_start(cmd_a,$unsigned(cmd_b),1,SIMPLE_DONE);
                                // For A = E << 15 with 0 <= E <= B, A >> 16 < B.
                                // The skipped digits are all zero, with this prefix as remainder.
                                if(SHORT_PROBABILITY_DIVISION && !cmd_a[63] &&
                                   {16'd0,cmd_a[63:16]} < $unsigned(cmd_b)) begin
                                    numerator<={cmd_a[15:0],48'd0};
                                    remainder<={17'd0,cmd_a[63:16]};
                                    remaining<=7'd8;
                                end
                            end""",
        ),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError(f"Unexpected adopted attention source: {old}")
        source = source.replace(old, new, 1)
    return source


def materialise(kv260, output, candidate):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    adopted = kv260 / ADOPTED
    generator = adopted / "materialise_attention_pair.py"
    checked(generator, spec["control_generator_sha256"])
    checked(adopted / "manifest.json", spec["control_manifest_sha256"])
    names = runpy.run_path(str(generator))["materialise"](kv260, output, True)
    ledger = output / "source-manifest.json"
    checked(ledger, spec["control_rtl_manifest_sha256"])
    hashes = json.loads(ledger.read_bytes())
    for name, expected in hashes.items():
        checked(output / (name + ".sv"), expected)
    if candidate:
        attention = output / "attention.sv"
        data = specialise(attention.read_text()).encode()
        pin = spec["candidate_attention_sha256"]
        if digest(data) != pin:
            raise ValueError("Generated attention source differs")
        attention.write_bytes(data)
        hashes["attention"] = pin
        ledger.write_text(json.dumps(hashes, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
