"""Simulation-only scalar multiply speed limits for the sealed Experiment 18 circuit."""

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile


RUN = "probability-div-v1-rtl-20261119T160135Z"
ARCHIVE_HASH = "6be001afaadce8ef883ca5206bef8bf4093e8dd9475927cc9162c210c923c76e"
TOOL_HASH = "cbaba03f25514c8016822e6d45d8110aff0705e1b50324ba14ab5bab15fe5d3e"
CASES = ("encoded-hello-cap255", "encoded-fu2p2q-cap255", "encoded-max48-cap255")
ARMS = {
    "baseline": (16, 16, 16),
    "ff5": (16, 5, 16),
    "rms8": (8, 16, 16),
    "ff8": (16, 8, 16),
    "attention8": (16, 16, 8),
    "all8": (8, 8, 8),
    "all1": (1, 1, 1),
}
CALLERS = {
    "norm1": ("norm1.scalar", 4),
    "norm2": ("norm2.scalar", 12),
    "normfinal": ("normfinal.scalar", 16),
    "feedforward": ("ff.scalar", 14),
    "attention_primary": ("att.scalar", 8),
    "attention_second": ("att.second_exp", 8),
}
PHASES = {"norm1": 4, "norm2": 12, "normfinal": 16, "feedforward": 14, "attention": 8}
SOURCES = {"fixed_scalar": "RMS_MUL_CYCLES", "feedforward": "FF_MUL_CYCLES",
           "attention": "ATT_MUL_CYCLES"}
EXACT = ("bos.csv", "attention-events.txt", "cache-addresses.bin",
         "divider-values.txt", "overlap-profile.txt")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def edit_once(source, old, new):
    check(source.count(old) == 1, f"Pinned RTL anchor changed: {old}")
    return source.replace(old, new)


def group_steps(source, plusarg):
    # Keep the exact recurrence and group consecutive radix-16 digit steps
    # within one simulated edge. This code is never given to a synthesis tool.
    source = edit_once(source, "    task automatic multiply_start(", f"""
    integer simulated_mul_cycles = 16;
    initial begin
        if ($value$plusargs("{plusarg}=%d", simulated_mul_cycles)) begin
            if (!(simulated_mul_cycles inside {{1, 2, 4, 5, 8, 16}}))
                $fatal(1, "Unsupported simulation multiply latency");
        end
    end

    logic [127:0] simulated_product;
    always_comb begin
        logic [67:0] digit_sum;
        int digits_this_edge;
        simulated_product = next_product;
        digit_sum = 0;
        digits_this_edge = 0;
        if (state == MUL_STEP) begin
            // Differences of adjacent cumulative digit counts sum to 16,
            // including when the requested latency is five edges.
            digits_this_edge = 16 * int'(remaining) / simulated_mul_cycles -
                               16 * (int'(remaining) - 1) / simulated_mul_cycles;
            for (int step = 1; step < digits_this_edge; step++) begin
                digit_sum = {{4'd0,simulated_product[127:64]}} +
                            68'(multiplicand)*simulated_product[3:0];
                simulated_product = {{digit_sum,simulated_product[63:4]}};
            end
        end
    end

    task automatic multiply_start(""")
    source = edit_once(source, "magnitude(b)};remaining<=16;",
                       "magnitude(b)};remaining<=7'(simulated_mul_cycles);")
    start = source.index("                MUL_STEP: begin")
    end = source.index("                SIMPLE_DONE:", start)
    mul_step = source[start:end]
    check(mul_step.count("next_product") == 4, "Unexpected product retirement path")
    return source[:start] + mul_step.replace("next_product", "simulated_product") + source[end:]


def instrument(bench):
    hooks = []
    for i, (_, (path, phase)) in enumerate(CALLERS.items()):
        instance = f"dut.core.{path}"
        hooks.append(f"""
        if (int'(dut.core_phase)=={phase} && {instance}.state=={instance}.MUL_STEP)
            observe_multiply({i}, int'({instance}.return_state), {instance}.remaining,
                             {instance}.simulated_mul_cycles, {instance}.multiplicand,
                             {instance}.product_sum[63:0], {instance}.simulated_product,
                             {instance}.negative);""")
    code = (Path(__file__).parent / "monitor.svh").read_text()
    code = edit_once(code, "        // SCALAR_HOOKS", "\n".join(hooks))
    return edit_once(bench, "\nendmodule\n", "\n" + code + "\nendmodule\n")


