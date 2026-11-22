"""Run the signed component oracle and the seven exact matched model cases."""

import argparse
import json
from pathlib import Path
import runpy
import sys
import time

from fixtures import write_fixtures
from materialise_ff_exp import HERE, materialise, pinned


PROFILE = "diagnostics/feed-forward-profile-v1"
PROFILE_PINS = {
    "replay.py": "320a93446fff019687e32d71831c733d0b5d401317bcfa919e28a6aeed9e7467",
    "analyse.py": "511e51ecc71d9f45116c52599d071717a6448e8a9af5b0393992f6b9df054a0c",
}
EXPECTED_SAVING = 9344


def previous_replay(kv260):
    root = kv260 / PROFILE
    for name, expected in PROFILE_PINS.items():
        pinned(root / name, expected)
    sys.path.insert(0, str(root))
    try:
        return runpy.run_path(str(root / "replay.py"))
    finally:
        sys.path.pop(0)


def compile_bench(args, root, helper, env, sources, bench, top, deadline):
    binary = root / "simulation"
    helper["run"](
        [str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
         "--top-module", top, "-j", "2", "--Mdir", str(root), "-o", binary.name,
         *map(str, sources), str(bench)],
        root.parent, env, root.parent / (root.name + "-compile.log"), 150, deadline,
    )
    return binary


