"""Exercise the candidate against the existing integer attention oracle and cache stimuli."""

import json
from pathlib import Path
import random
import re
import runpy
import sys

from materialise_attention import checked, once

HERE = Path(__file__).resolve().parent


def inputs(oracle, model, out):
    # Banks 0–11 precede the 257-word exponential table at bank 13.
    sizes = (10240, 1024, 1024, 1024, 1024, 4096, 4096, 4096, 32, 32, 32, 2048)
    words = [int(line, 16) for line in model.read_text().splitlines()]
    assert len(words) == 29281
    offset = sum(sizes)
    table = words[offset:offset+257]
    assert table[0] == 2**31 and len(table) == 257
    rng = random.Random(2026111701)
    cases = []
    for length in (1, 2, 17, 256):
        query = [rng.randrange(-2048, 2048) for _ in range(32)]
        keys = [[rng.randrange(-2048, 2048) for _ in range(32)] for _ in range(length)]
        values = [[rng.randrange(-32768, 32768) for _ in range(32)] for _ in range(length)]
        cases.append(dict(source="Deterministic signed fixture", q=query, k=keys, v=values, length=length,
                          expected=oracle(query, keys, values, table)))
    fixture = {"seed": 2026111701, "table_bank": 13, "cases": cases, "table": table}
    (out/"fixtures.json").write_text(json.dumps(fixture,indent=2)+"\n")
    def hexfile(name, values, width=16):
        path = out/(name+".hex")
        path.write_text("".join(f"{value & ((1 << width) - 1):0{width // 4}x}\n" for value in values))
        return path
    padded = lambda case, key: [*case[key], *([[0]*32] * (256-case["length"]))]
    args = dict(N=len(cases), Q=hexfile("Q",(v for c in cases for v in c["q"])),
        K=hexfile("K",(v for c in cases for row in padded(c,"k") for v in row)),
        V=hexfile("V",(v for c in cases for row in padded(c,"v") for v in row)),
        ANSWERS=hexfile("ANSWERS",(v for c in cases for v in c["expected"]["result"])),
        CLIPS=hexfile("CLIPS",(v for c in cases for v in c["expected"]["clips"]),8),
        LENGTHS=hexfile("LENGTHS",(c["length"] for c in cases)), TABLE=hexfile("TABLE",table,32),
        CSV=out/"events.csv", VCD=out/"waves.vcd")
    return args,cases


def bench(source):
    source = once(source,"    assign allow_read=(cycle%4)!=0;",r"""    bit forced_score, forced_value, refused;
    bit score_pending, value_pending;
    int score_refusals=0, value_refusals=0;
    logic [8:0] held_position;
    logic [5:0] held_coordinate;
    wire refuse_score=case_id>=0 && dut.state==5'd3 && cache_read_valid && !forced_score;
    wire refuse_value=case_id>=0 && dut.state==5'd14 && cache_read_valid && !forced_value;
    assign allow_read=(cycle%4)!=0 && !refuse_score && !refuse_value;
    always @(posedge clk) begin
        if (reset) begin
            forced_score <= 0; forced_value <= 0; refused <= 0;
            score_pending <= 0; value_pending <= 0;
        end else begin
            score_pending <= cache_read_valid && cache_read_ready && dut.state==5'd3;
            value_pending <= cache_read_valid && cache_read_ready && dut.state==5'd14;
            if (refused && (!cache_read_valid || cache_read_position != held_position ||
                           cache_read_coordinate != held_coordinate || !step_valid ||
                           (dut.state != 5'd1 && dut.state != 5'd12)))
                $fatal(1,"MAC refusal did not preserve next address or finish the old term");
            refused <= refuse_score || refuse_value;
            if (refuse_score || refuse_value) begin
                if (cache_read_ready) $fatal(1,"Directed refusal did not block request");
                held_position <= cache_read_position;
                held_coordinate <= cache_read_coordinate;
            end
            if (refuse_score) begin forced_score <= 1; score_refusals++; end
            if (refuse_value) begin forced_value <= 1; value_refusals++; end
        end
    end""")
    anchor='        $fclose(csv);$display("PASS attention requests=%0d heads=2 coordinates=32 reset_probes=4",passed);$finish;'
    return once(source,anchor,r"""        // Cancel one accepted lookahead per pass while the paired response is pending.
        for(integer probe=0;probe<2;probe=probe+1)begin
            integer elapsed;
            prepare(1,1);case_id=-3;launch();elapsed=0;
            while(!(backing_output_valid && (probe==0 ? score_pending : value_pending)))begin
                tick();@(negedge clk);elapsed++;
                if(elapsed>400000)$fatal(1,"No pending lookahead response");
            end
            clear();
            if (backing_output_valid || cache_read_valid || cache_output_ready)
                $fatal(1,"Old response escaped cancellation");
            run_case(1,-3);
        end
        if (score_refusals!=cases+4 || value_refusals!=cases-1)
            $fatal(1,"Missing directed MAC request refusals");
        $fclose(csv);
        $display("PASS attention requests=%0d heads=2 coordinates=32 reset_probes=6 score_refusals=%0d value_refusals=%0d",
                 passed,score_refusals,value_refusals);
        $finish;""")


def run(args, root, kv260, rtl, model, helper, env, deadline):
    path=kv260/"tools/rtl.py"
    spec=json.loads((HERE/"manifest.json").read_bytes())
    checked(path,spec["oracle_sha256"])
    sys.path.insert(0,str(path.parent))
    try:
        oracle=runpy.run_path(str(path))
    finally:
        sys.path.pop(0)
    root.mkdir()
    plusargs,cases=inputs(oracle["attention_oracle"],model,root)
    target=root/"attention_tb.sv"
    target.write_text(bench(checked(kv260/"rtl/attention_tb.sv",spec["component_bench_sha256"]).decode()))
    binary=root/"obj/simulation"
    helper["run"]([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
                   "--top-module","attention_tb","--Mdir",str(binary.parent),"-o","simulation",
                   *[str(rtl/(name+".sv")) for name in ("fixed_scalar","kv_cache","attention")],str(target)],
                  root,env,root/"compile.log",150,deadline)
    log=root/"simulation.log"
    helper["run"]([str(binary),*[f"+{key}={value}" for key,value in plusargs.items()]],root,env,log,120,deadline)
    expected=f"PASS attention requests={len(cases)+6} heads=2 coordinates=32 reset_probes=6 score_refusals={len(cases)+4} value_refusals={len(cases)-1}"
    if expected not in log.read_text().splitlines():
        raise ValueError("Component gates did not pass")
    observed=oracle["attention_check_trace"](plusargs["CSV"],cases)
    observed.update(directed_score_refusals=len(cases)+4,directed_value_refusals=len(cases)-1,
                    pending_lookahead_reset_probes=2)
    (root/"counts.json").write_text(json.dumps(observed,indent=2,sort_keys=True)+"\n")
    return observed
