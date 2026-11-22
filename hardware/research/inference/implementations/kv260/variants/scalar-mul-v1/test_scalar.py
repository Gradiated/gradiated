"""Exercise both scalar circuits against the existing independent integer oracle."""

import argparse
import csv
import json
from pathlib import Path
import random
import sys
import time

from materialise import BASELINE_GENERATOR, materialise, pin
from test_model import run, simulator
import runpy

BENCH_PIN = "cec02c2d6124308edcb2cc4bf637275de15148855675d2f73774d09831230cb2"


def reset_bench(bench, steps):
    insert = """        // Cancel a product after each possible number of completed steps.
        for(integer step=0;step<STEPS;step++)begin
            cmd_valid=1;cmd_op=2;cmd_a=-64'sd3037000499;cmd_b=64'sd3037000499;
            #1;if(!cmd_ready)$fatal(1,"Busy at multiply reset probe");
            tick();@(negedge clk);cmd_valid=0;
            repeat(step)begin
                if(result_valid || cmd_ready)$fatal(1,"Multiply ended before reset probe");
                tick();@(negedge clk);
            end
            reset=1;tick();
            if(result_valid || error || result!==0 || result_exponent!==0 ||
               cmd_ready || table_ready)$fatal(1,"Reset left in-flight multiplication visible");
            @(negedge clk);reset=0;
            cmd_valid=1;cmd_op=2;cmd_a=7;cmd_b=-15;
            #1;if(!cmd_ready)$fatal(1,"No new multiply accepted after reset");
            tick();@(negedge clk);cmd_valid=0;
            while(!result_valid)begin tick();@(negedge clk);end
            if(result!== -64'sd105 || error)$fatal(1,"Stale state after multiply reset");
            result_ready=1;tick();@(negedge clk);result_ready=0;
        end
""".replace("STEPS", str(steps))
    marker = "        // A held output is also cancelled by reset."
    if bench.count(marker)!=1:
        raise ValueError("Unexpected scalar testbench")
    return bench.replace(marker, insert + marker)


def extra_products(oracle):
    lower, upper = -(1 << 63), (1 << 63)-1
    rng = random.Random(0x6404)
    pairs = [(x, y) for x in (lower,-upper,-(1<<62),-16,-15,-1,0,1,15,16,upper)
             for y in (lower,-upper,-16,-15,-2,-1,0,1,2,15,16,upper)]
    for shift in range(64):
        digit = min(15, upper >> shift) << shift
        pairs.extend((a,b) for a,b in
                     ((15,digit),(-15,-digit),(1,digit),(digit,1),
                      (3,upper//3),(3,upper//3+1),(3037000499,3037000499),
                      (3037000500,3037000500)) if (a,b) not in pairs)
    for _ in range(512):
        bits = rng.randrange(1,64)
        pairs.append((rng.randrange(-(1<<bits),1<<bits),
                      rng.randrange(-(1<<(64-bits)),1<<(64-bits))))
        pairs.append((rng.randint(lower,upper),rng.randint(lower,upper)))
    cases = []
    for a,b in pairs:
        try:
            result,error=oracle(a,b),0
        except OverflowError:
            result,error=0,1
        cases.append(dict(op=2,a=a,b=b,shift=0,result=result,exponent=0,error=error))
    return cases


def main(a):
    deadline = time.monotonic()+5*60
    tool = a.verilator.resolve()
    env = simulator(tool, a.kv260)
    sys.path.insert(0, str(a.kv260/"tools"))
    import rtl

    root = a.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    words = [int(row,16) for row in a.model.read_text().splitlines()]
    if len(words)!=29281:
        raise ValueError("Unexpected model word count")
    exp, rsqrt = words[-513:-256], words[-256:]
    cases = rtl.scalar_vivado_cases(exp,rsqrt) + extra_products(rtl.scalar_multiply_reference)
    if len(cases)>4096:
        raise ValueError("Too many scalar fixtures")
    random.Random(0x4816).shuffle(cases)
    (root/"fixtures.json").write_text(json.dumps(dict(cases=cases, exp=exp, rsqrt=rsqrt),
                                                  indent=2)+"\n")
    args={key.upper():rtl.scalar_vivado_hexfile(root,key,(c[key] for c in cases),bits)
          for key,bits in (("op",8),("a",64),("b",64),("shift",8),("result",64),("exponent",8),("error",8))}
    args["ANSWER"]=args.pop("RESULT")
    args.update(EXP=rtl.scalar_vivado_hexfile(root,"exp_table",exp,32),
                RSQRT=rtl.scalar_vivado_hexfile(root,"rsqrt_table",rsqrt,32),N=len(cases))
    bench=pin(a.kv260/"rtl/fixed_scalar_tb.sv",BENCH_PIN).decode()
    baseline=a.kv260/"variants/prefill-skip-v1/materialise.py"
    pin(baseline, BASELINE_GENERATOR)
    generate=runpy.run_path(str(baseline))["materialise"]
    streams=[]
    for mode,steps in (("control",64),("candidate",16)):
        build=root/mode
        (generate if mode=="control" else materialise)(a.kv260,build)
        testbench=build/"fixed_scalar_tb.sv"
        testbench.write_text(reset_bench(bench,steps))
        binary=build/"obj/scalar"
        run([str(tool/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","--top-module","fixed_scalar_tb",
             "-j","2","--Mdir",str(binary.parent),"-o","scalar",str(build/"fixed_scalar.sv"),str(testbench)],
            root,env,build/"compile.log",150,deadline)
        parameters={**args,"CSV":build/"cycles.csv","VCD":build/"unused.vcd"}
        run([str(binary),*[f"+{k}={v}" for k,v in parameters.items()]],root,env,build/"simulation.log",600,deadline)
        with parameters["CSV"].open() as stream:
            streams.append(list(csv.DictReader(stream)))
    histogram = {}
    if any(len(rows)!=len(cases)+1 for rows in streams):
        raise ValueError("Scalar request count differs")
    for control,candidate in zip(*streams,strict=True):
        delta=int(control.pop("edges"))-int(candidate.pop("edges"))
        if control!=candidate:
            raise ValueError("Scalar protocol/answer mismatch")
        op=int(control["op"])
        error=int(control["error"])
        operand=int(control["a"])
        saved=48 if op==2 or op==3 and not error and operand>=-1048576 else 288 if op==4 and not error else 0
        if delta!=saved:
            raise ValueError(f"Unexpected latency for op {op}: observed {delta}, expected {saved}")
        key=f"op{op}_delta{delta}"
        histogram[key]=histogram.get(key,0)+1
    report=dict(passed=True, oracle_requests=len(cases), reset_at_each_multiply_step=[64,16],
                latency_deltas=histogram)
    (root/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","model","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    main(parser.parse_args())
