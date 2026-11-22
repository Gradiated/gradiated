"""Replay both probability-divider arms against the adopted Exp13 archive."""

import argparse
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_probability_div import HERE, checked, materialise

ARCHIVE_SHA256 = "5c66c50778943d4601f4bbc8d93741522dada0d333b558c6f23e31adf3e2cff9"
ADOPTED_TRACES = ("attention-events.txt", "attention-pairs.txt", "bos.csv",
                  "cache.kv", "down-profile.txt", "overlap-profile.txt", "phases.txt")


def load_model(kv260):
    path = kv260/"variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0, str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def extract(archive_path, dest):
    checked(archive_path, ARCHIVE_SHA256)
    with tarfile.open(archive_path) as archive:
        reference = json.load(archive.extractfile("replay/matched.json"))["candidate"]
        files = ["replay/autonomous_core_tb.sv", "predecessor/pinned/model.hex",
                 "predecessor/pinned/bos.hex"]
        for case in reference:
            files.extend(f"predecessor/pinned/{case}/{name}.hex" for name in ("input", "output", "scores"))
            files.extend(f"replay/{case}/{name}" for name in ADOPTED_TRACES)
        for name in files:
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError(f"Expected a regular archive member: {name}")
            output = dest/name
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(archive.extractfile(member).read())
    return reference


def phase_rows(folder, cached, get_phases):
    phases = get_phases(folder/"phases.txt")
    checkpoint = cached(folder/"cache.kv")
    for name, row in phases.items():
        row["positions"], row["cycles"], _ = checkpoint[name]
    return phases


def division_values(folder, positions):
    divider = iter((folder/"divider-values.txt").read_text().splitlines())
    depth = 0
    exponential = [[], []]
    sums = [0, 0]
    minimum_q = 32768
    maximum_q = zero = equal = ties = 0
    for row in (folder/"attention-events.txt").read_text().splitlines():
        kind, head, pos, *values = row.split()
        head, pos = int(head), int(pos)
        value, *extra = map(int, values)
        if kind == "S" and head == pos == 0:
            depth += 1
            exponential = [[], []]
            sums = [0, 0]
        if kind == "E":
            assert pos == len(exponential[head]) and 0 <= value <= 1 << 31
            exponential[head].append(value)
            sums[head] += value
            assert extra == [sums[head]]
        if kind == "P":
            assert len(exponential[head]) == depth
            e, s = exponential[head][pos], sums[head]
            assert 0 <= e <= s <= 1 << 39 and s > 0
            a = e << 15
            q, r = divmod(a, s)
            assert list(map(int, next(divider).split())) == [depth, head, pos, a, s, q, r]
            assert value == q + (2*r > s or (2*r == s and q % 2 == 1))
            minimum_q, maximum_q = min(minimum_q, q), max(maximum_q, q)
            zero += e == 0
            equal += e == s
            ties += 2*r == s
    assert depth == positions and next(divider, None) is None
    return dict(minimum_quotient=minimum_q, maximum_quotient=maximum_q,
                zero_exponentials=zero, equal_exponential_and_sum=equal, ties=ties)


