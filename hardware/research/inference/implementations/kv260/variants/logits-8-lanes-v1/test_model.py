"""Run the pinned component and full-model checks for four and eight lanes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
import time

from materialise_eight import HERE, PINS, PREVIOUS, materialise, pinned


PROJECTION_CYCLES = {4: 3040, 8: 1680}


def load_previous(kv260):
    root = kv260 / PREVIOUS
    for name in ("test_lanes.py", "materialise_lanes.py", "logits_lanes_tb.sv"):
        pinned(root / name, PINS[name])
    sys.path.insert(0, str(root))
    try:
        return runpy.run_path(str(root / "test_lanes.py"))
    finally:
        sys.path.pop(0)


def component(verilator, rtl, root, bench, lanes, env, run, deadline):
    fixture = root / "fixtures/component"
    binary = root / "obj-component/simulation"
    run([str(verilator), "--binary", "--timing", "--assert", "-Wno-fatal",
         "--top-module", "logits_lanes_tb", f"-GLANES={lanes}", "-j", "2",
         "--Mdir", str(binary.parent), "-o", "simulation", str(rtl / "transformer.sv"), str(bench)],
        root, env, root / "component-compile.log", 150, deadline)
    run([str(binary), "+FIXTURES=" + str(fixture)],
        root, env, root / "component.log", 60, deadline)
    print(f"{lanes} lanes passed all signed component checks", flush=True)


def simulate_arm(args, previous, helpers, oracle, root, lanes, deadline):
    root.mkdir()
    fixtures = root / "fixtures"
    previous["archived_fixtures"](args.archive, fixtures)
    previous["check_arithmetic_fixtures"](fixtures / "component")
    rtl = root / "rtl"
    names = materialise(args.kv260, rtl, lanes)
    verilator = args.verilator / "bin/verilator"
    env = helpers["simulator"](args.verilator, args.kv260)
    run = helpers["run"]
    component(verilator, rtl, root, args.kv260 / PREVIOUS / "logits_lanes_tb.sv", lanes, env, run, deadline)

    model = fixtures / "model"
    reference = model / "reference"
    full_bench = root / "autonomous_core_tb.sv"
    full_bench.write_text(oracle["instrument"]((reference / full_bench.name).read_text()))
    binary = root / "obj-model/simulation"
    run([str(verilator), "--binary", "--timing", "--assert", "-Wno-fatal",
         "--top-module", "autonomous_core_tb", "-j", "2", "--Mdir", str(binary.parent),
         "-o", "simulation", *[str(rtl / (name + ".sv")) for name in names], str(full_bench)],
        root, env, root / "compile.log", 150, deadline)

    frozen = json.loads((model / "result.json").read_bytes())
    observed = {}
    for label in previous["CASES"]:
        path = root / label
        path.mkdir()
        case, cap_text = label.rsplit("-cap", 1)
        cap = int(cap_text)
        archive = frozen[label]
        row = archive["candidate"]
        suite = reference / label
        params = {
            "MODEL": reference / "model.hex", "SCORES": reference / "bos.hex", "CSV": path / "bus.events",
            "RETURNS": path / "bos.csv", "INPUT": suite / "input.hex", "OUTPUT": suite / "output.hex",
            "ALLSCORES": suite / "scores.hex", "PREFIX": row["prefix"]["positions"],
            "OUTPUTS": archive["outputs"], "POSITIONS": row["done"]["positions"],
            "CAP": cap, "REASON": 1 if cap == 255 else 2 if case == "full-context" else 4,
            "SKIP": 1, "CACHE": path / "cache.kv", "PHASE": path / "phases.txt",
        }
        run([str(binary), *[f"+{key}={value}" for key, value in params.items()]],
            root, env, path / "simulation.log", 600, deadline)
        expected = helpers["boundaries"](model / "candidate" / label / "cache.kv")
        captured = helpers["boundaries"](params["CACHE"])
        phases = oracle["read_phases"](params["PHASE"])
        if set(expected) != set(captured) or set(expected) != set(phases):
            raise ValueError(f"Missing exact cache or phase boundary: {label}")
        for boundary, actual in captured.items():
            reference_data = expected[boundary]
            if any(actual[key] != reference_data[key] for key in ("kv", "positions")):
                raise ValueError(f"Exact cache mismatch: {label} {boundary}")
            phases[boundary].update(positions=actual["positions"], cycles=actual["cycles"])
        observed[label] = dict(outputs=archive["outputs"], **phases)
        print(f"{lanes} {label}: {phases['done']['cycles']} clocks", flush=True)
    (root / "result.json").write_text(json.dumps(observed, indent=2) + "\n")
    return observed


def compare(control, candidate):
    saving = PROJECTION_CYCLES[4] - PROJECTION_CYCLES[8]
    if control.keys() != candidate.keys():
        raise ValueError("Case labels differ")
    for label, before in control.items():
        after = candidate[label]
        outputs = before["outputs"]
        if outputs != after["outputs"] or before["prefix"] != after["prefix"]:
            raise ValueError(f"Output geometry or pre-projection prefix differs: {label}")
        a, b = before["done"], after["done"]
        positions = a["positions"] - before["prefix"]["positions"] + 1
        if a["positions"] != b["positions"] or a["first_valid"] != b["first_valid"]:
            raise ValueError(f"Done position or validity differs: {label}")
        deltas = {"first": saving if outputs else 0, "last": outputs * saving,
                  "done": positions * saving, "cycles": positions * saving}
        if any(a[key] - b[key] != value for key, value in deltas.items()):
            raise ValueError(f"First, last or terminal cycle law differs: {label}")
        if any(a["phases"][18] != positions * PROJECTION_CYCLES[lanes]
               for lanes, a in ((4, a), (8, b))):
            raise ValueError(f"Projection phase count differs: {label}")
        untouched_before = a["phases"][:18] + a["phases"][19:]
        untouched_after = b["phases"][:18] + b["phases"][19:]
        if untouched_before != untouched_after:
            raise ValueError(f"Another phase changed: {label}")


def main(args):
    manifest = json.loads((HERE / "manifest.json").read_bytes())
    previous_four = json.loads(pinned(args.previous_replay, manifest["matched_four_lane_replay_sha256"]))["4"]
    pinned(args.archive, manifest["exact_score_fixture_archive_sha256"])
    previous = load_previous(args.kv260)
    oracle, helpers = previous["verified_helpers"](args.kv260)
    deadline = time.monotonic() + min(1500, args.deadline_epoch - time.time())
    args.output.mkdir()
    control = simulate_arm(args, previous, helpers, oracle, args.output / "4", 4, deadline)
    if control != previous_four:
        raise ValueError("Four-lane replay differs from the archived control")
    candidate = simulate_arm(args, previous, helpers, oracle, args.output / "8", 8, deadline)
    compare(control, candidate)
    results = {"4": control, "8": candidate}
    encoded = (json.dumps(results, indent=2, sort_keys=True) + "\n").encode()
    (args.output / "matched.json").write_bytes(encoded)
    print("Both arms passed all seven cases.", sha256(encoded).hexdigest(), flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("kv260", "verilator", "archive", "previous-replay", "output"):
        cli.add_argument("--" + arg, type=lambda value: Path(value).resolve(), required=True)
    cli.add_argument("--deadline-epoch", type=float, required=True)
    main(cli.parse_args())
