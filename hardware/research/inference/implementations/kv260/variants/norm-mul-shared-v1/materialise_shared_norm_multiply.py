"""Generate the shared RMSNorm multiply closure from pinned dedicated RTL."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CHANGED = ("rmsnorm", "transformer")
KERNEL = "variants/ff-scalar-mul-dsp-v1/multiply_datapath.svh"
PORTS = """output logic mul_request,
    input logic mul_grant,
    output logic [63:0] mul_a, mul_b,
    input logic mul_valid,
    output logic mul_ready,
    input logic [127:0] mul_value"""


def digest(data):
    return sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or digest(data) != expected:
        raise ValueError(f"Source pin differs: {path}")
    return data


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f"Expected one pinned anchor: {before}")
    return text.replace(before, after, 1)


def rmsnorm(text, kernel, controller):
    norm, scalar = text.split("module fixed_scalar_norm_dsp (")
    norm = replace_once(norm, "    output logic saturated,error\n);",
                        "    output logic saturated,error,\n    " + PORTS + "\n);")
    norm = replace_once(norm, ".result(scalar_result),.result_exponent(scalar_exponent),.error(scalar_error)",
                        """.result(scalar_result),.result_exponent(scalar_exponent),.error(scalar_error),
        .mul_request(mul_request),.mul_grant(mul_grant),.mul_a(mul_a),.mul_b(mul_b),
        .mul_valid(mul_valid),.mul_ready(mul_ready),.mul_value(mul_value)""")
    scalar = replace_once(scalar, "    output logic error\n);",
                          "    output logic error,\n    " + PORTS + "\n);")
    scalar = replace_once(scalar, kernel, "")
    scalar = replace_once(scalar, """    logic [63:0] multiplicand, multiplier;
    logic [79:0] product_rows[0:3];
    logic [95:0] product_halves[0:1];
    logic [127:0] product_sum;""", """    logic [63:0] multiplicand, multiplier;
    logic [127:0] product_sum;
    assign mul_request = !reset && state == MUL_STEP;
    assign mul_a = multiplicand;
    assign mul_b = multiplier;
    assign mul_ready = !reset && state == MUL_FINISH;
    assign product_sum = mul_value;""")
    scalar = replace_once(scalar, "                MUL_STEP: state<=MUL_ROWS;",
                          "                MUL_STEP: if(mul_grant) state<=MUL_ROWS;")
    scalar = replace_once(scalar, "                MUL_FINISH: begin",
                          "                MUL_FINISH: if(mul_valid) begin")

    # Reuse the tested dedicated limb kernel verbatim apart from stage enables.
    for before, after in (
        ("state==MUL_STEP", "state==IDLE && (|grant)"),
        ("state==MUL_ROWS", "state==ROWS"),
        ("state==MUL_PAIRS", "state==PAIRS"),
        ("state==MUL_REDUCE", "state==REDUCE"),
    ):
        kernel = replace_once(kernel, before, after)
    controller = replace_once(controller, "    // DSP_LIMB_DATAPATH", kernel.rstrip("\n"))
    return norm + "module fixed_scalar_norm_dsp (" + scalar + controller


def transformer(text):
    declarations = """    logic [2:0] norm_mul_request, norm_mul_grant, norm_mul_valid, norm_mul_ready;
    logic [2:0][63:0] norm_mul_a, norm_mul_b;
    logic [127:0] norm_mul_value;
"""
    marker = "    logic [4:0] n1_index,n2_index,nf_index;"
    text = replace_once(text, marker, declarations + marker)
    sharing = """    rmsnorm_shared_mul norm_mul (
        .clk(clk),.reset(reset),.request(norm_mul_request),.grant(norm_mul_grant),
        .operand_a(norm_mul_a),.operand_b(norm_mul_b),.result_valid(norm_mul_valid),
        .result_ready(norm_mul_ready),.result(norm_mul_value)
    );

"""
    marker = "    rmsnorm #(.SOURCE_EXP(-14)"
    text = replace_once(text, marker, sharing + marker)
    for index, name in enumerate(("n1", "n2", "nf")):
        text = replace_once(text, f".error({name}_error));", f""".error({name}_error),
        .mul_request(norm_mul_request[{index}]),.mul_grant(norm_mul_grant[{index}]),
        .mul_a(norm_mul_a[{index}]),.mul_b(norm_mul_b[{index}]),
        .mul_valid(norm_mul_valid[{index}]),.mul_ready(norm_mul_ready[{index}]),.mul_value(norm_mul_value));""")
    return text


def materialise(kv260, dedicated, output, candidate):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    ledger = checked(dedicated / "source-manifest.json", spec["dedicated_source_manifest_sha256"])
    sources = json.loads(ledger)
    data = {name: checked(dedicated / f"{name}.sv", pin) for name, pin in sources.items()}
    if candidate:
        data["rmsnorm"] = rmsnorm(
            data["rmsnorm"].decode(),
            checked(kv260 / KERNEL, spec["dedicated_kernel_sha256"]).decode(),
            checked(HERE / "shared_controller.svh", spec["shared_template_sha256"]).decode(),
        ).encode()
        data["transformer"] = transformer(data["transformer"].decode()).encode()
        if {name: digest(data[name]) for name in CHANGED} != spec["candidate_sources"]:
            raise ValueError("Generated shared RTL pins differ")
    output.mkdir(parents=True)
    for name, source in data.items():
        (output / f"{name}.sv").write_bytes(source)
    (output / "source-manifest.json").write_text(
        json.dumps({name: digest(source) for name, source in data.items()}, indent=2) + "\n"
    )
    return tuple(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kv260", "dedicated", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.dedicated, args.output, args.arm == "candidate")