def initialise(repo, output):
    run = repo / "hardware/research/inference/results" / RUN / "run.json"
    entries = json.loads(run.read_text())["artifacts"]
    item, = [entry for entry in entries if entry["path"].endswith("/simulation.tar.gz")]
    check(item["sha256"] == ARCHIVE_HASH, "Archived replay pin differs from the run record")
    archive_path = repo / item["path"]
    data = archive_path.read_bytes()
    check(sha(data) == ARCHIVE_HASH and len(data) == item["bytes"], "Archived replay digest differs")

    with tarfile.open(archive_path) as archive:
        def read(name):
            member = archive.getmember(name)
            check(member.isfile(), f"Expected regular archive member: {name}")
            with archive.extractfile(member) as stream:
                return stream.read()

        prefix = "replay/candidate/rtl/"
        manifest = json.loads(read(prefix + "source-manifest.json"))
        sources = output / "rtl"
        sources.mkdir()
        for name, digest in manifest.items():
            path = name + ".sv"
            original = read(prefix + path)
            check(sha(original) == digest, f"Source manifest mismatch: {path}")
            source = original.decode()
            if name in SOURCES:
                source = group_steps(source, SOURCES[name])
            (sources / path).write_text(source)
        (output / "autonomous_core_tb.sv").write_text(
            instrument(read("replay/autonomous_core_tb.sv").decode())
        )
        pinned = "replay/gold/predecessor/pinned/"
        gold = output / "gold"
        gold.mkdir()
        for name in ("model.hex", "bos.hex"):
            (gold / name).write_bytes(read(pinned + name))
        references = json.loads(read("replay/matched.json"))
        for case in CASES:
            case_dir = gold / case
            case_dir.mkdir()
            for name in ("input.hex", "output.hex", "scores.hex"):
                (case_dir / name).write_bytes(read(pinned + case + "/" + name))
            for name in (*EXACT, "cache.kv", "phases.txt", "probability-profile.txt",
                         "attention-pairs.txt", "down-profile.txt", "bus.events"):
                (case_dir / name).write_bytes(read(f"replay/candidate/{case}/{name}"))
    return {
        case: {**references[case]["candidate"],
               **{k: references[case][k] for k in ("outputs", "scored_values")}}
        for case in CASES
    }


def command(args, cwd, env, log, timeout):
    with log.open("xb") as stream, subprocess.Popen(
        args, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
    ) as process:
        try:
            status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
    check(status == 0, f"Command exited {status}, see {log}")


