"""Check probability edge cases, generic fallback, and attention control."""

import argparse
import json
from pathlib import Path
import random
import runpy
import time

from materialise_probability_div import HERE, checked, materialise
from replay_probability import load_model


def scalar_fixtures(oracle, model, folder):
    words = [int(word, 16) for word in model.read_text().splitlines()]
    offset = sum((10240, 1024, 1024, 1024, 1024, 4096, 4096, 4096, 32, 32, 32, 2048))
    exp, rsqrt = words[offset:offset+257], words[offset+257:]
    assert len(words)==29281 and len(exp)==257 and len(rsqrt)==256
    for name, values in (("exp", exp), ("rsqrt", rsqrt)):
        (folder/(name+".hex")).write_text("".join(f"{word:08x}\n" for word in values))
    rng = random.Random(2026111918)
    bounds = (1, 2, 3, 32767, 32768, 32769, 65535, 65536, 65537, 1<<31,
              (1<<31)+1, (1<<39)-1, 1<<39)
    prob = {(e, s) for s in bounds for e in (0, 1, min(1<<31, s-1), min(1<<31, s))}
    prob.update((e, s) for e in (1, 3, 32767, 32769, 65535)
                for s in (65535, 65536, 65537))
    for _ in range(4096):
        e = rng.randrange((1<<31)+1)
        s = rng.randrange(max(1,e), (1<<39)+1)
        prob.add((e, s))
    inputs = [(1,e<<15,s,0) for e,s in sorted(prob)]
    inputs.extend((1,n,d,0) for n in (0,65535,65536,65537,131072,(1<<63)-1,-(1<<63))
                  for d in (1,2,3,-1,0,1<<62,(1<<62)+1))
    inputs.extend((row["op"],row["a"],row["b"],row["shift"])
                  for row in oracle["scalar_vivado_cases"](exp,rsqrt))
    inputs.extend((op,0,0,0) for op in (5,6,7))
    counts = dict(probability_cases=len(prob), shortened=0, full=0, rejected=0,
                  nondivision=0, ties_even=0, ties_odd=0, zero_exponential=0, full_scale=0)
    rows = []
    widths = (4,64,64,8,64,8,4,64,64)
    for index, (op,a,b,shift) in enumerate(inputs):
        try:
            result, exponent = oracle["scalar_reference"](op,a,b,shift,exp,rsqrt)
            error = 0
        except (OverflowError, ValueError):
            result = exponent = 0
            error = 1
        q = r = delta = 0
        if op==1 and not error:
            q, r = divmod(abs(a),b)
            delta = 24 if 0<=a and (a>>16)<b else 0
            counts["shortened" if delta else "full"] += 1
            if index < len(prob):
                assert result == q + (2*r>b or (2*r==b and q%2==1))
                assert delta==24
                counts["zero_exponential"] += a == 0
                counts["full_scale"] += a == b<<15
                counts["ties_even"] += 2*r == b and q%2==0
                counts["ties_odd"] += 2*r == b and q%2==1
        elif op==1:
            counts["rejected"] += 1
        else:
            counts["nondivision"] += 1
        values = (op,a,b,shift,result,exponent,error,q,r)
        rows.append(" ".join(f"{value & ((1<<bits)-1):0{bits//4}x}"
                             for value,bits in zip(values,widths,strict=True))+f" {delta}\n")
    assert all(counts.values())
    (folder/"scalar.hex").write_text("".join(rows))
    return len(rows), counts


