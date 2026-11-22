"""Check both arms of the pinned DDR4 fixture against the seven adopted control cases."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import struct
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
BASE_CLOCKS = 2112
EXTRA_CLOCKS = 4608
PREVIOUS_ARCHIVE_SHA256 = "5c66c50778943d4601f4bbc8d93741522dada0d333b558c6f23e31adf3e2cff9"


def check(condition, context):
    if not condition:
        raise ValueError(context)


def replace_once(source, before, after):
    check(source.count(before) == 1, before)
    return source.replace(before, after, 1)


def previous_run(archive, output):
    check(sha256(archive.read_bytes()).hexdigest() == PREVIOUS_ARCHIVE_SHA256,
          "Experiment 13 simulation archive differs")
    output.mkdir()
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            path = Path(member.name)
            if not member.isfile():
                continue
            adopted_trace = path.parts[0] == "replay" and path.name in {
                "autonomous_core_tb.sv", "matched.json", "bos.csv", "phases.txt", "cache.kv"}
            oracle = path.parts[:2] == ("predecessor", "pinned") and path.suffix == ".hex"
            if adopted_trace or oracle:
                target = output / path
                target.parent.mkdir(exist_ok=True, parents=True)
                target.write_bytes(source.extractfile(member).read())
    return output / "replay", output / "predecessor" / "pinned"


def testbench(previous):
    original = (previous / "autonomous_core_tb.sv").read_text()
    base = original.split("// Observe each completed position", 1)[0]
    check(len(base) < len(original) and "endmodule" not in base, "Changed pinned benchmark bench")
    base = replace_once(base, "    axi_transformer dut (.*);",
                        (HERE / "axi_ddr_model.svh").read_text() + "\n" +
                        (HERE / "ddr_fault_cases.svh").read_text() + "\n    axi_transformer dut (.*);")
    base = replace_once(base, "        // Original full-score host interface remains usable before autonomous mode.",
        """        check_read(8'h8c,32'h44445231);
        check_read(8'h64,8);
        write_reg(8'h64,1,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE+8,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE-1,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE,4'hf,0,0,OKAY);
        check_read(8'h60,DDR_BASE);
        write_reg(8'h64,32'(ddr_arm),4'hf,0,0,OKAY);
        check_read(8'h64,ddr_arm ? 1 : 8);
        if (ddr_arm) write_reg(8'h60,DDR_BASE,4'hf,0,0,SLVERR);
        if ($value$plusargs("FAULT=%d",injected_fault) && injected_fault != 0) begin
            m_axi_rresp = injected_fault == 1 ? 2'b10 : 2'b00;
            m_axi_rid = injected_fault == 2 ? 6'd1 : 6'd0;
            m_axi_rlast = injected_fault != 3;
            qualify_fault();
        end
        // Original full-score host interface remains usable before autonomous mode.""")
    base = replace_once(base, "        polls=0;status=0;",
        """        write_reg(8'h64,32'(!ddr_arm),4'hf,0,0,SLVERR);
        polls=0;status=0;""")
    base = replace_once(base, "        check_read(8'h44,0);read_reg(8'h40,2,SLVERR,data);",
        """        check_read(8'h44,0);read_reg(8'h40,2,SLVERR,data);
        check_read(8'h64,ddr_arm ? 1 : 8);
        check_read(8'h68,ddr_arm ? 32'(2048*positions) : 0);
        check_read(8'h6c,ddr_arm ? 32'(1024*positions) : 0);
        check_read(8'h70,ddr_arm ? 32'(1024*positions) : 0);
        check_read(8'h74,0);
        check_read(8'h78,ddr_arm ? 32'(4608*positions) : 0);
        check_read(8'h7c,ddr_arm ? 32'(1024*positions) : 0);
        check_read(8'h80,ddr_arm ? 32'(1536*positions) : 0);
        check_read(8'h84,32'(positions));
        check_read(8'h88,32'(measured_clocks));
        write_reg(8'h64,0,4'hf,0,0,OKAY);
        check_read(8'h64,8);
        write_reg(8'h64,32'(ddr_arm),4'hf,0,0,OKAY);""")
    return base + "\nendmodule\n"


def audit(arm, case, measured, previous, parse, output_bytes):
    check((measured / "bos.csv").read_bytes() == (previous / "bos.csv").read_bytes(), (arm, case, "BOS"))
    extra = EXTRA_CLOCKS if arm == "ddr" else 0
    new_phases = parse["get_phases"](measured / "phases.txt")
    old_phases = parse["get_phases"](previous / "phases.txt")
    new_cache = parse["cache"](measured / "cache.kv")
    old_cache = parse["cache"](previous / "cache.kv")
    total = new_cache["done"][0]
    prefix = new_cache["prefix"][0]
    for name, boundary in new_phases.items():
        ref = old_phases[name]
        positions, cycles, cache = new_cache[name]
        ref_positions, ref_cycles, ref_cache = old_cache[name]
        check((positions, cache) == (ref_positions, ref_cache), (arm, case, name, "cache"))
        cost = positions * extra
        check(cycles == ref_cycles + cost and boundary["first_valid"] == ref["first_valid"], (arm, case, name, "cycles"))
        check(boundary["first"] == ref["first"] + (prefix * extra if ref["first_valid"] else 0),
              (arm, case, name, "first"))
        check(boundary["last"] == ref["last"] + ((prefix + output_bytes - 1) * extra if ref["first_valid"] else 0),
              (arm, case, name, "last"))
        check(boundary["done"] == ref["done"] + (cost if name == "done" else 0), (arm, case, name, "done"))
        deltas = [current - original for current, original in zip(boundary["phases"], ref["phases"])]
        check(deltas == [cost if i == 10 else 0 for i in range(21)], (arm, case, name, "phase", deltas))
        boundary.update(positions=positions, cycles=cycles)
    records = [list(map(int, line.split())) for line in (measured / "ddr-profile.txt").read_text().splitlines()]
    transfers, ar_stalls, r_waits = (1024,1024,1536) if extra else (0,0,0)
    expected = [[i,transfers,transfers,extra,ar_stalls,r_waits,BASE_CLOCKS+extra] for i in range(1,total+1)]
    check(records == expected, (arm, case, "projection profile", records[:1], expected[:1]))
    return new_phases


def main(args):
    started = time.monotonic()
    deadline = started + 1500
    kv = args.kv260
    model_path = kv / "variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0, str(model_path.parent))
    try:
        model = runpy.run_path(str(model_path))
    finally:
        sys.path.pop(0)
    parse = runpy.run_path(str(kv / "variants/attention-exp-pair-v2/replay_pair.py"))
    env = model["simulator"](args.verilator, kv)
    args.output.mkdir()
    previous, oracle = previous_run(args.previous, args.output / "control-fixtures")
    model_image = b"".join(struct.pack("<I", int(line, 16)) for line in (oracle / "model.hex").read_text().splitlines())
    matrix = runpy.run_path(str(HERE / "extract_weights.py"))["extract"](model_image)
    matrix_hex = args.output / "projection.hex"
    matrix_hex.write_text("".join(f"{beat:016x}\n" for (beat,) in struct.iter_unpack("<Q", matrix)))
    bench = args.output / "autonomous_core_tb.sv"
    bench.write_text(testbench(previous))
    source = json.loads((args.rtl / "source-manifest.json").read_bytes())
    fixture_pins = json.loads((HERE / "manifest.json").read_bytes())["fixture_sources"]
    check(all(source.get(name) == checksum for name, checksum in fixture_pins.items()),
          "Generated RTL does not match the fixture pins")
    rtl = [args.rtl / (name + ".sv") for name in source]
    check(all(sha256(f.read_bytes()).hexdigest() == source[f.stem] for f in rtl), "Generated source manifest changed")
    run = model["run"]
    exe = args.output / "obj/simulation"
    run([str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "2",
         "--top-module", "autonomous_core_tb", "--Mdir", str(exe.parent), "-o", "simulation",
         *map(str, rtl), str(bench)], args.output, env, args.output / "compile.log", 300, deadline)
    reference = json.loads((previous / "matched.json").read_bytes())["candidate"]
    measured = {}
    for arm in ("bram", "ddr", "fault"):
        measured[arm] = {}
        trials = [(case, ref, 0) for case, ref in reference.items()] if arm != "fault" else [
            ("bos-only-cap0", reference["bos-only-cap0"], fault) for fault in range(1, 8)]
        for case, ref, fault in trials:
            folder = args.output / arm / (str(fault) if fault else case)
            folder.mkdir(parents=True)
            cap = int(case.rsplit("-cap", 1)[1])
            params = dict(MODEL=oracle/"model.hex", SCORES=oracle/"bos.hex", INPUT=oracle/case/"input.hex",
                          OUTPUT=oracle/case/"output.hex", ALLSCORES=oracle/case/"scores.hex",
                          CSV=folder/"bus.events", RETURNS=folder/"bos.csv", PREFIX=ref["prefix"]["positions"],
                          OUTPUTS=ref["outputs"], POSITIONS=ref["done"]["positions"], CAP=cap, SKIP=1,
                          CACHE=folder/"cache.kv", PHASE=folder/"phases.txt", DDR=int(arm != "bram"), FAULT=fault,
                          MATRIX=matrix_hex, REASON=1 if cap == 255 else 2 if case.startswith("full-context") else 4)
            log = folder / "simulation.log"
            run([str(exe), *[f"+{name}={value}" for name, value in params.items()]],
                folder, env, log, 120, deadline)
            if fault:
                check(f"PASS DDR fault or cancel {fault}," in log.read_text(), ("fault", fault))
                measured[arm][str(fault)] = next(line for line in log.read_text().splitlines() if line.startswith("PASS"))
                print(measured[arm][str(fault)], flush=True)
                continue
            check("PASS autonomous_real_core positions=" in log.read_text(), (arm, case, "terminal marker"))
            measured[arm][case] = audit(arm, case, folder, previous / case, parse, ref["outputs"])
            print(arm, case, measured[arm][case]["done"]["cycles"], flush=True)
    dense = args.output / "dense-obj/simulation"
    run([str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "2",
         "--top-module", "dense_ddr_tb", "--Mdir", str(dense.parent), "-o", "simulation",
         str(args.rtl / "dense_ddr_projection.sv"), str(args.rtl / "projection_ddr_reader.sv"),
         str(HERE / "dense_ddr_tb.sv")], args.output, env, args.output / "dense-compile.log", 180, deadline)
    fixture = runpy.run_path(str(HERE / "dense_projection_fixture.py"))
    measured["dense"] = {}
    for folder, arm in fixture["dense_cases"](matrix, args.output):
        log = folder / "simulation.log"
        run([str(dense), f"+FIXTURE={folder}", f"+ARM={arm}"], folder, env, log, 60, deadline)
        check(f"PASS dense arm={arm}" in log.read_text(), ("dense", arm))
        measured["dense"][str(arm)] = next(line for line in log.read_text().splitlines() if line.startswith("PASS"))
        print(measured["dense"][str(arm)], flush=True)
    (args.output / "matched.json").write_text(json.dumps(measured, indent=2) + "\n")
    print(f"Exact seven-case replay completed in {time.monotonic() - started:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("kv260", "verilator", "previous", "rtl", "output"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    main(parser.parse_args())
