"""Matched real-core simulation with pinned reference scores and full KV comparisons."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import struct
from edge_bench import build_edge
from materialise import materialise, replace

BENCH_PIN = "8524956490b9cf2b45cac92c66bae27cfd963b02ba3ed639ab8353aee0356f52"


def testbench(original):
    text = replace(original, "    bit observing=0;",
                   """    integer skip_mode, dumpfile, start_cycle, skip_count, logit_starts=0;
    bit prefix_recorded=0, done_recorded=0;
    string dump_path;
    task automatic dump_cache(input string boundary);
        integer count;
        count=int'(dut.core_context_count);
        $fwrite(dumpfile,"%s %0d %0d\\n",boundary,count,int'($time/10)-start_cycle);
        for(int i=0;i<count*32;i++)
            $fwrite(dumpfile,"%04x %04x\\n",dut.core.front.cache.k_memory[i],dut.core.front.cache.v_memory[i]);
    endtask
    bit observing=0;""")
    text = replace(text, "        if(dut.selected_valid && dut.core_token_ready)begin",
                   """        if(dut.auto_state==4 && !done_recorded)begin
            dump_cache("done");
            done_recorded=1;
        end
        if(skip_mode && seen_inputs>0 && seen_inputs<=skip_count &&
           (dut.core_logit_valid || dut.core_phase==17 || dut.core_phase==18))
            $fatal(1,"Vocabulary projection activity on an omitted position");
        if(dut.core_phase==17)begin
            logit_starts=logit_starts+1;
            if(!prefix_recorded && dut.core_context_count==9'(prefix_len))begin
                dump_cache("prefix");
                prefix_recorded=1;
            end
        end
        if(dut.selected_valid && dut.core_token_ready)begin
            if(seen_inputs==0)start_cycle=int'($time/10);""")
    text = replace(text, "seen_scores>=positions*320", "seen_scores>=(positions-skip_count)*320")
    text = text.replace("expected_scores[seen_scores]", "expected_scores[seen_scores+skip_count*320]")
    text = replace(text, '!$value$plusargs("CAP=%d",cap)', '!$value$plusargs("SKIP=%d",skip_mode) ||\n'
                   '           !$value$plusargs("CACHE=%s",dump_path) || !$value$plusargs("CAP=%d",cap)')
    text = replace(text, "        events=$fopen", '        skip_count=skip_mode ? prefix_len-1 : 0;\n'
                   '        dumpfile=$fopen(dump_path,"w");\n        events=$fopen')
    text = replace(text, "check_read(8'h24,32'h41553031);",
                   "check_read(8'h24,skip_mode ? 32'h41553032 : 32'h41553031);")
    text = replace(text, "        observing=0;",
                   """        observing=0;
        if(!prefix_recorded || logit_starts!=positions-skip_count)$fatal(1,"Projection count or prefix boundary differs");
        if(skip_mode)check_read(8'h5c,32'(skip_count));
        if(!done_recorded)$fatal(1,"Missing exact terminal snapshot");
        $fclose(dumpfile);""")
    return text.replace("positions*320", "(positions-skip_count)*320")


def cache(path):
    lines = iter(path.read_text().splitlines())
    snapshots = {}
    for line in lines:
        name, count, cycles = line.split()
        snapshots[name] = (int(count), int(cycles), [next(lines) for _ in range(int(count)*32)])
    return snapshots


def main(a):
    baseline = a.kv260 / "variants/autonomous-v1"
    previous = runpy.run_path(str(baseline / "test_autonomous.py"))
    pinned, run = previous["pinned"], previous["run"]
    tool = a.verilator.resolve()
    tool_pin = json.loads((a.kv260 / "rtl/toolchain.json").read_text())
    tree = {str(f.relative_to(tool)):sha256(f.read_bytes()).hexdigest() for f in sorted(tool.rglob("*")) if f.is_file()}
    if len(tree)!=tool_pin["tree_files"] or sha256(json.dumps(tree,sort_keys=True,separators=(",",":")).encode()).hexdigest()!=tool_pin["tree_sha256"]:
        raise ValueError("Simulator differs")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, VERILATOR_ROOT=str(tool/"share/verilator"),
               PATH="/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin",
               SDKROOT="/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")
    bench = out / "autonomous_core_tb.sv"
    bench.write_text(testbench(pinned(baseline/"tests/autonomous_core_tb.sv", BENCH_PIN).decode()))
    package = json.loads(pinned(a.bundle/"package.json","b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167"))
    def member(name):
        return pinned(a.bundle/name,package["files"][name]["sha256"])
    references=json.loads(pinned(a.references,"33d290aed332af9e8b100a708222796d53f82529bb9c55d5d9ed13606cb0d367"))["cases"]
    def hexfile(path, values):
        path.write_text("".join(f"{number & 0xffffffff:08x}\n" for number in values))
        return path
    model=hexfile(out/"model.hex",struct.unpack("<29281I",member("model-words.bin")))
    bos_values=json.loads(member("bos-logits.json"))["logits"]
    bos=hexfile(out/"bos.hex",bos_values)
    executables={}
    for mode in ("control","candidate"):
        rtl=out/mode
        names=materialise(a.kv260,rtl,candidate=mode=="candidate")
        run([str(tool/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","--top-module",
             "autonomous_core_tb","-j","2","--Mdir",str(rtl/"obj"),"-o","simulation",
             *[str(rtl/(name+".sv")) for name in names],str(bench)],
            out,env,rtl/"compile.log",150)
        executables[mode]=rtl/"obj/simulation"
    edge=out/"edge.sv"
    edge.write_text(build_edge(baseline/"tests/autonomous_edge_tb.sv"))
    edge_obj=out/"edge-obj"
    run([str(tool/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","--top-module",
         "autonomous_edge_tb","-j","2","--Mdir",str(edge_obj),"-o","simulation",
         str(out/"candidate/axi_transformer.sv"),str(edge)],out,env,out/"edge-compile.log",150)
    run([str(edge_obj/"simulation")],out,env,out/"edge-simulation.log",150)
    cases=[]
    for name, cap in [("encoded-hello",255),("encoded-fu2p2q",255),("encoded-max48",255),
                      ("encoded-hello",0),("encoded-hello",1)]:
        path,pin=previous["FRESH"][name]
        trace=json.loads(pinned(a.traces/path,pin))["completion"]
        ref=references[name]
        assert all(trace[k]==ref[k] for k in ("prefix_tokens","generated_tokens","stop_reason"))
        prefix=len(ref["prefix_tokens"])
        count=len(trace["input_tokens"]) if cap==255 else prefix
        cases.append((name,cap,prefix,trace["input_tokens"][:count],ref["generated_tokens"][:cap],
                      [row["logits"] for row in trace["frames"][:count]],1 if cap==255 else 4))
    cases.append(("bos-only",0,1,[256],[],[bos_values],4))
    context=next(row for row in json.loads(member("token-logits.json"))["cases"] if row["name"]=="repeated-J01-256")
    cases.append(("full-context",0,256,context["tokens"],[],context["logits"],2))
    report=[]
    for name,cap,prefix,tokens,outputs,scores,reason in cases:
        case=out/(name+"-cap"+str(cap))
        case.mkdir()
        inp=hexfile(case/"input.hex",tokens)
        expected=hexfile(case/"output.hex",outputs or [0])
        all_scores=hexfile(case/"scores.hex",[value for frame in scores for value in frame])
        snapshots={}
        for mode,executable in executables.items():
            prefix_path=case/mode
            kwargs={"MODEL":model,"SCORES":bos,"CSV":prefix_path.with_suffix(".events"),
                    "RETURNS":prefix_path.with_suffix(".bos"),"INPUT":inp,"OUTPUT":expected,
                    "ALLSCORES":all_scores,"PREFIX":prefix,"OUTPUTS":len(outputs),"POSITIONS":len(tokens),
                    "CAP":cap,"REASON":reason,"SKIP":int(mode=="candidate"),"CACHE":prefix_path.with_suffix(".kv")}
            run([str(executable),*[f"+{key}={value}" for key,value in kwargs.items()]],out,env,
                prefix_path.with_suffix(".log"),600)
            snapshots[mode]=cache(kwargs["CACHE"])
        results={}
        for boundary,count in [("prefix",prefix),("done",len(tokens))]:
            control=snapshots["control"][boundary]
            candidate=snapshots["candidate"][boundary]
            if control[0]!=count or candidate[0]!=count or control[2]!=candidate[2]:
                raise ValueError(f"KV differs at {name} {boundary}")
            results[boundary]={"positions":count,"control_cycles":control[1],"candidate_cycles":candidate[1]}
        row={"case":name,"cap":cap,"outputs":len(outputs),"skipped":prefix-1,
             "candidate_exact_scores":320*(len(tokens)-prefix+1),"boundaries":results}
        report.append(row)
        (out/"progress.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(row),flush=True)
    (out/"result.json").write_text(json.dumps({"passed":True,"cases":report},indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","bundle","references","traces","output"):
        p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
