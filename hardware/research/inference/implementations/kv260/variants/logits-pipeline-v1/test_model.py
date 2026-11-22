"""Replay both full RTL arms against the exact scalar-div reference."""

import argparse
import json
from pathlib import Path
import runpy
import tarfile
import time

from materialise import BASE_GENERATOR, materialise, pin, replace

ARCHIVE = "16c04aaa765e7785cd62ceb4991cec16795813860529cca810361078330fc7fa"
DIV_TEST = "c9521eecf894f99931eaaa8000690aefb392fe8778bcae335bbee33ca54f6902"
REFERENCE = "candidate/model-sim"
PROJECTION_CLOCKS = (32 - 1) * 320


def instrument(bench):
    bench = replace(bench, "    task automatic dump_cache", """    integer phase_ticks[21];
    integer phase_log;
    string phase_path;
    task automatic dump_cache""")
    bench = replace(bench, "        count=int'(dut.core_context_count);", """        $fwrite(phase_log,"%s %0d %0d %0d %0d",boundary,
            dut.first_valid,dut.first_cycles,dut.last_cycles,dut.done_cycles);
        foreach(phase_ticks[p]) $fwrite(phase_log," %0d",phase_ticks[p]);
        $fwrite(phase_log,"\\n");
        count=int'(dut.core_context_count);""")
    bench = replace(bench, "            seen_scores=seen_scores+1;\n        end",
                    """            seen_scores=seen_scores+1;
        end
        if(seen_inputs>0 && !done_recorded)begin
            if(int'(dut.core_phase)>=21) $fatal(1,"Unexpected core phase");
            phase_ticks[dut.core_phase]++;
        end""")
    bench = replace(bench, "        $readmemh(modelfile,words);", """        if(!$value$plusargs("PHASE=%s",phase_path)) $fatal(1,"Missing phase path");
        phase_log=$fopen(phase_path,"w");
        if(!phase_log) $fatal(1,"Cannot open phase path");
        $readmemh(modelfile,words);""")
    return replace(bench, "        $fclose(dumpfile);", "        $fclose(phase_log);\n        $fclose(dumpfile);")


