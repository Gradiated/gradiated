"""Check exact signed row arithmetic, read addresses, stalls and reset."""

import argparse
import json
from pathlib import Path
from random import Random
import re
import time

from materialise_projections import checked, materialise
from replay_projections import load

CASES=(
    ("qkv",96,15,"mac32_read_ahead"),
    ("output",32,16,"dense_attention_output_read_ahead"),
    ("gate",128,16,"dense_ff_gate_up_read_ahead"),
    ("up",128,15,"dense_ff_gate_up_read_ahead"),
)
BASE_BENCH="88e8ea442d8a2a91a1a586d6f650f3ac80b9169a30bbca97663b6b350157d6b4"


def hexfile(path,values,bits):
    path.write_text("".join(f"{value&((1<<bits)-1):0{(bits+3)//4}x}\n" for value in values))


def fixtures(root,rows,shift):
    rng=Random(2026111922+rows+shift)
    x=[16384,32767,-32768,1,-1]+[rng.randrange(-32768,32768) for _ in range(27)]
    matrices=[]
    terms=[]
    results=[]
    clipped=ties=0
    for row in range(rows):
        w=[rng.randrange(-32768,32768) for _ in x]
        if row<4:
            w=[0]*32
            w[0]=(1,3,-1,-3)[row]*(1<<(shift-15))
        if row in (4,5):
            w=[32767 if (a>=0)==(row==4) else -32768 for a in x]
        if row==rows-1:
            w[0],w[-1]=-32768,32767
        matrices.extend(w)
        total=0
        for a,b in zip(x,w,strict=True):
            p=a*b
            total+=p
            assert -(1<<47)<=total<1<<47
            terms.append(((p&0xffffffff)<<48)|(total&((1<<48)-1)))
        q,r=divmod(total,1<<shift)
        half=1<<(shift-1)
        rounded=q+int(r>half or (r==half and q&1))
        value=max(-32768,min(32767,rounded))
        ties+=r==half
        clipped+=rounded!=value
        results.append(((rounded!=value)<<16)|(value&0xffff))
    assert ties>=4 and clipped>=2
    folder=root/f"32x{rows}"
    folder.mkdir()
    for name,values,bits in (("inputs",x,16),("weights",matrices,16),("terms",terms,80),("results",results,17)):
        hexfile(folder/(name+".hex"),values,bits)
    return dict(terms_per_pass=len(terms),ties_per_pass=ties,clipped_rows_per_pass=clipped)


def mac_ports(module,side,arm):
    return f"""
    {module} #(.ROWS(OUTPUTS)) {side}(
        .clk,.reset,.load_valid(weight_valid),.load_ready(weight_ready[{arm}]),
        .load_address(weight_address[4:0]),.load_row(weight_row[ROW_BITS-1:0]),.load_input(input_value),
        .load_weight(weight_value),.start,.start_ready(start_ready[{arm}]),.busy(busy[{arm}]),
        .result_valid(result_valid[{arm}]),.result_ready(result_ready[{arm}]),
        .result(result[{arm}]),.result_row(result_row[{arm}]),.saturated(saturated[{arm}]),
        .step_valid(step_valid[{arm}]),.step_index(step_index[{arm}]),.step_row(step_row[{arm}]),
        .step_input(step_input[{arm}]),.step_weight(step_weight[{arm}]),.step_product(step_product[{arm}]),
        .step_sum(step_sum[{arm}])
    );
"""