def prepare_tool(tool):
    files = {str(f.relative_to(tool)): sha(f.read_bytes())
             for f in sorted(tool.rglob("*")) if f.is_file()}
    digest = sha(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
    check(digest == TOOL_HASH and len(files) == 132, "Verilator tree differs from the pinned tool")
    return dict(os.environ, VERILATOR_ROOT=str(tool / "share/verilator"),
                PATH="/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                SDKROOT="/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")


def phases(file):
    out = {}
    for line in file.read_text().splitlines():
        boundary, *numbers = line.split()
        valid, first, last, done, *ticks = map(int, numbers)
        out[boundary] = dict(first_valid=bool(valid), first=first, last=last, done=done, phases=ticks)
    return out


def cache(file):
    return [[line.split()[0], line.split()[1]] if line.startswith(("prefix ", "done ")) else line
            for line in file.read_text().splitlines()]


def schedule(file):
    return [list(map(int, line.split())) for line in file.read_text().splitlines()]


def profile(file):
    lines = file.read_text().splitlines()
    simultaneous = int(lines.pop())
    vals = [line.split() for line in lines]
    return dict(attention_two_lanes_multiplying_cycles=simultaneous,
                callers={caller: [dict(calls=int(row[2]), cycles=int(row[3]),
                                       max_abs_a_bits=int(row[4]), max_abs_b_bits=int(row[5]),
                                       raw_product_digest=row[6])
                                  for row in vals if int(row[0]) == i]
                         for i, caller in enumerate(CALLERS)})


def replay(arm, case, output, env, reference):
    work = output / arm / case
    work.mkdir(parents=True)
    gold = output / "gold"
    fixture = gold / case
    bench = output / "obj/simulation"
    params = dict(MODEL=gold/"model.hex", SCORES=gold/"bos.hex", INPUT=fixture/"input.hex",
                  OUTPUT=fixture/"output.hex", ALLSCORES=fixture/"scores.hex", CSV=work/"bus.events",
                  RETURNS=work/"bos.csv", PREFIX=reference["prefix"]["positions"],
                  OUTPUTS=reference["outputs"], POSITIONS=reference["done"]["positions"], CAP=255,
                  SKIP=1, CACHE=work/"cache.kv", PHASE=work/"phases.txt", REASON=1)
    params.update(zip(SOURCES.values(), ARMS[arm]))
    command([str(bench), *[f"+{k}={v}" for k, v in params.items()]],
            work, env, work / "simulation.log", 120)
    receipt = re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                        r"reason=1 legacy_BOS_scores=640", (work/"simulation.log").read_text())
    counts = (reference["done"]["positions"], reference["scored_values"], reference["outputs"])
    check(receipt and tuple(map(int, receipt.groups())) == counts,
          f"{arm}/{case}: model-oracle receipt differs")
    for name in EXACT:
        check((work/name).read_bytes() == (fixture/name).read_bytes(), f"{arm}/{case}: {name} differs")
    check(cache(work/"cache.kv") == cache(fixture/"cache.kv"), f"{arm}/{case}: KV values differ")
    for name, columns in (("probability-profile.txt", (0, 1, 2, 3, 4)), ("down-profile.txt", (0, 2, 3, 4, 5, 6))):
        preserved = lambda path: [tuple(row[i] for i in columns) for row in schedule(path)]
        check(preserved(work/name) == preserved(fixture/name), f"{arm}/{case}: {name} work differs")
    if arm == "baseline":
        for name in ("phases.txt", "cache.kv", "probability-profile.txt", "attention-pairs.txt",
                     "down-profile.txt", "bus.events"):
            check((work/name).read_bytes() == (fixture/name).read_bytes(), f"Baseline changed {case}/{name}")
    times = phases(work/"phases.txt")
    slots = times["done"]
    check(sum(slots["phases"]) == slots["done"], f"{arm}/{case}: phase ticks do not sum")
    print(f"{arm:11} {case:24} first={slots['first']:,} last={slots['last']:,} done={slots['done']:,}",
          flush=True)
    return dict(times, counts=counts, profile=profile(work/"multiply-profile.txt"))


def audit(arm, case, control, test):
    for name in CALLERS:
        left, right = (sample["profile"]["callers"][name] for sample in (control, test))
        check(len(left) == len(right) == 3, f"{case}/{name}: missing origin bin")
        for a, b in zip(left, right):
            for key in ("calls", "max_abs_a_bits", "max_abs_b_bits", "raw_product_digest"):
                check(a[key] == b[key], f"{arm}/{case}/{name}: {key} differs")

    phase_saved = {}
    for boundary in ("prefix", "done"):
        left, right = control[boundary], test[boundary]
        savings = [a - b for a, b in zip(left["phases"], right["phases"])]
        allowed = set()
        for latency, scopes in zip(ARMS[arm], (("norm1", "norm2", "normfinal"),
                                               ("feedforward",), ("attention",))):
            if latency != 16:
                allowed.update(PHASES[name] for name in scopes)
        check(all(delta >= 0 and (not delta or index in allowed) for index, delta in enumerate(savings)),
              f"{arm}/{case}: unexpected phase delta {savings}")
        phase_saved[boundary] = {name: savings[idx] for name, idx in PHASES.items()}
        if boundary == "done":
            check(sum(savings) == left["done"]-right["done"], f"{case}: completion delta differs")
    left, right = control["done"], test["done"]
    check(sum(phase_saved["prefix"].values()) == left["first"]-right["first"], f"{case}: first delta differs")
    return phase_saved


def write_metrics(results, path):
    rows = []
    for case in CASES:
        control = results["baseline"][case]["done"]
        control_decode = control["last"] - control["first"]
        for arm in ARMS:
            item = results[arm][case]
            observed = item["done"]
            decode = observed["last"] - observed["first"]
            done_saved = control["done"] - observed["done"]
            rows.append({
                "case": case,
                "arm": arm,
                "first_output_cycles": observed["first"],
                "last_output_cycles": observed["last"],
                "decode_cycles": decode,
                "completion_cycles": observed["done"],
                "saved_first_output_cycles": control["first"] - observed["first"],
                "saved_decode_cycles": control_decode - decode,
                "saved_completion_cycles": done_saved,
                "completion_cycle_reduction_pct": f"{100 * done_saved / control['done']:.5f}",
                "decode_tokens_per_second_at_50_mhz": f"{(item['counts'][2]-1) * 50_000_000 / decode:.5f}",
                **{f"saved_{key}_cycles": value
                   for key, value in sorted(item["saved_phase_cycles"]["done"].items())},
            })
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "verilator", "output"):
        parser.add_argument("--"+name, type=lambda p: Path(p).resolve(), required=True)
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    check(1 <= args.jobs <= 6, "Choose 1–6 local simulation workers")
    args.output.mkdir()
    reference = initialise(args.repo, args.output)
    env = prepare_tool(args.verilator)
    command([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
             "-j", "2", "--top-module", "autonomous_core_tb", "--Mdir", str(args.output/"obj"),
             "-o", "simulation", *map(str, sorted((args.output/"rtl").glob("*.sv"))),
             str(args.output/"autonomous_core_tb.sv")], args.output, env, args.output/"compile.log", 150)
    results = {arm: {} for arm in ARMS}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        jobs = {pool.submit(replay, arm, case, args.output, env, reference[case]): (arm, case)
                for arm in ARMS for case in CASES}
        for job in concurrent.futures.as_completed(jobs):
            arm, case = jobs[job]
            results[arm][case] = job.result()
    for arm in ARMS:
        for case in CASES:
            row = results[arm][case]
            row["saved_phase_cycles"] = audit(arm, case, results["baseline"][case], row)
    for case in CASES:
        groups = ("rms8", "ff8", "attention8")
        for phase in PHASES:
            group_sum = sum(results[arm][case]["saved_phase_cycles"]["done"][phase] for arm in groups)
            check(group_sum == results["all8"][case]["saved_phase_cycles"]["done"][phase],
                  f"{case}: combined phase savings differ from separate interventions")
    (args.output/"results.json").write_text(json.dumps(results, indent=2, sort_keys=True)+"\n")
    write_metrics(results, args.output/"metrics.csv")


if __name__ == "__main__":
    main()
