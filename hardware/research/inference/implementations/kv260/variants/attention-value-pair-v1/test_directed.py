"""Check bank ports, signed attention terms, stalled ordering and cancellation."""

import argparse
import csv
import json
from pathlib import Path
from random import Random
import time

from materialise_value_pair import HERE, checked, materialise
from replay_value_pair import load

MODEL_PIN="e0c4910071fb1577fea78e1b6cc7474bcfb2d64898713ec945bf1ed8dcc2df43"
LENGTHS=(1,2,3,16,17,64,128,255,256)


def fixtures(out,oracle,model):
    words=[int(line,16) for line in checked(model,MODEL_PIN).splitlines()]
    offset=sum((10240,1024,1024,1024,1024,4096,4096,4096,32,32,32,2048))
    table=words[offset:offset+257]
    assert len(words)==29281 and table[0]==1<<31 and len(table)==257
    random=Random(2026111923)
    cases=[]
    for d in LENGTHS:
        query=[0]*32 if d<=3 else [16384,256,*[0]*14]*2
        keys=[]
        for p in range(d):
            edge=((-16384,-1),(0,0),(-16384,0),(-16384,1))
            keys.append([*edge[p%4],*[0]*14,*edge[(p^1)%4],*[0]*14])
        if d==2:
            values=[[0]*32, [1,3,-1,-3]*8]
        elif d in (1,3):
            values=[[-32768,32767]*16 for _ in range(d)]
        else:
            values=[[random.randrange(-32768,32768) for _ in range(32)] for _ in range(d)]
        cases.append(dict(q=query,k=keys,v=values,length=d,source="Directed synthetic attention fixture",
                          expected=oracle(query,keys,values,table)))
    assert cases[0]["expected"]["prob"]==[[32768],[32768]]
    assert cases[1]["expected"]["result"][:4]==[0,2,0,-2]
    assert cases[2]["expected"]["clips"]==[1]*32

    def write(name,values,bits=16):
        path=out/(name+".hex")
        path.write_text("".join(f"{v&((1<<bits)-1):0{bits//4}x}\n" for v in values))
        return path

    def bank(name):
        return (v for case in cases for row in [*case[name],*([[0]*32]*(256-case["length"]))] for v in row)

    params=dict(N=len(cases), Q=write("Q",(v for case in cases for v in case["q"])),
                K=write("K",bank("k")),V=write("V",bank("v")),
                ANSWERS=write("ANSWERS",(v for case in cases for v in case["expected"]["result"])),
                CLIPS=write("CLIPS",(v for case in cases for v in case["expected"]["clips"]),8),
                LENGTHS=write("LENGTHS",LENGTHS),TABLE=write("TABLE",table,32))
    (out/"fixtures.json").write_text(json.dumps(dict(cases=cases,table=table),indent=2)+"\n")
    return cases,params


def testbench(base,paired):
    base=base.replace('    task automatic clear;',"""    integer refused_value_requests=0, delayed_value_responses=0, total_held_value_outputs=0;
    always @(posedge clk) if (!reset) begin
        if ((dut.state==5'd12 || dut.state==5'd14) && cache_read_valid && !cache_read_ready)
            refused_value_requests++;
        if (dut.state==5'd13 && !cache_output_valid) delayed_value_responses++;
        if (result_valid && !result_ready && !error) total_held_value_outputs++;
    end
    task automatic clear;""")
    end='        $fclose(csv);$display("PASS attention requests='
    assert base.count(end)==1
    inserted="""
        if(refused_value_requests==0 || delayed_value_responses==0 || total_held_value_outputs==0)
            $fatal(1,"Missing directed backpressure coverage");
        $display("VALUE_STALLS %0d %0d %0d",refused_value_requests,delayed_value_responses,total_held_value_outputs);
"""
    if not paired:
        return base.replace(end,inserted+end)
    base=base.replace("    attention dut(.*);", """    logic cache_read_pair, cache_output_pair, backing_output_pair;
    logic signed [15:0] cache_output_v_second, backing_output_v_second;
    logic step_pair_valid;
    logic signed [15:0] step_pair_weight;
    logic signed [32:0] step_pair_product;
    logic signed [47:0] step_pair_sum;
    bit corrupt_pair=0, corrupt_coord=0;
    assign cache_output_pair=backing_output_pair ^ corrupt_pair;
    assign cache_output_v_second=backing_output_v_second;
    attention_value_pair dut(.*);""")
    base=base.replace("assign cache_output_coordinate=backing_output_coordinate;",
                      "assign cache_output_coordinate=backing_output_coordinate ^ {4'd0,corrupt_coord};")
    base=base.replace("    kv_cache backing(","    kv_cache_value_pair backing(")
    base=base.replace(".read_coordinate(cache_read_coordinate),",".read_coordinate(cache_read_coordinate),.read_pair(cache_read_pair),")
    base=base.replace(".output_v(backing_output_v),.token_count(token_count),",
                      ".output_v(backing_output_v),.output_v_second(backing_output_v_second),\n"
                      "        .output_pair(backing_output_pair),.token_count(token_count),")
    base=base.replace("        if(score_valid)$fwrite",r'''        if(step_pair_valid) begin
            if(!step_valid || !step_mode || step_coordinate[0])
                $fatal(1,"Second lane lost alignment with the first");
            $fwrite(csv,"C,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,0,0,0\n",
                case_id,cycle,step_head,step_position,int'(step_coordinate)+1,
                step_input,step_pair_weight,step_pair_product,step_pair_sum);
        end
        if(score_valid)$fwrite''')
    return base.replace(end,inserted+(HERE/"value_probe.svh").read_text()+end)