def bench(base,scope,rows,shift,candidate):
    core=base[:base.index("module ff_down_tb;")]
    core=core.replace("INPUTS=128, OUTPUTS=32","INPUTS=32, OUTPUTS="+str(rows),1)
    core=core.replace(".SHIFT(15)",f".SHIFT({shift})")
    core=core.replace("dense_ff_down_pipeline",candidate)
    core=core.replace("if (INPUTS==128)","if (INPUTS==32)")
    core=core.replace("for (int phase=0; phase<3; phase++)","for (int phase=0; phase<6; phase++)")
    core=core.replace("""            1: wait (step_valid[1] && step_index[1]==1);
            2: wait (result_valid[1]);""","""            1: wait (step_valid[1] && step_index[1]==0);
            2: wait (step_valid[1] && step_index[1]==30);
            3: wait (step_valid[1] && step_index[1]==31);
            4: wait (result_valid[1]);
            5: begin
                wait (result_valid[1]);
                @(negedge clk); result_ready[1]=1;
                @(posedge clk); #1;
                if (candidate.state!=3'd1) $fatal(1,"Row boundary did not return to prime");
            end""")
    if scope=="qkv":
        core=core.replace("    wire [8:0] result_row[2], step_row[2];",
                          "    localparam int ROW_BITS=$clog2(OUTPUTS);\n"
                          "    wire [ROW_BITS-1:0] result_row[2], step_row[2];")
        core=core.replace("    wire [7:0] step_index[2];","    wire [4:0] step_index[2];")
        start=core.index("    dense #(")
        stop=core.index("    localparam int TERMS")
        core=(core[:start]+mac_ports("mac32","control",0)+mac_ports(candidate,"candidate",1)
              +"    assign input_ready=weight_ready;\n\n"+core[stop:])
        start=core.index("        @(negedge clk);\n        input_valid = 1; input_address")
        stop=core.index("        input_valid = 0; weight_row",start)
        core=core[:start]+"        @(negedge clk);\n"+core[stop:]
    position=core.index("    localparam int TERMS")
    core=core[:position]+"""
    always @(posedge clk) if (!reset) begin
        if (candidate.advance_mac &&
            (candidate.state!=3'd2 || int'(candidate.address)>=INPUTS-1 ||
             int'(candidate.read_address)!=int'(candidate.address)+1))
            $fatal(1,"Candidate crossed or wrapped the current row");
        if (candidate.state==3'd1 && (candidate.advance_mac || candidate.read_address!=0))
            $fatal(1,"Candidate primed a non-first coordinate");
        if (candidate.state==3'd4 && candidate.advance_mac)
            $fatal(1,"Candidate fetched a new pair while holding a row");
    end
"""+core[position:]
    return core+"""
module projection_tb;
    wire done;
    down_projection_check check_projection(done);
    initial begin
        wait (done);
        $finish;
    end
    initial begin #50000000; $fatal(1,"Directed projection simulation timed out"); end
endmodule
"""


def main(args):
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    model=load(kv260/"variants/scalar-mul-v1/test_model.py")
    env=model["simulator"](args.verilator,kv260)
    run=model["run"]
    out=args.output
    out.mkdir()
    rtl=out/"candidate"
    materialise(kv260,rtl,"projections-read-ahead-v1")
    materialise(kv260,out/"control","control")
    base=checked(kv260/"variants/ff-down-pipeline-v1/down_tb.sv",BASE_BENCH).decode()
    deadline=time.monotonic()+750
    values={}
    for scope,rows,shift,candidate in CASES:
        work=out/scope
        work.mkdir()
        coverage=fixtures(work,rows,shift)
        tb=work/"projection_tb.sv"
        tb.write_text(bench(base,scope,rows,shift,candidate))
        # Use the real scoped primitive, excluding unrelated clients from this unit bench.
        file={"qkv":"frontend","output":"transformer","gate":"feedforward","up":"feedforward"}[scope]
        source=(rtl/(file+".sv")).read_text()
        marker="module "+candidate+" #("
        assert source.count(marker)==1
        compiled=work/(candidate+".sv")
        compiled.write_text("`timescale 1ns/1ps\n"+source[source.index(marker):])
        inherited=rtl/("mac32.sv" if scope=="qkv" else "dense.sv")
        executable=work/"obj/simulation"
        run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
             "--top-module","projection_tb","--Mdir",str(executable.parent),"-o","simulation",
             str(inherited),str(compiled),str(tb)],work,env,work/"compile.log",150,deadline)
        run([str(executable),f"+FIXTURES={work}"],work,env,work/"simulation.log",150,deadline)
        log=(work/"simulation.log").read_text()
        passes=re.findall(r"DOWN_PASS (.+)",log)
        assert len(passes)==8 and log.count("DOWN_RESET_PASS")==6
        values[scope]=dict(coverage,rows=rows,shift=shift,exact_paired_passes=8,reset_probes=6,
                           control_clocks=66*rows,candidate_clocks=35*rows)
        print(scope,values[scope],flush=True)
    (out/"summary.json").write_text(json.dumps(dict(all_exact=True,scopes=values),indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    main(parser.parse_args())