def component(args, root, helper, env, deadline):
    component_root = root / "component"
    component_root.mkdir()
    counts = write_fixtures(component_root)
    feed = root / "candidate/rtl/feedforward.sv"
    control = root / "control/rtl/fixed_scalar.sv"
    binary = compile_bench(args, component_root / "obj", helper, env, (control, feed),
                           HERE / "scalar_tb.sv", "ff_exp_scalar_tb", deadline)
    helper["run"]([str(binary), "+FIXTURES=" + str(component_root),
                   f"+RAW_ROWS={counts['raw.hex']}", f"+INTERFACE_ROWS={counts['interface.hex']}"],
                  component_root, env, component_root / "simulation.log", 120, deadline)
    (component_root / "counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    print("Signed component cases passed.", counts, flush=True)


def read_phases(path):
    rows = {}
    for line in path.read_text().splitlines():
        name, *values = line.split()
        valid, first, last, done, *ticks = map(int, values)
        if name in rows or len(ticks) != 21:
            raise ValueError("Unexpected phase counter shape")
        rows[name] = dict(first_valid=bool(valid), first=first, last=last, done=done, phases=ticks)
    if rows.keys() != {"prefix", "done"}:
        raise ValueError("Missing archived boundary")
    return rows


def model(args, root, reference, previous, helper, env, candidate, names, deadline):
    arm = ("control", "candidate")[candidate]
    binary = compile_bench(args, root / "obj-model", helper, env,
                           [root / "rtl" / (name + ".sv") for name in names],
                           reference / "autonomous_core_tb.sv", "autonomous_core_tb", deadline)
    results = {}
    oracle = reference / "fixtures/model/reference"
    for label, old in previous.items():
        path = root / label
        path.mkdir()
        case, limit = label.rsplit("-cap", 1)
        cap = int(limit)
        params = dict(
            MODEL=oracle / "model.hex", SCORES=oracle / "bos.hex", CSV=path / "bus.events",
            RETURNS=path / "bos.csv", INPUT=oracle / label / "input.hex", OUTPUT=oracle / label / "output.hex",
            ALLSCORES=oracle / label / "scores.hex", PREFIX=old["prefix"]["positions"], OUTPUTS=old["outputs"],
            POSITIONS=old["done"]["positions"], CAP=cap, REASON=1 if cap == 255 else 2 if case == "full-context" else 4,
            SKIP=1, CACHE=path / "cache.kv", PHASE=path / "phases.txt",
        )
        helper["run"]([str(binary), *[f"+{key}={value}" for key, value in params.items()]],
                      path, env, path / "simulation.log", 120, deadline)
        if not candidate:
            for name in ("bos.csv", "bus.events", "cache.kv", "phases.txt"):
                if (path / name).read_bytes() != (reference / label / name).read_bytes():
                    raise ValueError(f"Exact control parity failed: {label}/{name}")
        archive_cache = helper["boundaries"](reference / label / "cache.kv")
        cache = helper["boundaries"](params["CACHE"])
        phases = read_phases(params["PHASE"])
        if set(archive_cache) != set(cache) or set(cache) != set(phases):
            raise ValueError(f"Unexpected boundaries: {label}")
        for boundary, items in cache.items():
            if any(archive_cache[boundary][key] != items[key] for key in ("positions", "kv")):
                raise ValueError(f"Exact cache values or position geometry changed: {label}/{boundary}")
            phases[boundary].update(positions=items["positions"], cycles=items["cycles"])
        results[label] = dict(outputs=old["outputs"], **phases)
        print(arm, label, phases["done"]["done"], "clocks", flush=True)
    (root / "result.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    return results


def compare(control, candidate):
    if control.keys() != candidate.keys():
        raise ValueError("Matched model case labels differ")
    for label, a in control.items():
        b = candidate[label]
        if a["outputs"] != b["outputs"]:
            raise ValueError(f"Outputs changed: {label}")
        prefix = a["prefix"]["positions"]
        emitted = a["outputs"]
        for boundary in ("prefix", "done"):
            left, right = a[boundary], b[boundary]
            cycles = left["positions"] * EXPECTED_SAVING
            expected = {
                "prefix": dict(first=0, last=0, done=0, cycles=cycles),
                "done": dict(first=prefix * EXPECTED_SAVING if emitted else 0,
                             last=(prefix + emitted - 1) * EXPECTED_SAVING if emitted else 0,
                             done=cycles, cycles=cycles),
            }[boundary]
            if any(left[key] != right[key] for key in ("positions", "first_valid")):
                raise ValueError(f"Boundary geometry differs: {label}/{boundary}")
            if any(left[key] - right[key] != delta for key, delta in expected.items()):
                raise ValueError(f"Exact boundary cycle law differs: {label}/{boundary}")
            for index, (start, finish) in enumerate(zip(left["phases"], right["phases"], strict=True)):
                if start - finish != (cycles if index == 14 else 0):
                    raise ValueError(f"Unexpected model phase change: {label}/{boundary} phase {index}")


def main(args):
    deadline = time.monotonic() + min(1100, args.deadline_epoch - time.time())
    kv260 = args.repo / "hardware/research/inference/implementations/kv260"
    prior = previous_replay(kv260)
    raw = args.repo / ".agents/runtime/hardware/inference/outputs" / prior["BASELINE"]
    for name, expected in prior["BASE_PINS"].items():
        pinned(raw / name, expected)
    previous = json.loads((raw / "model-results.json").read_bytes())["8"]
    previous = {label: previous[label] for label in prior["CASE_NAMES"]}
    helper = prior["load_helper"](kv260)
    env = helper["simulator"](args.verilator, kv260)
    root = args.output
    root.mkdir()
    names = []
    for candidate in (False, True):
        arm = ("control", "candidate")[candidate]
        (root / arm).mkdir()
        names = materialise(kv260, root / arm / "rtl", candidate)
    updated = [name for name in names if (root / "control/rtl" / (name + ".sv")).read_bytes()
               != (root / "candidate/rtl" / (name + ".sv")).read_bytes()]
    if updated != ["feedforward"]:
        raise ValueError("Exact RTL scope differs")
    reference = root / "pinned"
    prior["extract_inputs"](raw / "simulation.tar.gz", reference, json.loads((raw / "source-closure.json").read_bytes()))
    component(args, root, helper, env, deadline)
    control = model(args, root / "control", reference, previous, helper, env, False, names, deadline)
    if control != previous:
        raise ValueError("Reconstructed control differs from prior measurement")
    candidate = model(args, root / "candidate", reference, previous, helper, env, True, names, deadline)
    compare(control, candidate)
    (root / "matched.json").write_text(json.dumps({"control": control, "candidate": candidate}, indent=2, sort_keys=True) + "\n")
    print("Exact seven-case matched replay passed. Only FF_WAIT changed.", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "verilator", "output"):
        cli.add_argument("--" + arg, type=lambda value: Path(value).resolve(), required=True)
    cli.add_argument("--deadline-epoch", type=float, required=True)
    main(cli.parse_args())