def check_case(case, ref, pinned, control, candidate, pair, receipts):
    positions = ref["done"]["positions"]
    for filename in ADOPTED_TRACES:
        assert (control/filename).read_bytes() == (pinned/filename).read_bytes(), (case, filename)
        if filename not in ("cache.kv", "phases.txt"):
            assert (control/filename).read_bytes() == (candidate/filename).read_bytes(), (case, filename)
    for filename in ("divider-values.txt", "cache-addresses.bin"):
        assert (control/filename).read_bytes() == (candidate/filename).read_bytes(), (case, filename)
    addresses = (control/"cache-addresses.bin").read_bytes()
    assert len(addresses) == 3 * 64 * sum(range(1, positions+1))
    observed = {}
    cumulative = [0]
    for depth, (old, new) in enumerate(zip(
        (control/"probability-profile.txt").read_text().splitlines(),
        (candidate/"probability-profile.txt").read_text().splitlines(),
        strict=True,
    ), 1):
        reads = 2*depth
        old_counts, new_counts = [list(map(int, row.split())) for row in (old, new)]
        assert old_counts[:5] == [depth, reads, reads, 35*reads, 32*reads], (case, old)
        assert new_counts[:5] == [depth, reads, reads, 11*reads, 8*reads], (case, new)
        old_wait, new_wait = old_counts[3], new_counts[3]
        assert len(old_counts) == len(new_counts) == 6
        assert old_counts[5]-new_counts[5] == old_wait-new_wait
        observed[depth] = dict(divisions=reads, control_wait=old_wait, candidate_wait=new_wait,
                               control_steps=old_counts[4], candidate_steps=new_counts[4],
                               control_attention=old_counts[5], candidate_attention=new_counts[5])
        cumulative.append(cumulative[-1]+old_wait-new_wait)
    assert len(observed) == positions
    assert receipts["control"] == receipts["candidate"]
    count, scores, outputs, reason = receipts["candidate"]
    assert count == positions and outputs == ref["outputs"]
    assert scores == 320*(positions-ref["prefix"]["positions"]+1)
    phases = {arm: phase_rows(folder, pair["cache"], pair["get_phases"])
              for arm, folder in (("control", control), ("candidate", candidate))}
    cache = {arm: pair["cache"](folder/"cache.kv")
             for arm, folder in (("control", control), ("candidate", candidate))}
    for boundary in ("prefix", "done"):
        old, new = [phases[arm][boundary] for arm in ("control", "candidate")]
        assert old == ref[boundary], (case, boundary)
        count = old["positions"]
        saving = cumulative[count]
        assert new["positions"] == count and old["cycles"]-new["cycles"] == saving
        assert cache["control"][boundary][2] == cache["candidate"][boundary][2]
        for arm, sample in (("control", old), ("candidate", new)):
            assert sample["phases"][8] == sum(observed[d][arm+"_attention"] for d in range(1,count+1))
        assert old["first_valid"] == new["first_valid"]
        for stage, (before, after) in enumerate(zip(old["phases"], new["phases"], strict=True)):
            assert before-after == (saving if stage == 8 else 0), (case, boundary, stage)
        assert new["done"] == (old["done"]-saving if old["done"] else 0)
        if old["first_valid"]:
            prefix = ref["prefix"]["positions"]
            assert old["first"]-new["first"] == cumulative[prefix]
            assert old["last"]-new["last"] == cumulative[prefix+outputs-1]
        else:
            assert new["first"] == new["last"] == 0
    details = dict(outputs=outputs, scored_values=scores, skipped_positions=positions-scores//320,
                   stop_reason=reason, saved_clocks=cumulative[-1],
                   probability_profile=observed, divider=division_values(candidate, positions))
    print(case, phases["control"]["done"]["done"], phases["candidate"]["done"]["done"],
          "saved", cumulative[-1], flush=True)
    return {**phases, **details}


def main(args):
    deadline = time.monotonic() + min(1100, args.deadline_epoch-time.time())
    kv260 = args.repo/"hardware/research/inference/implementations/kv260"
    pair = runpy.run_path(str(kv260/"variants/attention-exp-pair-v2/replay_pair.py"))
    model = load_model(kv260)
    env = model["simulator"](args.verilator, kv260)
    out = args.output
    out.mkdir()
    reference = extract(args.archive, out/"gold")
    original = (out/"gold/replay/autonomous_core_tb.sv").read_text()
    assert original.endswith("\nendmodule\n") and original.count("endmodule")==1
    bench = out/"autonomous_core_tb.sv"
    bench.write_text(original.removesuffix("endmodule\n")+(HERE/"monitor.svh").read_text()+"endmodule\n")
    exe = {}
    run = model["run"]
    for arm in ("control", "candidate"):
        work = out/arm
        work.mkdir()
        rtl = work/"rtl"
        names = materialise(kv260, rtl, arm=="candidate")
        exe[arm] = work/"obj/simulation"
        run([str(args.verilator/"bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
             "-j", "2", "--top-module", "autonomous_core_tb", "--Mdir", str(exe[arm].parent),
             "-o", "simulation", *[str(rtl/(name+".sv")) for name in names], str(bench)],
            work, env, work/"compile.log", 150, deadline)
    measured = {}
    for case, ref in reference.items():
        receipts = {}
        for arm in ("control", "candidate"):
            folder = out/arm/case
            folder.mkdir()
            oracle = out/"gold/predecessor/pinned"
            cap = int(case.rsplit("-cap", 1)[1])
            params = dict(MODEL=oracle/"model.hex", SCORES=oracle/"bos.hex", INPUT=oracle/case/"input.hex",
                          OUTPUT=oracle/case/"output.hex", ALLSCORES=oracle/case/"scores.hex",
                          CSV=folder/"bus.events", RETURNS=folder/"bos.csv", PREFIX=ref["prefix"]["positions"],
                          OUTPUTS=ref["outputs"], POSITIONS=ref["done"]["positions"], CAP=cap, SKIP=1,
                          CACHE=folder/"cache.kv", PHASE=folder/"phases.txt",
                          REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4)
            run([str(exe[arm]), *[f"+{key}={value}" for key, value in params.items()]], folder, env,
                folder/"simulation.log", 120, deadline)
            match = re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                              r"reason=(\d+) legacy_BOS_scores=640", (folder/"simulation.log").read_text())
            assert match, (arm, case)
            receipts[arm] = tuple(map(int, match.groups()))
        measured[case] = check_case(case, ref, out/"gold/replay"/case, out/"control"/case,
                                    out/"candidate"/case, pair, receipts)
        (out/"matched.json").write_text(json.dumps(measured, indent=2)+"\n")
    assert len(measured)==7


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "verilator", "archive", "output"):
        parser.add_argument("--"+name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    main(parser.parse_args())
