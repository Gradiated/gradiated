"""Check the divider, exact quotient/remainder and the scalar command protocol."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
import runpy
import sys
import time

from test_model import pinned, prior

BENCH_PIN = "cec02c2d6124308edcb2cc4bf637275de15148855675d2f73774d09831230cb2"


def testbench(text, steps, has_finish):
    insertions = (
        ("    task automatic tick;", """    bit tracing_div=0;
    integer request_id, case_id, div_log;
    string div_file;
    logic [63:0] dividend_mag;
    always @(posedge clk) if(!reset && tracing_div && dut.state==5'd2)begin
        if(dut.remaining==7'dSTEPS)dividend_mag=dut.numerator;
        if(dut.remaining==1)
            $fwrite(div_log,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\\n",request_id,case_id,
                    dut.return_state,dut.negative,dut.rounding,dividend_mag,
                    dut.denominator,dut.next_quotient,dut.next_remainder);
    end
    task automatic tick;""".replace("STEPS",str(steps))),
        ("        cmd_op=ops[id][2:0];","        tracing_div=1;request_id=passed;case_id=id;\n        cmd_op=ops[id][2:0];"),
        ("passed=passed+1;","passed=passed+1;tracing_div=0;"),
        ("        $readmemh(opfile,ops,0,cases-1);", """        if(!$value$plusargs("DIVS=%s",div_file))$fatal(1,"Missing divider trace path");
        div_log=$fopen(div_file,"w");
        if(!div_log)$fatal(1,"Cannot open divider trace");
        $readmemh(opfile,ops,0,cases-1);"""),
        ("        // A held output is also cancelled by reset.", """        // Cancel after every possible number of executed divider steps,
        // including after the last radix-4 step before rounding.
        for(integer step=0;step<MAX_RESET;step++)begin
            cmd_valid=1;cmd_op=1;cmd_a= -64'sd123456789;cmd_b=64'sd37;
            #1;if(!cmd_ready)$fatal(1,"Divider reset probe busy");
            tick();@(negedge clk);cmd_valid=0;
            repeat(step)begin tick();@(negedge clk);end
            if(step==STEPS && dut.state!=5'd17)$fatal(1,"Missed final divider rounding stage");
            if(result_valid || cmd_ready)$fatal(1,"Divider retired before reset probe");
            reset=1;tick();
            if(result_valid || error || result!==0 || result_exponent!==0 ||
               cmd_ready || table_ready)$fatal(1,"Reset did not abort division");
            @(negedge clk);reset=0;cmd_valid=1;cmd_op=1;cmd_a= -64'sd15;cmd_b=64'sd6;
            #1;if(!cmd_ready)$fatal(1,"New divide rejected after reset");
            tick();@(negedge clk);cmd_valid=0;
            while(!result_valid)begin tick();@(negedge clk);end
            if(result!== -64'sd2 || error)$fatal(1,"Bad answer after divider reset");
            result_ready=1;tick();@(negedge clk);result_ready=0;
        end
        // A held output is also cancelled by reset.""".replace("MAX_RESET",str(steps+has_finish)).replace("STEPS",str(steps))),
        ("        $fclose(csv);","        $fclose(div_log);$fclose(csv);"),
    )
    for old,new in insertions:
        if text.count(old)!=1:
            raise ValueError("Unexpected scalar bench")
        text=text.replace(old,new)
    return text


def extra_divides(reference, exp, rsqrt):
    rng=random.Random(0x6432)
    lower,upper=-(1<<63),(1<<63)-1
    ds=(0,1,2,3,4,7,45426,1<<30,3<<30,(1<<61)-1,1<<61,(1<<62)-1,1<<62,(1<<62)+1)
    pairs={(a,b) for a in (lower,lower+1,-upper,-1,0,1,upper-1,upper) for b in ds}
    for b in ds[1:-1]:
        for q in (0,1,2,3,5,7):
            for r in (0,1,max(0,b//2-1),b//2,b//2+1,b-1):
                value=q*b+r
                for sign in (1,-1):
                    if lower<=sign*value<=upper:
                        pairs.add((sign*value,b))
    for _ in range(900):
        b=rng.randrange(1,1<<rng.randrange(1,63))
        q=rng.randrange(0,1<<rng.randrange(1,64))
        magnitude=rng.choice((rng.randrange(0,1<<rng.randrange(1,64)),q*b+rng.randrange(0,b)))
        a=rng.choice((-1,1))*magnitude
        pairs.add((a if lower<=a<=upper else rng.randint(lower,upper),b))
    cases=[]
    for a,b in sorted(pairs):
        try:
            result,exponent=reference(1,a,b,0,exp,rsqrt)
            error=0
        except (ValueError,OverflowError):
            result=exponent=0
            error=1
        cases.append(dict(op=1,a=a,b=b,shift=0,result=result,exponent=exponent,error=error))
    return cases


def main(a):
    helpers,control=prior(a.kv260)
    env=helpers["simulator"](a.verilator.resolve(),a.kv260)
    run=helpers["run"]
    timescale=time.monotonic()+600
    root=a.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.kv260/"tools"))
    import rtl
    words=[int(word,16) for word in a.model.read_text().splitlines()]
    if len(words)!=29281:
        raise ValueError("Unexpected model fixture length")
    exp,rsqrt=words[-513:-256],words[-256:]
    cases=rtl.scalar_vivado_cases(exp,rsqrt)+extra_divides(rtl.scalar_reference,exp,rsqrt)
    random.Random(0x2026).shuffle(cases)
    if len(cases)>4096:
        raise ValueError(f"Scalar fixture count out of bounds: {len(cases)}")
    (root/"cases.json").write_text(json.dumps(dict(cases=cases,exp=exp,rsqrt=rsqrt),indent=2)+"\n")
    flags={key.upper():rtl.scalar_vivado_hexfile(root,key,(c[key] for c in cases),bits)
           for key,bits in (("op",8),("a",64),("b",64),("shift",8),("result",64),("exponent",8),("error",8))}
    flags["ANSWER"]=flags.pop("RESULT")
    flags.update(EXP=rtl.scalar_vivado_hexfile(root,"exp_table",exp,32),
                 RSQRT=rtl.scalar_vivado_hexfile(root,"rsqrt_table",rsqrt,32),N=len(cases))
    original=pinned(a.kv260/"rtl/fixed_scalar_tb.sv",BENCH_PIN).decode()
    new=runpy.run_path(str(Path(__file__).parent/"make_division.py"))
    traces=[]
    streams=[]
    for arm,generate,steps,finish in (("control",control,64,False),
                                       ("candidate",new["materialise"],new["DIV_STEPS"],True)):
        out=root/arm
        generate(a.kv260,out)
        bench=out/"fixed_scalar_tb.sv"
        bench.write_text(testbench(original,steps,finish))
        binary=out/"obj/scalar"
        params={**flags,"CSV":out/"cycles.csv","DIVS":out/"divisions.csv","VCD":out/"unused.vcd"}
        run([str(a.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","--top-module",
             "fixed_scalar_tb","-j","2","--Mdir",str(binary.parent),"-o","scalar",
             str(out/"fixed_scalar.sv"),str(bench)],root,env,out/"compile.log",150,timescale)
        run([str(binary),*[f"+{k}={v}" for k,v in params.items()]],root,env,out/"simulation.log",600,timescale)
        traces.append(params["DIVS"].read_bytes())
        with params["CSV"].open() as stream:
            streams.append(list(csv.DictReader(stream)))
    if traces[0]!=traces[1] or not traces[0]:
        raise ValueError("Raw division traces differ")
    count=Counter()
    origins=Counter()
    for sample in traces[0].splitlines():
        visit,case,ret,neg,rounding,n,d,q,remainder=map(int,sample.split(b","))
        if not 0<=visit<len(streams[0]) or int(streams[0][visit]["case"])!=case:
            raise ValueError("Divider trace has the wrong command ordinal")
        if not 0<=case<len(cases) or not 0<d<=1<<62 or divmod(n,d)!=(q,remainder):
            raise ValueError("Raw quotient or remainder differs from integer oracle")
        if cases[case]["op"]==1 and (n,d,neg,rounding)!=(abs(cases[case]["a"]),cases[case]["b"],int(cases[case]["a"]<0),1):
            raise ValueError("Accepted signed division inputs differ")
        count[visit]+=1
        origins[ret]+=1
    if any(len(rows)!=len(cases)+1 for rows in streams):
        raise ValueError("Missing scalar command")
    for visit,(x,y) in enumerate(zip(*streams,strict=True)):
        delta=int(x.pop("edges"))-int(y.pop("edges"))
        if x!=y or delta!=31*count[visit]:
            raise ValueError("Scalar command or latency differs")
    report=dict(passed=True,mixed_cases=len(cases),direct_divide_cases=sum(c["op"]==1 for c in cases),
                exact_division_steps=sum(origins.values()),return_states=origins,
                reset_offsets=[64,33],cycles_saved_per_completed_division=31)
    (root/"result.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","model","output"):
        p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
