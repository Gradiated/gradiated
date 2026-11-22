"""Generate the exact four-lane control or its eight-lane specialisation."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
PREVIOUS = "variants/logits-lanes-v1"
CONTROL = "b47ac0197e576fcfbc3397ce2e11e2b2df6d500efd92a1e4b404dfc86a12c56e"
PINS = {
    "materialise_lanes.py": "9275aaf4eb83a43d57a1cd5e1312bdb25ec4f79a788c8a666ca1e1331ae35bd2",
    "manifest.json": "84589f6f6dae2b4f60700881464710c55cab5572a74f152ce400b2dc32839b2d",
    "test_lanes.py": "cb402b29311e896b23438760f9d1812923c7c7283d2eea85f19914a530fc8484",
    "logits_lanes_tb.sv": "049876395830934473d67ef706cf566b56e7372de92dd28e9457eada39a781d2",
}


def pinned(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Source changed: {path}")
    return data


def materialise(kv260, output, lanes):
    if lanes not in (4, 8):
        raise ValueError("Expected four or eight lanes")
    previous = kv260 / PREVIOUS
    for name in ("materialise_lanes.py", "manifest.json"):
        pinned(previous / name, PINS[name])
    names = runpy.run_path(str(previous / "materialise_lanes.py"))["materialise"](kv260, output, 4)
    transformer = output / "transformer.sv"
    control = pinned(transformer, CONTROL)
    if lanes == 8:
        before = b"logits_parallel #(.LANES(4)) logits ("
        if control.count(before) != 1:
            raise ValueError("Expected one four-lane projection")
        candidate = control.replace(before, b"logits_parallel #(.LANES(8)) logits (", 1)
        expected = json.loads((HERE / "manifest.json").read_bytes())["candidate_transformer_sha256"]
        if sha256(candidate).hexdigest() != expected:
            raise ValueError("Candidate transformer closure changed")
        transformer.write_bytes(candidate)
        manifest = output / "source-manifest.json"
        sources = json.loads(manifest.read_bytes())
        sources["transformer"] = expected
        manifest.write_text(json.dumps(sources, indent=2) + "\n")
    return names


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lanes", type=int, choices=(4, 8), required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output, args.lanes)
