"""Materialise the final token-score pipeline from pinned scalar-div RTL."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASE_MANIFEST = "73123c2c753093e1e359de64a98b98e48471382ba4bd85758108ab7a78944f13"
BASE_GENERATOR = "26cbfb0abd729f96b1455dd76bc7876b369269a1063e6e3a9e3d32ce60ee66a1"


def pin(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Source differs: {path}")
    return data


def replace(text, target, replacement):
    if text.count(target) != 1:
        raise ValueError(f"Expected one occurrence: {target}")
    return text.replace(target, replacement)


def pipeline(dense):
    dense = dense[dense.index("module dense #("):]
    changes = (
        ("module dense #(", "module logits_dense #("),
        ("    logic [INPUT_BITS-1:0] address;",
         "    logic [INPUT_BITS-1:0] address, read_address;\n"
         "    logic advance_mac;"),
        ("    assign read_weight_address = WEIGHT_BITS'(int'(row)*INPUTS+int'(address));",
         "    assign advance_mac = state == MAC && int'(address) != INPUTS-1;\n"
         "    assign read_address = address + INPUT_BITS'(advance_mac);\n"
         "    assign read_weight_address = WEIGHT_BITS'(int'(row)*INPUTS+int'(read_address));"),
        ("            step_valid <= 0;\n            case (state)",
         "            step_valid <= 0;\n"
         "            // Prime coordinate zero, then fetch the following pair during its predecessor's MAC.\n"
         "            if (state == READ || advance_mac) begin\n"
         "                operand_x <= input_memory[read_address];\n"
         "                operand_w <= weight_memory[read_weight_address];\n"
         "            end\n"
         "            case (state)"),
        ("                READ: begin\n"
         "                    operand_x <= input_memory[address];\n"
         "                    operand_w <= weight_memory[read_weight_address];\n"
         "                    state <= MAC;\n"
         "                end",
         "                READ: state <= MAC;"),
        ("                    else begin address <= address + 1'b1; state <= READ; end",
         "                    else address <= read_address;"),
    )
    for target, replacement in changes:
        dense = replace(dense, target, replacement)
    return dense


def materialise(kv260, output):
    baseline = kv260 / "variants/scalar-div-v1"
    sources = json.loads(pin(baseline / "manifest.json", BASE_MANIFEST))
    generator = baseline / "make_division.py"
    pin(generator, BASE_GENERATOR)
    names = runpy.run_path(str(generator))["materialise"](kv260, output)
    control = pin(output / "transformer.sv", sources["transformer"]).decode()
    dense = pin(output / "dense.sv", sources["dense"]).decode()
    candidate = replace(
        control,
        "    dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(32)) logits (",
        "    logits_dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(32)) logits (",
    )
    generated = (candidate + "\n" + pipeline(dense)).encode()
    sources["transformer"] = sha256(generated).hexdigest()
    if sources != json.loads((HERE / "manifest.json").read_bytes()):
        raise ValueError("Token-score pipeline source closure differs")
    (output / "transformer.sv").write_bytes(generated)
    (output / "source-manifest.json").write_text(json.dumps(sources, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output)