def copy_member(archive, name, destination):
    item = archive.getmember(name)
    if not item.isfile():
        raise ValueError(f"Not a regular archive member: {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(archive.extractfile(item).read())


def read_phases(path):
    result = {}
    for line in path.read_text().splitlines():
        label, first_valid, first, last, done, *phases = line.split()
        if label in result or len(phases) != 21:
            raise ValueError("Bad phase trace")
        result[label] = dict(first_valid=bool(int(first_valid)), first=int(first), last=int(last),
                             done=int(done), phases=list(map(int, phases)))
    if list(result) != ["prefix", "done"]:
        raise ValueError("Missing phase boundary")
    return result


def compare(control, candidate, outputs):
    for boundary in ("prefix", "done"):
        a, b = control[boundary], candidate[boundary]
        if a["positions"] != b["positions"] or a["first_valid"] != b["first_valid"]:
            raise ValueError("Different positions or first-byte status")
        saving = 0 if boundary == "prefix" else PROJECTION_CLOCKS * (
            a["positions"] - control["prefix"]["positions"] + 1)
        if a["cycles"] - b["cycles"] != saving or a["done"] - b["done"] != saving:
            raise ValueError(f"Request timing differs from matched schedule: {boundary}")
        phase_deltas = [x - y for x, y in zip(a["phases"], b["phases"], strict=True)]
        if phase_deltas != [saving if p == 18 else 0 for p in range(21)]:
            raise ValueError(f"Unexpected phase timing changes: {phase_deltas}")
    a, b = control["done"], candidate["done"]
    if a["first_valid"] != bool(outputs) or a["first"] - b["first"] != (PROJECTION_CLOCKS if outputs else 0):
        raise ValueError("Unexpected first-output timing")
    if a["last"] - b["last"] != PROJECTION_CLOCKS * outputs:
        raise ValueError("Unexpected last-output timing")


def main(args):
    deadline = min(time.monotonic() + 1500, time.monotonic() + args.deadline_epoch - time.time())
    variant = args.kv260 / "variants/scalar-div-v1"
    pin(variant / "test_model.py", DIV_TEST)
    generator = variant / "make_division.py"
    pin(generator, BASE_GENERATOR)
    div_test = runpy.run_path(str(variant / "test_model.py"))
    helpers, _ = div_test["prior"](args.kv260)
    cases = div_test["CASES"]
    env = helpers["simulator"](args.verilator.resolve(), args.kv260)
    run, boundaries = helpers["run"], helpers["boundaries"]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    pin(args.archive, ARCHIVE)
    refs = root / "reference"
    with tarfile.open(args.archive) as archive:
        for name in ("model.hex", "bos.hex", "autonomous_core_tb.sv", "profile-results.json"):
            copy_member(archive, f"{REFERENCE}/{name}", refs / name)
        for label in cases:
            for name in ("input.hex", "output.hex", "scores.hex"):
                copy_member(archive, f"{REFERENCE}/{label}/{name}", refs / label / name)
            copy_member(archive, f"candidate/{label}/cache.kv", refs / label / "cache.kv")
    archived = json.loads((refs / "profile-results.json").read_text())
    control_materialise = runpy.run_path(str(generator))["materialise"]
    paired = {}
    for arm, generate in (("control", control_materialise), ("candidate", materialise)):
        work = root / arm
        work.mkdir()
        rtl = work / "rtl"
        modules = generate(args.kv260, rtl)
        bench = work / "autonomous_core_tb.sv"
        bench.write_text(instrument((refs / bench.name).read_text()))
        binary = work / "obj/simulation"
        run([str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
             "--top-module", "autonomous_core_tb", "-j", "2", "--Mdir", str(binary.parent), "-o", "simulation",
             *[str(rtl / (name + ".sv")) for name in modules], str(bench)],
            work, env, work / "compile.log", 150, deadline)
        for label in cases:
            observed = work / label
            observed.mkdir()
            fixtures = refs / label
            case_name, cap_number = label.rsplit("-cap", 1)
            cap = int(cap_number)
            cached = boundaries(fixtures / "cache.kv")
            outputs = archived[label]["outputs"]
            params = dict(MODEL=refs / "model.hex", SCORES=refs / "bos.hex",
                          CSV=observed / "bus.events", RETURNS=observed / "bos.csv",
                          INPUT=fixtures / "input.hex", OUTPUT=fixtures / "output.hex",
                          ALLSCORES=fixtures / "scores.hex", PREFIX=cached["prefix"]["positions"],
                          OUTPUTS=outputs, POSITIONS=cached["done"]["positions"], CAP=cap,
                          REASON=1 if cap == 255 else 2 if case_name == "full-context" else 4,
                          SKIP=1, CACHE=observed / "cache.kv", PHASE=observed / "phases.txt")
            run([str(binary), *[f"+{key}={value}" for key, value in params.items()]],
                work, env, observed / "simulation.log", 600, deadline)
            phases = read_phases(params["PHASE"])
            for boundary, actual in boundaries(params["CACHE"]).items():
                expected = cached[boundary]
                if actual["positions"] != expected["positions"] or actual["kv"] != expected["kv"]:
                    raise ValueError(f"Exact cache mismatch: {arm} {label} {boundary}")
                if arm == "control" and actual["cycles"] != expected["cycles"]:
                    raise ValueError(f"Archived baseline cycles differ: {label} {boundary}")
                phases[boundary].update(positions=actual["positions"], cycles=actual["cycles"])
            entry = paired.setdefault(label, {"outputs": outputs})
            entry[arm] = phases
            if arm == "candidate":
                compare(entry["control"], phases, outputs)
            (root / "result.json").write_text(json.dumps(paired, indent=2) + "\n")
            print(arm, label, phases["done"]["cycles"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kv260", "verilator", "archive", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--deadline-epoch", required=True, type=float)
    main(parser.parse_args())
