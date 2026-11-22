"""Check paired exponential cutoff, load, drain, and cancellation cases."""

import argparse
import json
from pathlib import Path
import random
import runpy
import sys
import time


def load(path):
    sys.path.insert(0, str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def fixtures(oracle, model, work):
    words = [int(line,16) for line in model.read_text().splitlines()]
    offset = sum((10240,1024,1024,1024,1024,4096,4096,4096,32,32,32,2048))
    table = words[offset:offset+257]
    assert len(words)==29281 and len(table)==257 and table[0]==1<<31
    generator = random.Random(2026111713)
    cases=[]
    for length in (1,2,3,255,256):
        # Produce exact cutoff neighbours while reversing fast/slow lanes.
        query = [16384,256,*[0]*14]*2
        keys=[]
        for i in range(length):
            rows = ((-16384,-1),(0,0),(-16384,0),(-16384,1))
            a,b = rows[i%4], rows[(i^1)%4]
            if length==1:
                a=b=(0,0)
            keys.append([*a,*[0]*14,*b,*[0]*14])
        values=[[generator.randrange(-32768,32768) for _ in range(32)] for _ in range(length)]
        cases.append(dict(q=query,k=keys,v=values,length=length,source="Directed signed cutoff fixture",
                          expected=oracle(query,keys,values,table)))
    assert cases[1]["expected"]["exp"][0][0] == cases[1]["expected"]["exp"][1][1] == 0
    assert cases[-1]["expected"]["scores"][0][0:4] == [-1048577,0,-1048576,-1048575]
    assert all(x>0 for x in cases[-1]["expected"]["exp"][0][1:4])
    (work/"fixtures.json").write_text(json.dumps(dict(cases=cases,table=table),indent=2)+"\n")

    def hexfile(name, values, width=16):
        file=work/(name+".hex")
        file.write_text("".join(f"{v & ((1<<width)-1):0{width//4}x}\n" for v in values))
        return file

    def inputs(key):
        return (v for case in cases for row in [*case[key], *([[0]*32]*(256-case["length"]))] for v in row)

    args=dict(N=len(cases), Q=hexfile("Q",(v for c in cases for v in c["q"])),
              K=hexfile("K",inputs("k")),V=hexfile("V",inputs("v")),
              ANSWERS=hexfile("ANSWERS",(v for c in cases for v in c["expected"]["result"])),
              CLIPS=hexfile("CLIPS",(v for c in cases for v in c["expected"]["clips"]),8),
              LENGTHS=hexfile("LENGTHS",(c["length"] for c in cases)),TABLE=hexfile("TABLE",table,32),
              CSV=work/"events.csv",VCD=work/"waves.vcd")
    return args,cases


def bench(source):
    anchor='        $fclose(csv);$display("PASS attention requests='
    assert source.count(anchor)==1
    source=source.replace(anchor, r"""        // First member cuts off. The second member faults on a missing table.
        prepare(1,0);case_id=-3;launch();
        while(!result_valid)begin tick();@(negedge clk);end
        if(!error || !dut.second_cmd_ready || !dut.scalar_cmd_ready)
            $fatal(1,"Missing table did not drain the paired lanes");
        result_ready=1;tick();@(negedge clk);quiet();
        // Reset while the second lane still computes a valid result.
        prepare(1,1);case_id=-3;launch();
        while(dut.state!=dut.EXP_RETIRE_SECOND)begin tick();@(negedge clk);end
        if(dut.second_result_valid || dut.second_cmd_ready)
            $fatal(1,"Expected a live slow lane beside the retired cutoff");
        clear();
        #1;
        if(!dut.second_cmd_ready || dut.second_result_valid)
            $fatal(1,"Reset left a stale second-lane result");
        // Reject an invalid rewrite, then move a real nonzero table word
        // through the external interface and verify both copies changed.
        prepare(1,1);case_id=-3;
        table_valid=1;table_index=9'd31;table_value=32'h80000001;
        #1;
        if(table_ready)$fatal(1,"Invalid table reload accepted");
        tick();@(negedge clk);
        if(dut.scalar.exp_memory[31]!==exp_table[31] ||
           dut.second_exp.exp_memory[31]!==exp_table[31])
            $fatal(1,"Rejected load changed the table");
        table_value=32'd110005;
        #1;
        if(!table_ready)$fatal(1,"Valid reload refused");
        tick();@(negedge clk);
        if(dut.scalar.exp_memory[31]!==table_value || dut.second_exp.exp_memory[31]!==table_value)
            $fatal(1,"One lane missed a valid table rewrite");
        quiet();
        $display("PASS paired cutoff, second failure drain, paired reset and mirrored table reload");
""" + anchor)
    return source


def main(args):
    kv=args.repo/"hardware/research/inference/implementations/kv260"
    oracle=load(kv/"tools/rtl.py")
    model=load(kv/"variants/scalar-mul-v1/test_model.py")
    env=model["simulator"](args.verilator,kv)
    run=model["run"]
    deadline=time.monotonic()+min(350,args.deadline_epoch-time.time())
    w=args.output
    w.mkdir()
    plus,cases=fixtures(oracle["attention_oracle"],args.model,w)
    tb=w/"attention_tb.sv"
    tb.write_text(bench((kv/"rtl/attention_tb.sv").read_text()))
    exe=w/"obj/simulation"
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","attention_tb","--Mdir",str(exe.parent),"-o","simulation",
         *[str(args.rtl/(name+".sv")) for name in ("fixed_scalar","kv_cache","attention")],str(tb)],
        w,env,w/"compile.log",150,deadline)
    run([str(exe),*[f"+{k}={v}" for k,v in plus.items()]],w,env,w/"simulation.log",120,deadline)
    assert "PASS paired cutoff" in (w/"simulation.log").read_text()
    result=oracle["attention_check_trace"](plus["CSV"],cases)
    result.update(paired_cancel_probes=1,paired_fault_probes=1,table_rewrite_checks=2)
    (w/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(result,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("repo","verilator","rtl","model","output"):
        p.add_argument("--"+name,type=lambda s:Path(s).resolve(),required=True)
    p.add_argument("--deadline-epoch",type=float,required=True)
    main(p.parse_args())