def canonical_trace(src,dest,paired):
    with src.open() as stream:
        reader=csv.DictReader(stream)
        header=reader.fieldnames
        events={}
        for row in reader:
            label=int(row["case"])
            if label>=0:
                events.setdefault(label,[]).append(row)
    with dest.open("w") as stream:
        writer=csv.DictWriter(stream,header)
        writer.writeheader()
        for label,rows in events.items():
            value=[r for r in rows if r["kind"]=="C"]
            checks={}
            for row in value:
                key=(int(row["head"]),int(row["coordinate"]))
                position=int(row["position"])
                assert position==checks.get(key,0),(label,key,position)
                checks[key]=position+1
            if paired:
                for even,odd in zip(value[::2],value[1::2],strict=True):
                    assert (even["cycle"],even["head"],even["position"])==(odd["cycle"],odd["head"],odd["position"])
                    assert int(even["coordinate"])%2==0 and int(odd["coordinate"])==int(even["coordinate"])+1
            ordered=iter(sorted(value,key=lambda r:(int(r["head"]),int(r["coordinate"]),int(r["position"]))))
            writer.writerows(next(ordered) if row["kind"]=="C" else row for row in rows)


def invoke(args):
    kv=args.repo/"hardware/research/inference/implementations/kv260"
    model=load(kv/"variants/scalar-mul-v1/test_model.py")
    oracle=load(kv/"tools/rtl.py")
    env=model["simulator"](args.verilator,kv)
    run=model["run"]
    out=args.output
    out.mkdir()
    corpus=out/"fixtures"
    corpus.mkdir()
    cases,params=fixtures(corpus,oracle["attention_oracle"],args.model)
    deadline=time.monotonic()+700

    def simulate(work,top,sources,plus):
        exe=work/"obj/simulation"
        run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
             "--top-module",top,"--Mdir",str(exe.parent),"-o","simulation",*map(str,sources)],
            work,env,work/"compile.log",180,deadline)
        run([str(exe),*[f"+{k}={v}" for k,v in plus.items()]],work,env,work/"simulation.log",160,deadline)
        return (work/"simulation.log").read_text()

    results={}
    for arm in ("control","candidate"):
        work=out/arm
        work.mkdir()
        rtl=work/"rtl"
        materialise(kv,rtl,arm)
        paired=arm=="candidate"
        bench=work/"attention_tb.sv"
        bench.write_text(testbench((kv/"rtl/attention_tb.sv").read_text(),paired))
        log=simulate(work,"attention_tb",[rtl/"attention.sv",rtl/"kv_cache.sv",bench],
                     dict(params,CSV=work/"events.csv",VCD=work/"waves.vcd"))
        assert f"PASS attention requests={len(cases)+4+int(paired)}" in log
        canonical=work/"canonical.csv"
        canonical_trace(work/"events.csv",canonical,paired)
        results[arm]=oracle["attention_check_trace"](canonical,cases)
        _,refusals,delays,holds=next(line for line in log.splitlines() if line.startswith("VALUE_STALLS")).split()
        results[arm].update(request_refusals=int(refusals),response_delays=int(delays),held_outputs=int(holds))
        print(arm,results[arm],flush=True)
        if paired:
            assert "PASS paired value tag, coordinate, pending odd result reset and recovery" in log
    work=out/"cache"
    work.mkdir()
    log=simulate(work,"cache_pair_tb",[out/"candidate/rtl/kv_cache.sv",HERE/"cache_pair_tb.sv"],{})
    assert "PASS pair cache: 8192 scalar reads, 4096 paired reads" in log
    summary=dict(all_exact=True,arms=results,depths=LENGTHS,full_scale_probability=True,signed_minimum_value=True,
                 signed_ties=True,clipping=True,cache_ordered_writes=8192,scalar_cache_reads=8192,paired_cache_reads=4096,
                 wrong_pair_or_coordinate_probes=2,pending_odd_reset_probes=1,pending_cache_reset_probes=1)
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","model","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    invoke(parser.parse_args())
