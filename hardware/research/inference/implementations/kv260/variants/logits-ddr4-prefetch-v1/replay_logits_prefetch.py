"""Replay the exact serialized and prefetched DDR logits against the same frozen oracle."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
import time

HERE = Path(__file__).resolve().parent
SAVED = 39 * 41
SERIAL_EXTRA = 7040
CANDIDATE_EXTRA = SERIAL_EXTRA - SAVED
ORIGINAL_CLOCKS = 1680
SERIAL_PROFILE = [320, 2560, SERIAL_EXTRA, 320, 3840, ORIGINAL_CLOCKS + SERIAL_EXTRA]
PREFETCH_PROFILE = [320, 2560, CANDIDATE_EXTRA, 320, 3840, ORIGINAL_CLOCKS + CANDIDATE_EXTRA]
SERIAL_OVERLAP = [7080, 0, 0, 40, 40, 0, 0]
PREFETCH_OVERLAP = [7080, 39 * 32, 39 * 9, 40, 40, 39 * 13, 39 * 4]


def bench(prior, serial, replace_once, candidate):
    base = serial["bench"](prior, replace_once, True)
    overlap = (HERE/"observe_overlap.svh").read_text()
    replacements = (
        ("    axi_transformer dut (.*);", overlap+"\n    axi_transformer dut (.*);"),
    )
    if candidate:
        replacements += (
            ("(dut.ddr_mode && (!dut.ddr_request || dut.ddr_group != 6'(burst_index/8)))",
             """(dut.ddr_mode && !dut.ddr_fault && (!dut.ddr_request ||
                   dut.projection_reader.next_fetch_group != 6'(burst_index/8) ||
                   dut.ddr_group > 6'(burst_index/8) || dut.ddr_group+6'd1 < 6'(burst_index/8)))"""),
            ("32'(7040*logit_starts)", f"32'({CANDIDATE_EXTRA}*logit_starts)"),
            ("32'(8720*logit_starts)", f"32'({ORIGINAL_CLOCKS+CANDIDATE_EXTRA}*logit_starts)"),
            ("    assign fetch_launch = dut.ddr_request && !dut.ddr_busy;",
             "    assign fetch_launch = dut.projection_reader.start_fetch;"),
            ("    task automatic await_transport(input bit return_phase);",
             (HERE/"prefetch_fault_cases.svh").read_text()+"\n    task automatic await_transport(input bit return_phase);"),
            ('if ($value$plusargs("FAULT=%d",injected_fault) && injected_fault!=0) qualify_fault();',
             '''if ($value$plusargs("FAULT=%d",injected_fault) && injected_fault!=0) begin
            if (injected_fault>=10) qualify_prefetch_fault();
            else qualify_fault();
        end'''),
        )
    for start, end in replacements:
        base = replace_once(base, start, end)
    return base


def audit(folder, reference_folder, case, ref, parser, candidate):
    assert (folder/"bos.csv").read_bytes() == (reference_folder/case/"bos.csv").read_bytes()
    timing = parser["get_phases"](folder/"phases.txt")
    cache = parser["cache"](folder/"cache.kv")
    expected_cache = parser["cache"](reference_folder/case/"cache.kv")
    invocations = ref["done"]["positions"] - ref["prefix"]["positions"] + 1
    extra = CANDIDATE_EXTRA if candidate else SERIAL_EXTRA
    for name, boundary in timing.items():
        anchor = ref[name]
        n, cycles, vector = cache[name]
        assert n == expected_cache[name][0] == anchor["positions"]
        assert vector == expected_cache[name][2]
        added = invocations*extra if name=="done" else 0
        assert cycles == anchor["cycles"]+added
        assert boundary["first_valid"] == anchor["first_valid"]
        assert boundary["first"] == anchor["first"]+(extra if anchor["first_valid"] else 0)
        assert boundary["last"] == anchor["last"]+(ref["outputs"]*extra if anchor["first_valid"] else 0)
        assert boundary["done"] == anchor["done"]+added
        assert boundary["phases"] == [old+(added if index==18 else 0)
                                      for index, old in enumerate(anchor["phases"])], (case,name)
        boundary.update(positions=n, cycles=cycles)
    actual = [list(map(int, line.split())) for line in (folder/"ddr-profile.txt").read_text().splitlines()]
    profile = PREFETCH_PROFILE if candidate else SERIAL_PROFILE
    assert actual == [[index, *profile] for index in range(1, invocations+1)], (case, actual[:2])
    overlap = [list(map(int, line.split())) for line in (folder/"overlap.txt").read_text().splitlines()]
    expected = PREFETCH_OVERLAP if candidate else SERIAL_OVERLAP
    assert overlap == [[index, *expected] for index in range(1, invocations+1)], (case, overlap[:2])
    work, mac, other, captures, coincident_captures, _, _ = expected
    assert work - extra - captures == mac + other + coincident_captures - captures
    return timing


def main(args):
    start = time.monotonic()
    deadline = start+1500
    kv = args.kv260
    fixture = runpy.run_path(str(kv/"variants/output-projection-ddr4-burst-v1/replay_projection_burst.py"))
    parser = runpy.run_path(str(kv/"variants/attention-exp-pair-v2/replay_pair.py"))
    serial = runpy.run_path(str(kv/"variants/logits-ddr4-burst-v1/replay_logits_ddr.py"))
    model = kv/"variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0, str(model.parent))
    try:
        measure = runpy.run_path(str(model))
    finally:
        sys.path.pop(0)
    run = measure["run"]
    env = measure["simulator"](args.verilator, kv)
    args.output.mkdir()
    prior, oracle = fixture["previous_run"](args.previous, args.output/"reference")
    matrix = args.output/"logits.hex"
    results = {"matrix_sha256": serial["packed_weights"](oracle,matrix)}
    cases = json.loads((prior/"matched.json").read_text())["candidate"]
    spec = json.loads((HERE/"manifest.json").read_text())
    for arm, rtl in (("control", args.control), ("candidate", args.candidate)):
        folder = args.output/arm
        folder.mkdir()
        ledger = rtl/"source-manifest.json"
        pins = json.loads(ledger.read_bytes())
        candidate = arm=="candidate"
        field = "candidate_closure_sha256" if candidate else "control_closure_sha256"
        assert sha256(ledger.read_bytes()).hexdigest() == spec[field]
        sources = [rtl/(name+".sv") for name in pins]
        assert all(sha256(f.read_bytes()).hexdigest() == pins[f.stem] for f in sources)
        testbench = folder/"autonomous_core_tb.sv"
        testbench.write_text(bench(prior, serial, fixture["replace_once"], candidate))
        exe = folder/"obj/simulation"
        run([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "2",
             "--top-module", "autonomous_core_tb", "--Mdir", str(exe.parent), "-o", "simulation",
             *map(str, sources), str(testbench)], folder, env, folder/"compile.log", 300, deadline)
        results[arm] = {}
        trials = [(case, case, 0, 0) for case in cases]
        if candidate:
            trials.extend((f"fault-{fault}", "bos-only-cap0", fault, 0) for fault in range(1, 13))
            trials.append(("perturb", "bos-only-cap0", 0, 1))
        for name, case, fault, perturb in trials:
            ref = cases[case]
            out = folder/name
            out.mkdir()
            cap = int(case.rsplit("-cap",1)[1])
            params = dict(MODEL=oracle/"model.hex", SCORES=oracle/"bos.hex", INPUT=oracle/case/"input.hex",
                          OUTPUT=oracle/case/"output.hex", ALLSCORES=oracle/case/"scores.hex",
                          CSV=out/"bus.events", RETURNS=out/"bos.csv", PREFIX=ref["prefix"]["positions"],
                          OUTPUTS=ref["outputs"], POSITIONS=ref["done"]["positions"], CAP=cap, SKIP=1,
                          CACHE=out/"cache.kv", PHASE=out/"phases.txt",
                          REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4,
                          MATRIX=matrix, FAULT=fault, PERTURB=perturb)
            log = out/"simulation.log"
            run([str(exe), *[f"+{key}={value}" for key,value in params.items()]], out, env, log, 180, deadline)
            passed = next(line for line in log.read_text().splitlines() if line.startswith("PASS"))
            if fault or perturb:
                assert ("fault or cancel" if fault else "independent tied-weight perturbation") in passed
                results[arm][name] = passed
            else:
                assert "autonomous_real_core" in passed
                results[arm][name] = audit(out, prior, case, ref, parser, candidate)
            print(arm, name, passed, flush=True)
    arithmetic = args.output/"arithmetic"
    serial["directed_fixture"](arithmetic)
    exe = arithmetic/"obj/simulation"
    run([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "2",
         "--top-module", "logits_arithmetic_tb", "--Mdir", str(exe.parent), "-o", "simulation",
         str(args.candidate/"transformer.sv"), str(args.candidate/"logits_group_reader.sv"),
         str(HERE/"logits_arithmetic_tb.sv")], arithmetic, env, arithmetic/"compile.log", 180, deadline)
    log = arithmetic/"simulation.log"
    run([str(exe), f"+FIXTURE={arithmetic}"], arithmetic, env, log, 90, deadline)
    results["arithmetic"] = next(line for line in log.read_text().splitlines()
                                 if line.startswith("PASS directed logits arithmetic"))
    print(results["arithmetic"], flush=True)
    (args.output/"matched.json").write_text(json.dumps(results,indent=2)+"\n")
    print(f"Exact replay completed in {time.monotonic()-start:.2f}s")


if __name__=="__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("kv260", "verilator", "previous", "control", "candidate", "output"):
        p.add_argument("--"+name, type=lambda value: Path(value).resolve(), required=True)
    main(p.parse_args())
