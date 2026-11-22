"""Generate the pinned serialized or double-buffered DDR logits RTL."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin differs: {path}")
    return data


def transformer(source, substitute):
    return substitute(source,
        ("    assign result_valid = state == STREAM;",
         "    assign result_valid = state == STREAM && !fetch_fault;"),
        ("    assign fetch_request = state == PRIME && !reset;",
         "    assign fetch_request = busy && !reset && !fetch_fault;"),
        ("    assign fetch_wait = fetch_request && !fetch_valid && !fetch_fault;",
         "    assign fetch_wait = state == PRIME && fetch_request && !fetch_valid;"),
        ("    assign mac_active = state == MAC && !reset;",
         "    assign mac_active = state == MAC && !reset && !fetch_fault;"),
        ("    assign read_pair = (state == PRIME && fetch_valid) || advance_mac;",
         "    assign read_pair = !fetch_fault && ((state == PRIME && fetch_valid) || advance_mac);"),
        ("            case (state)\n                IDLE: if (launch)",
         "            if (fetch_fault) state <= IDLE;\n            else case (state)\n                IDLE: if (launch)"),
        ("                PRIME: if (fetch_fault) state <= IDLE;\n                       else if (fetch_valid) state <= MAC;",
         "                PRIME: if (fetch_valid) state <= MAC;"))


def materialise(kv260, output, candidate):
    spec = json.loads((HERE/"manifest.json").read_bytes())
    serial = kv260/"variants/logits-ddr4-burst-v1"
    generator = serial/"materialise_logits_ddr.py"
    checked(generator, spec["serial_generator_sha256"])
    checked(serial/"manifest.json", spec["serial_manifest_sha256"])
    baseline = runpy.run_path(str(generator))
    baseline["materialise"](kv260, output, True)
    ledger = output/"source-manifest.json"
    hashes = json.loads(checked(ledger, spec["control_closure_sha256"]))
    if candidate:
        source = checked(output/"transformer.sv", hashes["transformer"]).decode()
        changed = {
            "transformer": transformer(source, baseline["substitute"]).encode(),
            "logits_group_reader": checked(HERE/"logits_group_reader.sv", spec["reader_sha256"]),
        }
        for name, data in changed.items():
            pin = sha256(data).hexdigest()
            if pin != spec["candidate_sources"][name]:
                raise ValueError(f"Generated source changed: {name}")
            (output/f"{name}.sv").write_bytes(data)
            hashes[name] = pin
        ledger.write_text(json.dumps(hashes, indent=2)+"\n")
        checked(ledger, spec["candidate_closure_sha256"])
    return tuple(hashes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "candidate"), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.arm == "candidate")
