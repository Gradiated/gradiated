"""Check only the changed cache schedule against exact component and model oracles."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import runpy
import sys
import time

import component
from materialise_attention import HERE, checked, materialise, once


def read_phases(path):
    result={}
    for line in path.read_text().splitlines():
        label, *items=line.split()
        valid, first, last, done, *states=map(int,items)
        if label in result or len(states)!=21:
            raise ValueError("Invalid attention phase evidence")
        result[label]=dict(first_valid=bool(valid),first=first,last=last,done=done,phases=states)
    assert set(result)=={"prefix","done"}
    return result


def audit_run(case, expected, prediction, path, old, model):
    phases=read_phases(path/"phases.txt")
    cache=model["boundaries"](path/"cache.kv")
    baseline=model["boundaries"](old/"cache.kv")
    for boundary, row in phases.items():
        n=expected[boundary]["positions"]
        assert n==cache[boundary]["positions"]==baseline[boundary]["positions"]
        assert cache[boundary]["kv"]==baseline[boundary]["kv"]
        assert row["first_valid"]==expected[boundary]["first_valid"]
        assert cache[boundary]["cycles"]==prediction[boundary]["cycles"]
        assert all(row[name]==prediction[boundary][name] for name in ("first","last","done"))
        delta=prediction[boundary]["saved_attention"]
        if any(a-b!=(delta if i==8 else 0)
               for i,(a,b) in enumerate(zip(expected[boundary]["phases"],row["phases"],strict=True))):
            raise ValueError(f"Unexpected phase or counter change: {case}/{boundary}")
        row.update(positions=n,cycles=cache[boundary]["cycles"])
    checked(path/"bos.csv",sha256((old/"bos.csv").read_bytes()).hexdigest())
    raw=[list(map(int,line.split())) for line in (path/"overlap-profile.txt").read_text().splitlines()]
    if raw!=[[n,2*n,32*n,32*n,30*n,32,32*n,32*n,32*(n-1)]
             for n in range(1,phases["done"]["positions"]+1)]:
        raise ValueError("Exact per-position cache schedule differs")
    return dict(outputs=expected["outputs"],**phases)


def model_case(case, baseline, prediction, args, work, helper, env, binary, deadline):
    path=work/"candidate"/case
    path.mkdir()
    oracle=work/"pinned/oracle"
    cap=int(case.rsplit("-cap",1)[1])
    params=dict(MODEL=oracle/"model.hex",SCORES=oracle/"bos.hex",INPUT=oracle/case/"input.hex",
                OUTPUT=oracle/case/"output.hex",ALLSCORES=oracle/case/"scores.hex",CSV=path/"bus.events",
                RETURNS=path/"bos.csv",PREFIX=baseline["prefix"]["positions"],OUTPUTS=baseline["outputs"],
                POSITIONS=baseline["done"]["positions"],CAP=cap,SKIP=1,
                REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4,
                CACHE=path/"cache.kv",PHASE=path/"phases.txt")
    helper["run"]([str(binary),*[f"+{name}={value}" for name,value in params.items()]],path,env,
                  path/"simulation.log",120,deadline)
    if not re.search(r"^PASS autonomous_real_core positions=", (path/"simulation.log").read_text(), re.M):
        raise ValueError("Full-model success receipt missing")
    result=audit_run(case,baseline,prediction,path,work/"pinned/expected"/case,helper)
    print(case,result["done"]["done"],"clocks",flush=True)
    return result


def main(args):
    deadline=time.monotonic()+min(1100,args.deadline_epoch-time.time())
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    spec=json.loads((HERE/"manifest.json").read_bytes())
    diagnostic_path=args.diagnostic/"replay.py"
    checked(diagnostic_path,spec["diagnostic_replay_sha256"])
    diagnostic=runpy.run_path(str(diagnostic_path))
    repo_raw=args.repo/".agents/runtime/hardware/inference/outputs"/diagnostic["BASELINE"]
    for file,pin in diagnostic["BASE_PINS"].items():
        checked(repo_raw/file,pin)
    baseline=json.loads((repo_raw/"model-results.json").read_bytes())["candidate"]
    predictions=json.loads(checked(args.predictions,spec["predictions_sha256"]))["cases"]
    assert baseline.keys()==predictions.keys()
    helper=diagnostic["helper"](kv260)
    env=helper["simulator"](args.verilator,kv260)
    work=args.output
    work.mkdir()
    names=diagnostic["extract"](repo_raw,work/"pinned")
    candidate=work/"candidate"
    candidate.mkdir()
    assert set(materialise(kv260,candidate/"rtl",True))==set(names)
    changed=[name for name in names if (candidate/"rtl"/(name+".sv")).read_bytes()!=(work/"pinned/rtl"/(name+".sv")).read_bytes()]
    if changed!=["attention"]:
        raise ValueError("Generated change escaped the attention RTL")
    shape=component.run(args,work/"component",kv260,candidate/"rtl",work/"pinned/oracle/model.hex",helper,env,deadline)
    print("Exact attention component passed:",shape,flush=True)
    original=(work/"pinned/oracle/autonomous_core_tb.sv").read_text()
    bench=candidate/"autonomous_core_tb.sv"
    bench.write_text(once(original,"endmodule", (HERE/"monitor.svh").read_text()+"\nendmodule"))
    binary=candidate/"obj/simulation"
    helper["run"]([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
                   "--top-module","autonomous_core_tb","--Mdir",str(binary.parent),"-o","simulation",
                   *[str(candidate/"rtl"/(name+".sv")) for name in names],str(bench)],
                  candidate,env,candidate/"compile.log",150,deadline)
    actual={name:model_case(name,row,predictions[name],args,work,helper,env,binary,deadline)
            for name,row in baseline.items()}
    (work/"matched.json").write_text(json.dumps(dict(control=baseline,candidate=actual),indent=2,sort_keys=True)+"\n")
    print("Exact seven-case full-model comparison and every cache schedule passed.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","diagnostic","output","predictions"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
