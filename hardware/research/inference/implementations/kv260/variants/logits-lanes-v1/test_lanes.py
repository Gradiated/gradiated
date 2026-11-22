"""Check exact scores, bank traces and request cycles for one emitted variant."""

import argparse
import json
from pathlib import Path
import runpy
import sys
import tarfile
import time

from materialise_lanes import materialise, pinned

ARCHIVE = "34bbfb5f802ab213800aaac7720fbbcb6d11362aaaf477e611546d4489bea85a"
PIPELINE_TEST = "853c92138843b62915353e33b1d808383936030960268bc62b55a63ba34035a3"
DIV_TEST = "c9521eecf894f99931eaaa8000690aefb392fe8778bcae335bbee33ca54f6902"
CASES = ("encoded-hello-cap255","encoded-fu2p2q-cap255","encoded-max48-cap255",
         "encoded-hello-cap0","encoded-hello-cap1","bos-only-cap0","full-context-cap0")
CYCLES_PER_PROJECTION = {lanes:(34+lanes)*(320//lanes) for lanes in (1,2,4)}


def archived_fixtures(archive, root):
    pinned(archive,ARCHIVE)
    names = {"model/result.json", "model/reference/model.hex", "model/reference/bos.hex",
             "model/reference/autonomous_core_tb.sv"}
    names.update(f"component/{name}.hex" for name in ("input","weights","sums","products","answers16","answers32"))
    for label in CASES:
        names.update(f"model/reference/{label}/{name}.hex" for name in ("input","output","scores"))
        names.add(f"model/candidate/{label}/cache.kv")
    with tarfile.open(archive) as source:
        for name in sorted(names):
            member = source.getmember(name)
            if not member.isfile():
                raise ValueError(f"Expected regular fixture file: {name}")
            path = root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(source.extractfile(member).read())


def hex_values(path, bits):
    maximum = 1 << bits
    content = [int(line,16) for line in path.read_text().splitlines()]
    if any(not 0 <= value < maximum for value in content):
        raise ValueError(f"Fixture value is wider than {bits}: {path}")
    return [value-maximum if value >= maximum//2 else value for value in content]


def check_arithmetic_fixtures(path):
    inputs = hex_values(path/"input.hex",16)
    weights = hex_values(path/"weights.hex",16)
    products = hex_values(path/"products.hex",32)
    sums = hex_values(path/"sums.hex",48)
    if len(inputs)!=32 or [len(values) for values in (weights,products,sums)]!=[10240]*3:
        raise ValueError("Wrong standalone shape")
    answers = {bits:[int(line,16) for line in (path/f"answers{bits}.hex").read_text().splitlines()]
               for bits in (16,32)}
    if any(len(items)!=320 for items in answers.values()):
        raise ValueError("Incorrect signed answer fixtures")
    for row in range(320):
        total = 0
        for coord in range(32):
            i = row*32+coord
            product = inputs[coord]*weights[i]
            total += product
            if product != products[i] or total != sums[i]:
                raise ValueError("Independent signed oracle trace mismatch")
        magnitude,remainder = divmod(abs(total),256)
        magnitude += int(remainder>128 or (remainder==128 and magnitude%2))
        rounded = -magnitude if total<0 else magnitude
        for width,table in answers.items():
            low,high = -(1<<(width-1)),(1<<(width-1))-1
            clipped = min(high,max(low,rounded))
            fixture = (int(clipped!=rounded)<<32) | (clipped & 0xffffffff)
            if table[row] != fixture:
                raise ValueError("Independent signed oracle round/clip mismatch")


def compare(control, candidate, outputs, lanes):
    per_projection = CYCLES_PER_PROJECTION[1]-CYCLES_PER_PROJECTION[lanes]
    projections = control["done"]["positions"]-control["prefix"]["positions"]+1
    for label,expected in (("prefix",0),("done",projections*per_projection)):
        a,b = control[label],candidate[label]
        if a["positions"]!=b["positions"] or a["first_valid"]!=b["first_valid"]:
            raise ValueError("Position or first-byte status changed")
        if a["cycles"]-b["cycles"]!=expected or a["done"]-b["done"]!=expected:
            raise ValueError(f"Request cycle law failed: {label}")
        if [x-y for x,y in zip(a["phases"],b["phases"],strict=True)]!=[
            expected if i==18 else 0 for i in range(len(a["phases"]))
        ]:
            raise ValueError("A phase outside LOGIT_WAIT changed")
    a,b = control["done"],candidate["done"]
    if (a["first_valid"]!=bool(outputs) or a["first"]-b["first"]!=(per_projection if outputs else 0)
            or a["last"]-b["last"]!=outputs*per_projection):
        raise ValueError("First/last output cycle law failed")


def verified_helpers(kv260):
    division = kv260/"variants/scalar-div-v1/test_model.py"
    model = kv260/"variants/logits-pipeline-v1/test_model.py"
    pinned(division,DIV_TEST)
    pinned(model,PIPELINE_TEST)
    sys.path.insert(0,str(model.parent))
    try:
        one = runpy.run_path(str(model))
        division = runpy.run_path(str(division))
        helpers, _ = division["prior"](kv260)
    finally:
        sys.path.pop(0)
    return one,helpers


def compile_and_run_component(args, root, env, run, deadline):
    if args.lanes==1:
        return
    component = root/"component"
    check_arithmetic_fixtures(component)
    rtl = root/"rtl"
    bench = Path(__file__).with_name("logits_lanes_tb.sv")
    binary = root/"obj-component/simulation"
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal",
         "--top-module","logits_lanes_tb",f"-GLANES={args.lanes}","-j","2","--Mdir",str(binary.parent),
         "-o","simulation",str(rtl/"transformer.sv"),str(bench)],
        root,env,component/"compile.log",150,deadline)
    run([str(binary),"+FIXTURES="+str(component)],root,env,component/"simulation.log",60,deadline)
    (component/"result.json").write_text(json.dumps({
        "lanes":args.lanes,"rows":320,"ordered_products_per_width":10240,
        "result_widths":[32,16],"reset_offsets":35+args.lanes,
        "all_stream_lanes_stalled":True,"projection_cycles":CYCLES_PER_PROJECTION[args.lanes],
    },indent=2)+"\n")
    print(f"{args.lanes} lanes exact component checks passed",flush=True)


def main(args):
    deadline = min(time.monotonic()+1500,time.monotonic()+args.deadline_epoch-time.time())
    one, helpers = verified_helpers(args.kv260)
    env = helpers["simulator"](args.verilator.resolve(),args.kv260)
    run, boundaries = helpers["run"],helpers["boundaries"]
    root = args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    archive_root = root/"fixtures"
    archived_fixtures(args.archive,archive_root)
    (archive_root/"component").rename(root/"component")
    rtl = root/"rtl"
    names = materialise(args.kv260,rtl,args.lanes)
    compile_and_run_component(args,root,env,run,deadline)
    model = archive_root/"model"
    reference = model/"reference"
    frozen = json.loads((model/"result.json").read_text())
    bench = root/"autonomous_core_tb.sv"
    bench.write_text(one["instrument"]((reference/bench.name).read_text()))
    binary = root/"obj-model/simulation"
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal",
         "--top-module","autonomous_core_tb","-j","2","--Mdir",str(binary.parent),"-o","simulation",
         *[str(rtl/(name+".sv")) for name in names],str(bench)],
        root,env,root/"compile.log",150,deadline)
    results = {}
    for label in CASES:
        suite = reference/label
        path = root/label
        path.mkdir()
        case,cap_name = label.rsplit("-cap",1)
        cap = int(cap_name)
        archived = frozen[label]["candidate"]
        outputs = frozen[label]["outputs"]
        expected_cache = boundaries(model/"candidate"/label/"cache.kv")
        params = dict(MODEL=reference/"model.hex",SCORES=reference/"bos.hex",
                      CSV=path/"bus.events",RETURNS=path/"bos.csv",
                      INPUT=suite/"input.hex",OUTPUT=suite/"output.hex",ALLSCORES=suite/"scores.hex",
                      PREFIX=archived["prefix"]["positions"],OUTPUTS=outputs,POSITIONS=archived["done"]["positions"],
                      CAP=cap,REASON=1 if cap==255 else 2 if case=="full-context" else 4,
                      SKIP=1,CACHE=path/"cache.kv",PHASE=path/"phases.txt")
        run([str(binary),*[f"+{key}={value}" for key,value in params.items()]],
            root,env,path/"simulation.log",600,deadline)
        phases = one["read_phases"](params["PHASE"])
        for boundary,seen in boundaries(params["CACHE"]).items():
            expected = expected_cache[boundary]
            if seen["positions"]!=expected["positions"] or seen["kv"]!=expected["kv"]:
                raise ValueError(f"Exact KV cache mismatch: {label} {boundary}")
            phases[boundary].update(positions=seen["positions"],cycles=seen["cycles"])
        compare(archived,phases,outputs,args.lanes)
        results[label] = dict(outputs=outputs,**phases)
        (root/"result.json").write_text(json.dumps(results,indent=2)+"\n")
        print(f"{args.lanes} {label}: {phases['done']['cycles']} clocks",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for option in ("kv260","verilator","archive","output"):
        p.add_argument("--"+option,type=Path,required=True)
    p.add_argument("--lanes",type=int,choices=(1,2,4),required=True)
    p.add_argument("--deadline-epoch",type=float,required=True)
    main(p.parse_args())
