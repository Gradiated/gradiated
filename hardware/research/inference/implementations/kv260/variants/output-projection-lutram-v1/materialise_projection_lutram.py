"""Change only the mapping directive for the output-projection weight array."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASE = "variants/attention-exp-div-v1"


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def replace_one(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one source match: {old}")
    return source.replace(old, new, 1)


def candidate_source(transformer, dense):
    clone = replace_one(dense, "module dense #(", "module dense_output_projection_lutram #(")
    declaration = "    logic signed [15:0] weight_memory [0:INPUTS*OUTPUTS-1];"
    clone = replace_one(clone, declaration, '    (* ram_style = "distributed" *) ' + declaration.lstrip())
    binding = "    dense #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) output_projection ("
    updated = replace_one(transformer, binding, binding.replace("dense ", "dense_output_projection_lutram ", 1))
    return (updated + "\n" + clone).encode()


def materialise(kv260, output, candidate):
    spec = json.loads((HERE/"manifest.json").read_bytes())
    control = kv260/BASE
    generator = control/"materialise_attention_exp.py"
    checked(generator, spec["control_generator_sha256"])
    checked(control/"manifest.json", spec["control_manifest_sha256"])
    names = runpy.run_path(str(generator))["materialise"](kv260, output, True)
    if candidate:
        transformer = checked(output/"transformer.sv", spec["control_transformer_sha256"]).decode()
        dense = checked(output/"dense.sv", spec["control_dense_sha256"]).decode()
        result = candidate_source(transformer, dense)
        pin = spec["candidate_transformer_sha256"]
        if sha256(result).hexdigest() != pin:
            raise ValueError("Generated transformer differs from registered candidate")
        (output/"transformer.sv").write_bytes(result)
        ledger = output/"source-manifest.json"
        values = json.loads(ledger.read_bytes())
        values["transformer"] = pin
        ledger.write_text(json.dumps(values, indent=2)+"\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
