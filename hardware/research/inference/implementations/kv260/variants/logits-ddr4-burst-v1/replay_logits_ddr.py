"""Replay exact legacy and DDR-fed logits, with phase and AXI accounting."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
EXTRA = 7040
PROFILE = [320,2560,EXTRA,320,3840,1680+EXTRA]
FROZEN_IMAGE = "698df2e177b8e478088fffe9b02af09cd10c9ac0afbe252f3b031f133262e055"


def packed_weights(oracle, target):
    words = [int(line,16) for line in (oracle/"model.hex").read_text().splitlines()]
    assert sha256(struct.pack(f"<{len(words)}I",*words)).hexdigest() == FROZEN_IMAGE
    grid = [words[(group*8+lane)*32+coordinate]
            for group in range(40) for coordinate in range(32) for lane in range(8)]
    packed = struct.pack("<10240H",*grid)
    target.write_text("".join(f"{beat:016x}\n" for beat, in struct.iter_unpack("<Q",packed)))
    return sha256(packed).hexdigest()


def bench(prior, replace_once, candidate):
    original = (prior/"autonomous_core_tb.sv").read_text()
    base = original.split("// Observe each completed position",1)[0]
    assert len(base) < len(original) and "endmodule" not in base
    if not candidate:
        return base+"\nendmodule\n"
    model = (HERE/"axi_logits_model.svh").read_text()
    fault = (HERE/"logits_fault_cases.svh").read_text()
    changes = (
        ("    axi_transformer dut (.*);",model+"\n"+fault+"\n    axi_transformer dut (.*);"),
        ("        // Original full-score host interface remains usable before autonomous mode.",
         """        check_read(8'h8c,32'h44445233);
        check_read(8'h64,8);
        write_reg(8'h64,1,4'hf,0,0,SLVERR);
        write_reg(8'h10,256,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE+64,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE+8,4'hf,0,0,SLVERR);
        write_reg(8'h60,DDR_BASE,4'hf,0,0,OKAY);
        check_read(8'h60,DDR_BASE);
        write_reg(8'h64,1,4'hf,0,0,OKAY);
        check_read(8'h64,1);
        write_reg(8'h60,DDR_BASE,4'hf,0,0,SLVERR);
        if ($value$plusargs("FAULT=%d",injected_fault) && injected_fault!=0) qualify_fault();
        if ($value$plusargs("PERTURB=%d",perturb) && perturb) begin
            // Token 256 is also BOS. It still embeds from the original on-chip
            // weight row, while its separately packed score row is all zero.
            if (scores[256] == 0) $fatal(1,"Original BOS score 256 must differ");
            scores[256] = 0;
            for (int coordinate=0;coordinate<32;coordinate++)
                matrix[(32*32+coordinate)*2][15:0] = 0;
            run_bos(0);
            check_read(8'h68,20480);
            check_read(8'h6c,320);
            check_read(8'h70,2560);
            $display("PASS independent tied-weight perturbation");
            $finish;
        end
        // Original full-score host interface remains usable before autonomous mode."""),
        ("        polls=0;status=0;", """        write_reg(8'h64,0,4'hf,0,0,SLVERR);
        polls=0;status=0;"""),
        ("        check_read(8'h44,0);read_reg(8'h40,2,SLVERR,data);",
         """        check_read(8'h44,0);read_reg(8'h40,2,SLVERR,data);
        check_read(8'h64,1);
        check_read(8'h68,32'(20480*logit_starts));
        check_read(8'h6c,32'(320*logit_starts));
        check_read(8'h70,32'(2560*logit_starts));
        check_read(8'h74,0);
        check_read(8'h78,32'(7040*logit_starts));
        check_read(8'h7c,32'(320*logit_starts));
        check_read(8'h80,32'(3840*logit_starts));
        check_read(8'h84,32'(logit_starts));
        check_read(8'h88,32'(8720*logit_starts));
        write_reg(8'h64,0,4'hf,0,0,OKAY);
        check_read(8'h64,8);
        write_reg(8'h64,1,4'hf,0,0,OKAY);"""),
    )
    for start,end in changes:
        base = replace_once(base,start,end)
    return base+"\nendmodule\n"


def audit(folder, previous, case, ref, parse, candidate):
    assert (folder/"bos.csv").read_bytes() == (previous/case/"bos.csv").read_bytes()
    timing = parse["get_phases"](folder/"phases.txt")
    cache = parse["cache"](folder/"cache.kv")
    old_cache = parse["cache"](previous/case/"cache.kv")
    score_invocations = ref["done"]["positions"]-ref["prefix"]["positions"]+1
    extra = EXTRA if candidate else 0
    for name,boundary in timing.items():
        anchor = ref[name]
        n, cycles, vector = cache[name]
        assert n == old_cache[name][0] == anchor["positions"] and vector == old_cache[name][2]
        added = score_invocations*extra if name=="done" else 0
        assert cycles == anchor["cycles"]+added
        assert boundary["first_valid"] == anchor["first_valid"]
        assert boundary["first"] == anchor["first"]+(extra if anchor["first_valid"] else 0)
        assert boundary["last"] == anchor["last"]+(ref["outputs"]*extra if anchor["first_valid"] else 0)
        assert boundary["done"] == anchor["done"]+added
        assert boundary["phases"] == [old+(added if index==18 else 0) for index,old in enumerate(anchor["phases"])], (case,name)
        boundary.update(positions=n,cycles=cycles)
    if candidate:
        actual = [list(map(int,line.split())) for line in (folder/"ddr-profile.txt").read_text().splitlines()]
        assert actual == [[index,*PROFILE] for index in range(1,score_invocations+1)]
    return timing


def directed_fixture(folder):
    folder.mkdir()
    x=[128]+[((index*20111)%65536)-32768 for index in range(1,32)]
    w=[[(((row+17)*index*9973+row*619)%65536)-32768 for index in range(32)] for row in range(320)]
    w[:4]=[[weight]+[0]*31 for weight in (1,3,-1,-3)]
    w[4]=[32767 if value>=0 else -32768 for value in x]
    w[5]=[-32768 if value>=0 else 32767 for value in x]
    sums, packed, results=[], [], [None]*320
    for group in range(40):
        partial=[0]*8
        for coordinate, activation in enumerate(x):
            for lane in range(8):
                value=w[group*8+lane][coordinate]
                packed.append(value)
                partial[lane]+=activation*value
                sums.append(partial[lane])
        for lane,value in enumerate(partial):
            rounded=round(value/256)
            clipped=max(-32768,min(32767,rounded))
            results[group*8+lane]=(int(clipped!=rounded)<<16)|(clipped & 65535)
    assert results[:6]==[0,2,0,65534,0x17fff,0x18000]
    words=[value for value, in struct.iter_unpack("<Q",struct.pack("<10240h",*packed))]
    for name,bits,values in (("x",16,x),("sums",48,sums),("results",17,results),("weights",64,words)):
        (folder/(name+".hex")).write_text("".join(f"{value&((1<<bits)-1):0{(bits+3)//4}x}\n" for value in values))


def main(args):
    start=time.monotonic()
    deadline=start+1500
    kv=args.kv260
    prior_helper=runpy.run_path(str(kv/"variants/output-projection-ddr4-burst-v1/replay_projection_burst.py"))
    parser=runpy.run_path(str(kv/"variants/attention-exp-pair-v2/replay_pair.py"))
    model=kv/"variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0,str(model.parent))
    try:
        measure=runpy.run_path(str(model))
    finally:
        sys.path.pop(0)
    run=measure["run"]
    env=measure["simulator"](args.verilator,kv)
    args.output.mkdir()
    prior,oracle=prior_helper["previous_run"](args.previous,args.output/"control-fixtures")
    matrix=args.output/"logits.hex"
    results={"matrix_sha256":packed_weights(oracle,matrix)}
    cases=json.loads((prior/"matched.json").read_text())["candidate"]
    spec=json.loads((HERE/"manifest.json").read_text())
    for arm,rtl in (("control",args.control),("candidate",args.candidate)):
        folder=args.output/arm
        folder.mkdir()
        ledger=rtl/"source-manifest.json"
        pins=json.loads(ledger.read_bytes())
        candidate=arm=="candidate"
        if candidate:
            assert all(pins[name]==pin for name,pin in spec["candidate_sources"].items())
        else:
            assert sha256(ledger.read_bytes()).hexdigest()==spec["control_closure_sha256"]
        sources=[rtl/(name+".sv") for name in pins]
        assert all(sha256(f.read_bytes()).hexdigest()==pins[f.stem] for f in sources)
        testbench=folder/"autonomous_core_tb.sv"
        testbench.write_text(bench(prior,prior_helper["replace_once"],candidate))
        exe=folder/"obj/simulation"
        run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
             "--top-module","autonomous_core_tb","--Mdir",str(exe.parent),"-o","simulation",
             *map(str,sources),str(testbench)],folder,env,folder/"compile.log",300,deadline)
        results[arm]={}
        trials=[(case,case,0,0) for case in cases]
        if candidate:
            trials.extend((f"fault-{fault}","bos-only-cap0",fault,0) for fault in range(1,10))
            trials.append(("perturb","bos-only-cap0",0,1))
        for name,case,fault,perturb in trials:
            ref=cases[case]
            out=folder/name
            out.mkdir()
            cap=int(case.rsplit("-cap",1)[1])
            params=dict(MODEL=oracle/"model.hex",SCORES=oracle/"bos.hex",INPUT=oracle/case/"input.hex",
                        OUTPUT=oracle/case/"output.hex",ALLSCORES=oracle/case/"scores.hex",
                        CSV=out/"bus.events",RETURNS=out/"bos.csv",PREFIX=ref["prefix"]["positions"],
                        OUTPUTS=ref["outputs"],POSITIONS=ref["done"]["positions"],CAP=cap,SKIP=1,CACHE=out/"cache.kv",
                        PHASE=out/"phases.txt",REASON=1 if cap==255 else 2 if case.startswith("full-context") else 4,
                        MATRIX=matrix,FAULT=fault,PERTURB=perturb)
            log=out/"simulation.log"
            run([str(exe),*[f"+{key}={value}" for key,value in params.items()]],out,env,log,180,deadline)
            passed=next(line for line in log.read_text().splitlines() if line.startswith("PASS"))
            if fault or perturb:
                assert ("DDR fault or cancel" if fault else "independent tied-weight perturbation") in passed
                results[arm][name]=passed
            else:
                assert "autonomous_real_core" in passed
                results[arm][name]=audit(out,prior,case,ref,parser,candidate)
            print(arm,name,passed,flush=True)
    arithmetic=args.output/"arithmetic"
    directed_fixture(arithmetic)
    exe=arithmetic/"obj/simulation"
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","logits_arithmetic_tb","--Mdir",str(exe.parent),"-o","simulation",
         str(args.candidate/"transformer.sv"),str(args.candidate/"logits_group_reader.sv"),
         str(HERE/"logits_arithmetic_tb.sv")],arithmetic,env,arithmetic/"compile.log",180,deadline)
    log=arithmetic/"simulation.log"
    run([str(exe),f"+FIXTURE={arithmetic}"],arithmetic,env,log,90,deadline)
    results["arithmetic"]=next(line for line in log.read_text().splitlines() if line.startswith("PASS directed logits arithmetic"))
    print(results["arithmetic"],flush=True)
    (args.output/"matched.json").write_text(json.dumps(results,indent=2)+"\n")
    print(f"Exact replay completed in {time.monotonic()-start:.2f}s")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","previous","control","candidate","output"):
        p.add_argument("--"+name,type=lambda value:Path(value).resolve(),required=True)
    main(p.parse_args())
