"""Replay the frozen seven-case model and check exact output and phase changes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
import time


def cache(path):
    lines = iter(path.read_text().splitlines())
    out = {}
    for line in lines:
        name, count, cycles = line.split()
        count = int(count)
        out[name] = (count, int(cycles), [next(lines) for _ in range(32 * count)])
    return out


def get_phases(path):
    out = {}
    for line in path.read_text().splitlines():
        name, *values = line.split()
        valid, first, last, done, *phases = map(int, values)
        assert len(phases) == 21
        out[name] = dict(first_valid=bool(valid), first=first, last=last, done=done, phases=phases)
    assert set(out) == {"prefix", "done"}
    return out


def forecast(scores):
    savings = []
    for context in scores:
        n = len(context[0])
        timing = [0, 0, 0, 0, 0, 0, 0, 0, 0]
        timing[0] = n
        saved = 0
        for head in context:
            lengths = [1 if x - max(head) < -1048576 else 49 for x in head]
            for i in range(0, n, 2):
                first = lengths[i]
                timing[4] += first - 1
                timing[7] += first == 1
                if i + 1 == n:
                    timing[3] += 1
                    timing[1] += 2 + first
                    continue
                second = lengths[i+1]
                timing[2] += 1
                timing[5] += second - 1
                timing[6] += min(first, second) - 1
                timing[8] += second == 1
                timing[1] += 3 + max(first + 1, second)
                saved += min(first + 1, second)
        savings.append((saved, timing))
    return savings


def audit(case, results, prior, gold_case, folder):
    model_events = (folder/"attention-events.txt").read_text().splitlines()
    scores = []
    for line in model_events:
        kind, *values = line.split()
        if kind != "S":
            continue
        head, position, score = map(int, values)
        if head == 0 and position == 0:
            scores.append([[], []])
        assert position == len(scores[-1][head])
        scores[-1][head].append(score)
    assert scores == read_gold_scores(gold_case)
    stream = []
    running_sum = 0
    for row in model_events:
        fields = row.split()
        if fields[0] == "E":
            _, _, position, value, observed_sum = fields
            if position == "0":
                running_sum = 0
            running_sum += int(value)
            assert running_sum == int(observed_sum)
            row = " ".join(fields[:-1])
        stream.append(row)
    assert stream == model_events_only(gold_case)
    prediction = forecast(scores)
    profile = [list(map(int, line.split())) for line in (folder/"attention-pairs.txt").read_text().splitlines()]
    assert [timing for _, timing in prediction] == profile, (case, first_difference(profile, prediction))
    accum = [0]
    for clocks, _ in prediction:
        accum.append(accum[-1] + clocks)
    for name in ("bos.csv","overlap-profile.txt","down-profile.txt"):
        assert (folder/name).read_bytes() == (prior/name).read_bytes(), (case,name)
    phases = get_phases(folder/"phases.txt")
    original_cache = cache(prior/"cache.kv")
    candidate_cache = cache(folder/"cache.kv")
    for name, boundary in phases.items():
        ref = results[name]
        count, count_cycles, vector = candidate_cache[name]
        assert count == ref["positions"] == original_cache[name][0]
        assert vector == original_cache[name][2]
        assert count_cycles == ref["cycles"] - accum[count]
        assert boundary["first_valid"] == ref["first_valid"]
        for index, (candidate, adopted) in enumerate(zip(boundary["phases"], ref["phases"], strict=True)):
            assert adopted - candidate == (accum[count] if index == 8 else 0), (case,name,index)
        assert boundary["done"] == (ref["done"]-accum[count] if ref["done"] else 0)
        if ref["first_valid"]:
            assert boundary["first"] == ref["first"]-accum[results["prefix"]["positions"]]
            assert boundary["last"] == ref["last"]-accum[results["prefix"]["positions"]+results["outputs"]-1]
        else:
            assert boundary["first"] == boundary["last"] == 0
        boundary.update(positions=count,cycles=count_cycles)
    print(case, "saved clocks", accum[-1], "of", results["done"]["done"], flush=True)
    return dict(phases, outputs=results["outputs"], saved_clocks=accum[-1], exp_profile=profile)


def first_difference(profile, forecasts):
    return next(((i,actual,expected) for i,(actual,(_,expected)) in enumerate(zip(profile,forecasts))
                 if actual != expected), (len(profile), len(forecasts)))


def main(a):
    kv = a.repo/"hardware/research/inference/implementations/kv260"
    model_path = kv/"variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0,str(model_path.parent))
    try:
        model = runpy.run_path(str(model_path))
    finally:
        sys.path.pop(0)
    env = model["simulator"](a.verilator, kv)
    deadline = time.monotonic() + min(1100,a.deadline_epoch-time.time())
    a.output.mkdir()
    older = json.loads((a.previous/"matched.json").read_bytes())["control"]
    original = (a.previous/"candidate/autonomous_core_tb.sv").read_text()
    base = original.split("// Observe the same ready-cache replay as Experiment 10",1)[0]
    assert len(base) < len(original) and base.count("endmodule")==0
    bench = a.output/"autonomous_core_tb.sv"
    bench.write_text(base+Path(__file__).with_name("monitor.svh").read_text()+"\nendmodule\n")
    source = json.loads((a.rtl/"source-manifest.json").read_bytes())
    rtl = [a.rtl/(name+".sv") for name in source]
    assert all(sha256(f.read_bytes()).hexdigest()==source[f.stem] for f in rtl)
    exe = a.output/"obj/simulation"
    run = model["run"]
    run([str(a.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","autonomous_core_tb","--Mdir",str(exe.parent),"-o","simulation",
         *map(str,rtl),str(bench)],a.output,env,a.output/"compile.log",150,deadline)
    measured = {}
    for case, ref in older.items():
        folder = a.output/case
        folder.mkdir()
        oracle = a.previous/"pinned"
        cap = int(case.rsplit("-cap",1)[1])
        params = dict(MODEL=oracle/"model.hex", SCORES=oracle/"bos.hex", INPUT=oracle/case/"input.hex",
                      OUTPUT=oracle/case/"output.hex", ALLSCORES=oracle/case/"scores.hex",
                      CSV=folder/"bus.events", RETURNS=folder/"bos.csv", PREFIX=ref["prefix"]["positions"],
                      OUTPUTS=ref["outputs"], POSITIONS=ref["done"]["positions"], CAP=cap, SKIP=1,
                      CACHE=folder/"cache.kv", PHASE=folder/"phases.txt",
                      REASON=1 if cap == 255 else 2 if case.startswith("full-context") else 4)
        run([str(exe),*[f"+{name}={value}" for name,value in params.items()]],folder,env,folder/"simulation.log",120,deadline)
        assert "PASS autonomous_real_core positions=" in (folder/"simulation.log").read_text()
        measured[case] = audit(case,ref,a.previous/"control"/case,a.gold/case,folder)
    (a.output/"matched.json").write_text(json.dumps(dict(control=older,candidate=measured),indent=2)+"\n")


def model_events_only(folder):
    # The independent monitor also captures one legacy BOS before and after
    # the autonomous request. Each legacy BOS emits S, E and P for both heads.
    rows = (folder/"intermediates.txt").read_text().splitlines()
    assert rows[:6] == rows[-6:]
    return rows[6:-6]


def read_gold_scores(folder):
    out = []
    for line in model_events_only(folder):
        kind, *values = line.split()
        if kind != "S":
            continue
        head, pos, word = map(int, values)
        if head == 0 and pos == 0:
            out.append([[],[]])
        assert pos == len(out[-1][head])
        out[-1][head].append(word)
    return out


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("repo","verilator","previous","gold","rtl","output"):
        p.add_argument("--"+name,type=lambda s:Path(s).resolve(),required=True)
    p.add_argument("--deadline-epoch",type=float,required=True)
    main(p.parse_args())
