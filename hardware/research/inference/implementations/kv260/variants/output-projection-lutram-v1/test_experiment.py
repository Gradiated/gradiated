"""Check the pinned dense fixture and seven complete model schedules."""

import argparse
from hashlib import sha256
from pathlib import Path
import json
import runpy
import sys
import tarfile
import time

from materialise_projection_lutram import HERE, checked, materialise, replace_one

PRIOR = ".agents/runtime/hardware/inference/outputs/attention-exp-div-rtl-20261117T131434Z"
EXPECTED = ("bos.csv", "bus.events", "cache.kv", "phases.txt", "overlap-profile.txt",
            "attention-divider.txt", "down-profile.txt")


def load(path):
    sys.path.insert(0, str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def compile_bench(args, output, source, bench, top, run, env, deadline, options=()):
    binary = output/"obj/simulation"
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal",
         "-j","2","--top-module",top,"--Mdir",str(binary.parent),"-o","simulation",
         *options,*map(str,source),str(bench)],output,env,output/"compile.log",150,deadline)
    return binary


def dense_checks(args, work, kv, spec, environment, run, deadline):
    rtl_tool=kv/"tools/rtl.py"
    bench=kv/"rtl/dense_tb.sv"
    checked(rtl_tool,spec["dense_oracle_sha256"])
    checked(kv/"tools/runtime.py",spec["dense_runtime_sha256"])
    bench_text=checked(bench,spec["dense_bench_sha256"]).decode()
    oracle=load(rtl_tool)
    cases=oracle["dense_fixtures"](32,32,16,16)
    main=work/"dense"
    main.mkdir()
    hexfile=oracle["dense_hexfile"]
    inputs=dict(CASES=len(cases),X=hexfile(main,"inputs",(v for c in cases for v in c["x"])),
        W=hexfile(main,"weights",(v for c in cases for row in c["weights"] for v in row)),
        ANSWERS=hexfile(main,"answers",(item["result"] for c in cases for item in c["expected"])),
        CLIPS=hexfile(main,"clips",(item["saturated"] for c in cases for item in c["expected"]),8))
    results={}
    for arm in ("control","candidate"):
        folder=main/arm
        folder.mkdir()
        local=folder/"dense_tb.sv"
        local.write_text(bench_text if arm=="control" else
                         replace_one(bench_text,"    dense #(","    dense_output_projection_lutram #("))
        rtl=work/arm/"rtl"
        binary=compile_bench(args,folder,[rtl/"dense.sv"]+([rtl/"transformer.sv"] if arm=="candidate" else []),
                            local,"dense_tb",run,environment,deadline,("-GSHIFT=16",))
        trace=folder/"cycles.csv"
        params=dict(inputs,CSV=trace,VCD=folder/"waves.vcd")
        run([str(binary),*[f"+{name}={value}" for name,value in params.items()]],
            folder,environment,folder/"simulation.log",120,deadline)
        if "inputs=32 outputs=32 shift=16 bits=16 reset_probes=7" not in (folder/"simulation.log").read_text():
            raise ValueError("Missing exact geometry and reset receipt")
        results[arm]=oracle["dense_check_trace"](trace,cases,32,32)
    if results["control"]!=results["candidate"] or (main/"control/cycles.csv").read_bytes()!=(main/"candidate/cycles.csv").read_bytes():
        raise ValueError("Mapped-array directive affected dense state or timing")
    (main/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    print("Dense 32×32 traces matched",results["candidate"],flush=True)


def model_checks(args, work, repo, kv, spec, names, env, model, run, deadline):
    raw=repo/PRIOR
    archive=raw/"simulation.tar.gz"
    checked(archive,spec["control_replay_archive_sha256"])
    reference=json.loads(checked(raw/"model-results.json",spec["control_replay_result_sha256"]))["candidate"]
    base=work/"pinned"
    base.mkdir()
    candidate=work/"candidate"
    with tarfile.open(archive) as old:
        def extract(name, out):
            item=old.getmember(name)
            if not item.isfile():
                raise ValueError(f"Unexpected replay fixture shape {name}")
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(old.extractfile(item).read())
        extract("candidate/autonomous_core_tb.sv",candidate/"autonomous_core_tb.sv")
        for name in ("model.hex","bos.hex"):
            extract(f"pinned/oracle/{name}",base/name)
        for case in reference:
            for name in ("input.hex","output.hex","scores.hex"):
                extract(f"pinned/oracle/{case}/{name}",base/case/name)
            for name in EXPECTED:
                extract(f"candidate/{case}/{name}",work/"control"/case/name)
    binary=compile_bench(args,candidate,[candidate/"rtl"/(name+".sv") for name in names],
                         candidate/"autonomous_core_tb.sv","autonomous_core_tb",run,env,deadline)
    records={}
    for case, expected in reference.items():
        folder=candidate/case
        folder.mkdir()
        control=work/"control"/case
        cap=int(case.rsplit("-cap",1)[1])
        inputs=dict(MODEL=base/"model.hex",SCORES=base/"bos.hex",INPUT=base/case/"input.hex",
                    OUTPUT=base/case/"output.hex",ALLSCORES=base/case/"scores.hex",CSV=folder/"bus.events",
                    RETURNS=folder/"bos.csv",PREFIX=expected["prefix"]["positions"],OUTPUTS=expected["outputs"],
                    POSITIONS=expected["done"]["positions"],CAP=cap,SKIP=1,CACHE=folder/"cache.kv",
                    PHASE=folder/"phases.txt",REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4)
        run([str(binary),*[f"+{name}={value}" for name,value in inputs.items()]],
             folder,env,folder/"simulation.log",120,deadline)
        if "PASS autonomous_real_core positions=" not in (folder/"simulation.log").read_text():
            raise ValueError(f"Missing full model receipt: {case}")
        records[case]={name:sha256(checked(folder/name,sha256((control/name).read_bytes()).hexdigest())).hexdigest()
                       for name in EXPECTED}
        print(case,expected["done"]["done"],"identical clocks and seven exact traces",flush=True)
    (work/"trace-receipt.json").write_text(json.dumps(records,indent=2,sort_keys=True)+"\n")
    (work/"matched.json").write_text(json.dumps({"control":reference,"candidate":reference},
                                              indent=2,sort_keys=True)+"\n")


def main(args):
    deadline=time.monotonic()+min(1100,args.deadline_epoch-time.time())
    kv=args.repo/"hardware/research/inference/implementations/kv260"
    spec=json.loads((HERE/"manifest.json").read_bytes())
    diag=kv/"diagnostics/attention-profile-v1/replay.py"
    checked(diag,spec["replay_helper_sha256"])
    helper=load(diag)["helper"](kv)
    env=helper["simulator"](args.verilator,kv)
    work=args.output
    work.mkdir()
    names=[]
    for arm in ("control","candidate"):
        (work/arm).mkdir()
        names=materialise(kv,work/arm/"rtl",arm=="candidate")
    changed=[name for name in names if (work/"control/rtl"/(name+".sv")).read_bytes()!=
             (work/"candidate/rtl"/(name+".sv")).read_bytes()]
    if changed!=["transformer"]:
        raise ValueError("The mapping change escaped the generated transformer source")
    dense_checks(args,work,kv,spec,env,helper["run"],deadline)
    model_checks(args,work,args.repo,kv,spec,names,env,helper,helper["run"],deadline)


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ("repo","verilator","output"):
        cli.add_argument("--"+name,type=lambda arg:Path(arg).resolve(),required=True)
    cli.add_argument("--deadline-epoch",type=float,required=True)
    main(cli.parse_args())
