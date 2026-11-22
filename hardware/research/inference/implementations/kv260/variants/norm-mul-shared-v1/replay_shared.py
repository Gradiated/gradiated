"""Replay the dedicated and shared normalization multipliers on seven exact fixtures."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile
import time

from materialise_shared_norm_multiply import checked, materialise, replace_once


HERE = Path(__file__).resolve().parent
ARCHIVE_PIN = "497dd939c88eaab38672722b85ac96fcf4df493ec2d3d73d66d4569ec6b2ff5d"
TOOL_PIN = "cbaba03f25514c8016822e6d45d8110aff0705e1b50324ba14ab5bab15fe5d3e"
PHASES = {4, 12, 16}
NUM_PRODS = 102
SAVED_PER_NORM = NUM_PRODS * (16 - 5)
CORE_TRACES = ("attention-events.txt", "divider-values.txt", "cache-addresses.bin",
               "attention-pairs.txt", "overlap-profile.txt", "down-profile.txt",
               "norm-products.txt", "norm-outputs.txt", "bos.csv", "feedforward-products.txt",
               "feedforward-elements.txt", "feedforward-profile.txt")
EXACT_TRACES = (*CORE_TRACES, "phases.txt", "bus.events", "cache.kv", "probability-profile.txt")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def arm_bench(origin, shared):
    norm_names = ("norm1", "norm2", "normfinal")
    prefixes = ("n1", "n2", "nf")
    actions = []
    for i, (norm, signal) in enumerate(zip(norm_names, prefixes, strict=True)):
        instance = f"dut.core.{norm}.scalar"
        mask = f" && dut.core.norm_mul_valid[{i}]" if shared else ""
        actions.append(f"""    if ({instance}.state == {instance}.MUL_FINISH{mask})
        observe_product({i}, {instance}.multiplicand, {instance}.multiplier,
                        {instance}.negative, {instance}.product_sum);
    if (dut.core.{signal}_valid && dut.core.{signal}_ready)
        observe_norm_output({i}, dut.core.{signal}_index, dut.core.{signal}_result,
                            dut.core.{signal}_clip, dut.core.{signal}_error);""")
    body = (HERE / "model_monitor.svh").read_text()
    body = replace_once(body, "    // SCALAR_OBSERVATIONS", "\n".join(actions))
    if shared:
        owner_code = """    begin
        logic [2:0] request, grant, retire;
        request = dut.core.norm_mul_request;
        grant = dut.core.norm_mul_grant;
        retire = dut.core.norm_mul_valid & dut.core.norm_mul_ready;
        if (!$onehot0(request) || request != grant)
            $fatal(1, "Concurrent or delayed normalisation grant in the transformer");
        if (|grant) begin
            if (granted_owner != 0 ||
                (grant[0] && dut.core_phase != 4) ||
                (grant[1] && dut.core_phase != 12) ||
                (grant[2] && dut.core_phase != 16))
                $fatal(1, "Wrong or overlapping normalisation grant");
            granted_owner = grant;
            grant_cycle = cycle_count;
            for (int i=0; i<3; i++)
                if (grant[i]) observed_grants[i]++;
        end
        if (|dut.core.norm_mul_valid) begin
            if (retire != granted_owner || dut.core.norm_mul_valid != granted_owner ||
                cycle_count - grant_cycle != 4)
                $fatal(1, "Shared result ownership or calculation clocks differ");
            granted_owner = 0;
        end
    end"""
        body = replace_once(body, "    // SHARED_OWNERSHIP", owner_code)
    return replace_once(origin, "\nendmodule\n", body + "\nendmodule\n")


def extract(archive_path, root):
    checked(archive_path, ARCHIVE_PIN)
    with tarfile.open(archive_path) as archive:
        def get(path):
            member = archive.getmember(path)
            need(member.isfile(), f"Unexpected archive member: {path}")
            with archive.extractfile(member) as stream:
                return stream.read()

        expected = {
            case: {**value["candidate"], "outputs": value["outputs"],
                   "scored_values": value["scored_values"]}
            for case, value in json.loads(get("replay/matched.json")).items()
        }
        original = get("replay/autonomous_core_tb.sv").decode()
        gold = root / "gold"
        gold.mkdir()
        prefix = "replay/gold/replay/gold/predecessor/pinned/"
        for name in ("model.hex", "bos.hex"):
            (gold / name).write_bytes(get(prefix + name))
        for case in expected:
            case_dir = gold / case
            case_dir.mkdir()
            for name in ("input.hex", "scores.hex", "output.hex"):
                (case_dir / name).write_bytes(get(prefix + case + "/" + name))
            for name in ("cache.kv", "phases.txt", "attention-events.txt", "divider-values.txt",
                         "cache-addresses.bin", "bos.csv"):
                (case_dir / name).write_bytes(get(f"replay/candidate/{case}/{name}"))
    return expected, original


def tool_environment(tool):
    files = {str(f.relative_to(tool)): sha256(f.read_bytes()).hexdigest()
             for f in sorted(tool.rglob("*")) if f.is_file()}
    digest = sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    need(len(files) == 132 and digest == TOOL_PIN, "Verilator runtime differs from the pinned tree")
    return dict(os.environ, VERILATOR_ROOT=str(tool / "share/verilator"),
                PATH="/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                SDKROOT="/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")


def run(args, work, env, log, timeout, deadline):
    seconds = min(timeout, deadline - time.monotonic())
    need(seconds > 0, "Local RTL qualification deadline reached")
    with log.open("xb") as stream, subprocess.Popen(
        args, cwd=work, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
    ) as process:
        try:
            status = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
    need(status == 0, f"Simulation command exited {status}, see {log}")


def phases(path):
    rows = {}
    for line in path.read_text().splitlines():
        key, *fields = line.split()
        valid, first, last, done, *ticks = map(int, fields)
        rows[key] = dict(valid=bool(valid), first=first, last=last, done=done, ticks=ticks)
    return rows


def strip_cache_times(path):
    return [" ".join(line.split()[:2]) if line.startswith(("prefix ", "done ")) else line
            for line in path.read_text().splitlines()]


def trial(executable, case, reference, root, env, deadline):
    work = executable.parent.parent / case
    work.mkdir()
    gold = root / "gold"
    cap = int(case.rsplit("-cap", 1)[1])
    params = dict(MODEL=gold/"model.hex", SCORES=gold/"bos.hex", INPUT=gold/case/"input.hex",
                  OUTPUT=gold/case/"output.hex", ALLSCORES=gold/case/"scores.hex",
                  CSV=work/"bus.events", RETURNS=work/"bos.csv", PREFIX=reference["prefix"]["positions"],
                  OUTPUTS=reference["outputs"], POSITIONS=reference["done"]["positions"], CAP=cap, SKIP=1,
                  CACHE=work/"cache.kv", PHASE=work/"phases.txt",
                  REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4)
    run([str(executable), *[f"+{key}={value}" for key, value in params.items()]],
        work, env, work/"simulation.log", 150, deadline)
    count = re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                      r"reason=(\d+) legacy_BOS_scores=640", (work/"simulation.log").read_text())
    need(count and tuple(map(int, count.groups())) == (
        reference["done"]["positions"], reference["scored_values"], reference["outputs"], params["REASON"]),
        f"{work}: model oracle failed")
    return work


def verify_case(case, ref, control, candidate, gold):
    case_label = f"{case}:"
    for file in EXACT_TRACES:
        need((control/file).read_bytes() == (candidate/file).read_bytes(),
             f"{case_label} shared and dedicated replay differ in {file}")
    for file in ("attention-events.txt", "divider-values.txt", "cache-addresses.bin", "bos.csv"):
        need((control/file).read_bytes() == (gold/file).read_bytes(),
             f"{case_label} inherited numerical trace changed in {file}")
    need(strip_cache_times(control/"cache.kv") == strip_cache_times(gold/"cache.kv"),
         f"{case_label} inherited stored KV differs")

    old, comparison = (phases(root/"phases.txt") for root in (gold, control))
    for boundary, observed in comparison.items():
        baseline = old[boundary]
        n = ref[boundary]["positions"]
        expected = [ticks - SAVED_PER_NORM * n if i in PHASES else ticks
                    for i, ticks in enumerate(baseline["ticks"])]
        need(observed["ticks"] == expected and observed["valid"] == baseline["valid"],
             f"{case_label} {boundary} has unexpected stage clocks")
    old_done, actual = old["done"], comparison["done"]
    n = ref["done"]["positions"]
    prefix = ref["prefix"]["positions"]
    last = prefix + ref["outputs"] - 1
    depths = dict(first=prefix if old_done["valid"] else 0, last=last if old_done["valid"] else 0, done=n)
    for boundary, depth in depths.items():
        need(old_done[boundary] - 3 * SAVED_PER_NORM * depth == actual[boundary],
             f"{case_label} forecast mismatch at {boundary}")
    need(sum(actual["ticks"]) == actual["done"], f"{case_label} phase totals do not sum")

    totals = [0, 0, 0]
    with (candidate/"norm-products.txt").open() as stream:
        for line in stream:
            position, client, a, b, sign, product = line.split()
            index = int(client)
            need(1 <= int(position) <= n and int(sign) in (0, 1)
                 and int(a, 16) * int(b, 16) == int(product, 16),
                 f"{case_label} raw product differs from Python arithmetic")
            totals[index] += 1
    need(totals == [n * NUM_PRODS] * 3, f"{case_label} incorrect product counts")
    for arm, directory in (("control", control), ("candidate", candidate)):
        ownership = [list(map(int, line.split())) for line in (directory/"norm-ownership.txt").read_text().splitlines()]
        expected = [[i, n*NUM_PRODS, n*32, n*NUM_PRODS if arm=="candidate" else 0] for i in range(3)]
        need(ownership == expected, f"{case_label} {arm} unexpected ownership or norm output counts")
    print(f"{case:24} first={actual['first']:,} last={actual['last']:,} done={actual['done']:,} "
          f"exact products={sum(totals):,}", flush=True)
    return {**comparison, "positions": n, "outputs": ref["outputs"], "products": sum(totals),
            "scored_values": ref["scored_values"]}


def compile_model(tool, env, work, deadline):
    sources = sorted((work/"rtl").glob("*.sv"))
    binary = work/"obj/simulation"
    run([str(tool/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal", "-j", "2", "+define+PARTIAL_MULTIPLIER",
         "--top-module", "autonomous_core_tb", "--Mdir", str(binary.parent), "-o", binary.name,
         *map(str, sources), str(work/"autonomous_core_tb.sv")],
        work, env, work/"compile.log", 150, deadline)
    return binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "dedicated", "kv260", "output", "verilator"):
        parser.add_argument("--"+name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 30*60
    root = args.output
    root.mkdir()
    expected, origin = extract(args.archive, root)
    need(len(expected) == 7, "Expected seven frozen fixtures")
    env = tool_environment(args.verilator)

    for arm in ("control", "candidate"):
        work = root/arm
        materialise(args.kv260, args.dedicated, work/"rtl", arm=="candidate")
        (work/"autonomous_core_tb.sv").write_text(arm_bench(origin, arm=="candidate"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        binaries = list(pool.map(lambda arm: compile_model(args.verilator, env, root/arm, deadline),
                                 ("control", "candidate")))
    results = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {case:[pool.submit(trial, binary, case, ref, root, env, deadline) for binary in binaries]
                   for case, ref in expected.items()}
        for case, ref in expected.items():
            control, candidate = [future.result() for future in pending[case]]
            results[case] = verify_case(case, ref, control, candidate, root/"gold"/case)
    (root/"model-results.json").write_text(json.dumps(results, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
