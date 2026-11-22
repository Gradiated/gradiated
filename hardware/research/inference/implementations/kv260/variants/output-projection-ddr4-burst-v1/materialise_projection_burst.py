"""Extend the pinned Experiment 14 DDR reader with beat and row reuse."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent


def read_checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def adapter(source):
    changes = (
        ("MAX_BURST_LENGTH 1,", "MAX_BURST_LENGTH 8,"),
        ("    logic ddr_mode, ddr_busy,", "    logic [1:0] ddr_mode_select;\n    logic ddr_mode, ddr_busy,"),
        ("    assign m_axi_arlen = 8'd0;", "    assign ddr_mode = ddr_mode_select != 0;"),
        (".request(ddr_request), .index(ddr_index), .base(ddr_base),",
         ".request(ddr_request), .index(ddr_index), .base(ddr_base), .mode(ddr_mode_select),"),
        (".araddr(m_axi_araddr), .arvalid(m_axi_arvalid)", ".araddr(m_axi_araddr), .arlen(m_axi_arlen), .arvalid(m_axi_arvalid)"),
        ("ddr_mode <= 0;", "ddr_mode_select <= 0;"),
        ("ddr_mode <= write_data[0];", "ddr_mode_select <= write_data[1:0];"),
        ("write_data[2:0]==0", "write_data[5:0]==0"),
        ("(write_data==1 && ddr_base!=0", "(write_data<=3 && ddr_base!=0"),
        ("{27'd0,counter_full,(!ddr_mode", "{25'd0,ddr_mode_select,counter_full,(!ddr_mode"),
        ("32'h44445231;", "32'h44445232;"),
    )
    for before, after in changes:
        if source.count(before) != 1:
            raise ValueError(f"Unexpected adopted adapter: {before}")
        source = source.replace(before, after)
    return source


def materialise(kv260, output):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    previous = kv260 / "variants/output-projection-ddr4-v1"
    generator = previous / "materialise_projection_ddr.py"
    read_checked(generator, spec["previous_generator_sha256"])
    read_checked(previous / "manifest.json", spec["previous_manifest_sha256"])
    runpy.run_path(str(generator))["materialise"](kv260, output)
    ledger = output / "source-manifest.json"
    prior = json.loads(read_checked(ledger, spec["previous_closure_sha256"]))
    inner = output / "axi_transformer.sv"
    original = read_checked(inner, prior["axi_transformer"]).decode()
    replacements = {
        "axi_transformer": adapter(original).encode(),
        "projection_ddr_reader": read_checked(HERE / "projection_ddr_reader.sv", spec["reader_sha256"]),
    }
    for name, data in replacements.items():
        pin = sha256(data).hexdigest()
        if pin != spec["fixture_sources"][name]:
            raise ValueError(f"Generated fixture source changed: {name}")
        (output / f"{name}.sv").write_bytes(data)
        prior[name] = pin
    ledger.write_text(json.dumps(prior, indent=2) + "\n")
    return tuple(prior)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output)
