"""Run the exact arithmetic gate and the seven pinned attention model replays."""

import argparse
import json
from pathlib import Path
from hashlib import sha256
import runpy
import sys
import time

from materialise_attention_exp import CACHE, FF, HERE, checked, materialise
from predict import CACHE_RUN, ROOT, predict


def prior_module(path):
    sys.path.insert(0, str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def compile_bench(args, work, rtl, bench, top, model, env, deadline):
    binary = work / "obj/simulation"
    model["run"]([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert",
                  "-Wno-fatal", "-j", "2", "--top-module", top, "--Mdir", str(binary.parent),
                  "-o", "simulation", *map(str, rtl), str(bench)],
                 work, env, work/"compile.log", 150, deadline)
    return binary


def scalar_cases(args, work, candidate, kv260, spec, model, env, deadline):
    work.mkdir()
    fixture_source = checked(kv260/FF/"fixtures.py", spec["scalar_fixtures_sha256"]).decode()
    # Exercise the arithmetic helper beyond the separately checked table interface.
    bound = "(1 << 31) * (DIVISOR - 1)"
    fixture_source = fixture_source.replace(bound, "((1 << 32) - 1) * (DIVISOR - 1)")
    fixture = {}
    exec(compile(fixture_source, "fixtures.py", "exec"), fixture)
    counts = fixture["write_fixtures"](work)
    bench = work/"scalar_tb.sv"
    source = checked(kv260/FF/"scalar_tb.sv", spec["scalar_bench_sha256"]).decode()
    marker = '        fd=$fopen({fixtures,"/interface.hex"},"r");'
    reject = """        @(negedge clk);
        table_valid=1; table_index=0; table_value=32'h8000_0001;
        #1;
        if (table_ready[0] || table_ready[1]) $fatal(1,"Out-of-range table word accepted");
        tick();
        @(negedge clk); table_value=32'hffff_ffff;
        #1;
        if (table_ready[0] || table_ready[1]) $fatal(1,"Out-of-range table word accepted");
        tick();
        if (control.exp_loaded[0] || candidate.exp_loaded[0]) $fatal(1,"Rejected table word mutated state");
        @(negedge clk); table_valid=0;

"""
    if source.count(marker) != 1:
        raise ValueError("Unexpected table-test insertion point")
    bench.write_text(source.replace(marker, reject+marker, 1)
                     .replace("fixed_scalar_ff_exp", "fixed_scalar_attention_exp"))
    binary = compile_bench(args, work, [candidate/"fixed_scalar.sv", candidate/"attention.sv"],
                           bench, "ff_exp_scalar_tb", model, env, deadline)
    model["run"]([str(binary), f"+FIXTURES={work}", f"+RAW_ROWS={counts['raw.hex']}",
                  f"+INTERFACE_ROWS={counts['interface.hex']}"],
                 work, env, work/"simulation.log", 120, deadline)
    if "PASS exact quotient/remainder" not in (work/"simulation.log").read_text():
        raise ValueError("Arithmetic fixture pass receipt missing")
    (work/"counts.json").write_text(json.dumps(counts, indent=2)+"\n")
    print("Signed divider and full-width EXP tables passed", counts, flush=True)


def main(args):
    deadline = time.monotonic() + min(1100, args.deadline_epoch - time.time())
    kv260 = args.repo/"hardware/research/inference/implementations/kv260"
    spec = json.loads((HERE/"manifest.json").read_bytes())
    old = prior_module(kv260/CACHE/"test_experiment.py")
    diag_path = kv260/"diagnostics/attention-profile-v1/replay.py"
    checked(diag_path, spec["diagnostic_replay_sha256"])
    diag = prior_module(diag_path)
    raw = args.repo / ROOT / diag["BASELINE"]
    for name, pin in diag["BASE_PINS"].items():
        checked(raw/name, pin)
    reference = args.repo / ROOT / CACHE_RUN / "model-results.json"
    baseline = json.loads(checked(reference, spec["control_replay_sha256"]))["candidate"]
    prediction = json.loads(checked(HERE/"predictions.json", spec["predictions_sha256"]))
    if predict(args.repo, checked, spec) != prediction:
        raise ValueError("Prediction regeneration differs")
    model = diag["helper"](kv260)
    env = model["simulator"](args.verilator, kv260)
    work = args.output
    work.mkdir()
    reference_names = diag["extract"](raw, work/"pinned")
    control, candidate = work/"control", work/"candidate"
    control.mkdir()
    candidate.mkdir()
    assert set(materialise(kv260, control/"rtl", False)) == set(reference_names)
    assert set(materialise(kv260, candidate/"rtl", True)) == set(reference_names)
    changed = [name for name in reference_names
               if (control/"rtl"/(name+".sv")).read_bytes() != (candidate/"rtl"/(name+".sv")).read_bytes()]
    if changed != ["attention"]:
        raise ValueError("The candidate changed more than the attention RTL")
    deltas = prediction["cases"]
    scalar_cases(args, work/"scalar", candidate/"rtl", kv260, spec, model, env, deadline)
    original = (work/"pinned/oracle/autonomous_core_tb.sv").read_text()
    bench = candidate/"autonomous_core_tb.sv"
    cache_monitor = checked(kv260/CACHE/"monitor.svh", spec["cache_monitor_sha256"]).decode()
    bench.write_text(old["once"](original, "endmodule",
                                 cache_monitor+"\n"+(HERE/"monitor.svh").read_text()+"\nendmodule"))
    binary = compile_bench(args, candidate, [candidate/"rtl"/(name+".sv") for name in reference_names],
                           bench, "autonomous_core_tb", model, env, deadline)
    results = {}
    for name, row in baseline.items():
        forecast = deltas[name]
        results[name] = old["model_case"](name, row, forecast, args, work, model, env, binary, deadline)
        path = candidate/name/"attention-divider.txt"
        counters = [list(map(int, line.split())) for line in path.read_text().splitlines()]
        expected = [[length, full, 23*full, 64*length]
                    for length, full in enumerate(forecast["full_exponentials"], 1)]
        if counters != expected:
            raise ValueError(f"Exact divider schedule or probability counts changed: {name}")
    (work/"matched.json").write_text(json.dumps({"control": baseline, "candidate": results},
                                               indent=2, sort_keys=True)+"\n")
    print("Exact seven-case model replay, cache schedules and divider counts passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("repo", "verilator", "output"):
        parser.add_argument("--"+key, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    main(parser.parse_args())