def attention_bench(pair, original):
    bench = pair["bench"](original)
    marker = '        $fclose(csv);$display("PASS attention requests='
    assert bench.count(marker)==1
    return bench.replace(marker, r"""        // A valid table write can make every exponential zero. The old
        // probability guard must reject a zero sum before any division launches.
        prepare(0,1);case_id=-4;
        for (int j=0; j<2; j++) begin
            table_valid=1;table_index=9'(j);table_value=0;
            #1;if(!table_ready)$fatal(1,"Zero table word refused");
            tick();@(negedge clk);
        end
        table_valid=0;launch();
        while(!result_valid) begin
            if(dut.state==dut.PROB_SEND || dut.state==dut.PROB_WAIT)
                $fatal(1,"Zero sum entered probability division");
            tick();@(negedge clk);
        end
        if(!error || result!=0) $fatal(1,"Zero sum failed to report error");
        result_ready=1;tick();@(negedge clk);quiet();
        // Cancel after the first probability has issued. A clean request
        // must recover independently of the interrupted divider state.
        prepare(0,1);case_id=-4;launch();
        while(dut.state!=dut.PROB_WAIT) begin tick();@(negedge clk);end
        repeat(3) begin tick();@(negedge clk);end
        if(dut.state!=dut.PROB_WAIT || dut.scalar_result_valid)
            $fatal(1,"Reset probe missed active probability division");
        clear();run_case(0,-5);
        $display("PASS zero-sum rejection and in-flight attention probability reset");
""" + marker)


def main(args):
    checked(args.model, "e0c4910071fb1577fea78e1b6cc7474bcfb2d64898713ec945bf1ed8dcc2df43")
    kv260 = args.repo/"hardware/research/inference/implementations/kv260"
    pair = runpy.run_path(str(kv260/"variants/attention-exp-pair-v2/test_directed.py"))
    oracle = pair["load"](kv260/"tools/rtl.py")
    model = load_model(kv260)
    env = model["simulator"](args.verilator,kv260)
    deadline = time.monotonic()+min(350,args.deadline_epoch-time.time())
    out = args.output
    out.mkdir()
    rtl = out/"rtl"
    materialise(kv260,rtl,True)

    def compile_bench(top, work, sources, tb):
        binary = work/"obj/simulation"
        model["run"]([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert",
                      "-Wno-fatal","-j","2","--top-module",top,"--Mdir",str(binary.parent),
                      "-o","simulation",*map(str,sources),str(tb)],work,env,
                     work/"compile.log",150,deadline)
        return binary

    scalar = out/"scalar"
    scalar.mkdir()
    rows, counts = scalar_fixtures(oracle,args.model,scalar)
    scalar_bin = compile_bench("probability_scalar_tb",scalar,[rtl/"attention.sv"],HERE/"scalar_tb.sv")
    model["run"]([str(scalar_bin),f"+FIXTURES={scalar}",f"+ROWS={rows}"],scalar,env,
                 scalar/"simulation.log",120,deadline)
    assert f"PASS scalar: {rows} " in (scalar/"simulation.log").read_text()
    print("Exact scalar directed fixtures",rows,counts,flush=True)

    attention = out/"attention"
    attention.mkdir()
    params,cases = pair["fixtures"](oracle["attention_oracle"],args.model,attention)
    bench = attention/"attention_tb.sv"
    bench.write_text(attention_bench(pair,(kv260/"rtl/attention_tb.sv").read_text()))
    att_bin = compile_bench("attention_tb",attention,[rtl/"kv_cache.sv",rtl/"attention.sv"],bench)
    model["run"]([str(att_bin),*[f"+{key}={value}" for key,value in params.items()]],attention,
                 env,attention/"simulation.log",120,deadline)
    for marker in ("PASS paired cutoff", "PASS zero-sum rejection", "PASS attention requests=10"):
        assert marker in (attention/"simulation.log").read_text()
    result = oracle["attention_check_trace"](params["CSV"],cases)
    result.update(scalar_fixture_rows=rows,scalar_fixtures=counts,scalar_reset_probes=1,
                  attention_probability_reset_probes=1,attention_zero_sum_rejections=1,
                  paired_cancel_probes=1,paired_fault_probes=1,table_rewrite_checks=2)
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print("Exact directed attention fixtures",result,flush=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo","verilator","model","output"):
        parser.add_argument("--"+name,type=lambda value: Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
