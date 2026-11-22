"""Prove bit-exact scalar commands and resets in all nested RMSNorm products."""

import argparse
import json
from pathlib import Path
import runpy
import sys
import time

from materialise_norm_multiply import HERE, checked, materialise

SCALAR_BENCH_SHA256="64fb3e109279ce1a8207a7363c3033ae0be4e839451e8fa81753e251941b0fb8"


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def main(args):
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    prior=kv260/"variants/ff-scalar-mul-dsp-v1"
    model=load(kv260/"variants/scalar-mul-v1/test_model.py")
    oracle=load(kv260/"tools/rtl.py")
    generate=load(prior/"test_scalar.py")["fixtures"]
    env=model["simulator"](args.verilator,kv260)
    deadline=time.monotonic()+min(350,args.deadline_epoch-time.time())
    out=args.output
    out.mkdir()
    control,candidate=(out/arm for arm in ("control","candidate"))
    materialise(kv260,control,False)
    materialise(kv260,candidate,True)
    control_source=out/"fixed_scalar_mul_control.sv"
    generic=(control/"fixed_scalar.sv").read_text()
    assert generic.count("module fixed_scalar (")==1
    control_source.write_text(generic.replace("module fixed_scalar (","module fixed_scalar_mul_control ("))
    bench=out/"scalar_tb.sv"
    bench_text=checked(prior/"scalar_tb.sv",SCALAR_BENCH_SHA256).decode()
    assert bench_text.count("fixed_scalar_ff_exp candidate")==1
    bench_text=bench_text.replace("fixed_scalar_ff_exp candidate","fixed_scalar_norm_dsp candidate")
    marker='        $display("PASS scalar:'
    assert bench_text.count(marker)==1
    bench.write_text(bench_text.replace(marker,(HERE/"rsqrt_reset.svh").read_text()+marker))
    counts=generate(oracle,args.model,out)
    exp=[int(word,16) for word in (out/"exp.hex").read_text().splitlines()]
    rsqrt=[int(word,16) for word in (out/"rsqrt.hex").read_text().splitlines()]
    assert oracle["scalar_reference"](4,1<<32,0,0,exp,rsqrt)==(1<<30,0)
    rsqrt_rows=[row for row in (out/"scalar.hex").read_text().splitlines() if row.startswith("4 ")]
    assert len(rsqrt_rows)>100
    exe=out/"obj/simulation"
    run=model["run"]
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","partial_multiply_scalar_tb","--Mdir",str(exe.parent),"-o","simulation",
         str(control_source),str(candidate/"rmsnorm.sv"),str(bench)],out,env,out/"compile.log",150,deadline)
    run([str(exe),f"+FIXTURES={out}",f"+ROWS={counts['rows']}"],out,env,out/"simulation.log",120,deadline)
    receipt=(out/"simulation.log").read_text()
    assert f"PASS scalar: {counts['rows']}" in receipt and "PASS thirty reciprocal-sqrt cancellations" in receipt
    counts.update(all_exact=True,direct_multiply_reset_states=5,rsqrt_command_rows=len(rsqrt_rows),
                  rsqrt_cancellation_probes=30,control_steps=16,candidate_steps=5)
    (out/"summary.json").write_text(json.dumps(counts,indent=2)+"\n")
    print(counts,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","model","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
