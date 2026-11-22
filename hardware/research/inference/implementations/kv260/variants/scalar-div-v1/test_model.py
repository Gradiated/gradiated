"""Profile dividers and check exact model behaviour against the scalar-mul run."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys
import tarfile
import time

PRIOR_ARCHIVE = "36d82df2516a57022ddec0737d5a479f2a34c85874809adf03d1b0be87dfe3c7"
PRIOR_HELPER = "2081ea5cd7d18fdc611f194085dbf5ef99e400f2c2c4f9bad4410677af635c4c"
PRIOR_GENERATOR = "1d73a8acb7158002c8ddb7e92b4ea67c4a8624e756bb91a9ed08559ffac44193"
LANES = ("norm1", "norm2", "normfinal", "att", "ff")
ORIGINS = ("command", "exp-power", "exp-index", "exp-interpolate", "rsqrt-index")
CASES = ("encoded-hello-cap255", "encoded-fu2p2q-cap255", "encoded-max48-cap255",
         "encoded-hello-cap0", "encoded-hello-cap1", "bos-only-cap0", "full-context-cap0")


def pinned(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Source differs: {path}")
    return data


def prior(kv260):
    variant = kv260/"variants/scalar-mul-v1"
    for name,pin in (("test_model.py",PRIOR_HELPER),("materialise.py",PRIOR_GENERATOR)):
        pinned(variant/name,pin)
    sys.path.insert(0,str(variant))
    try:
        support=runpy.run_path(str(variant/"test_model.py"))
        generate=runpy.run_path(str(variant/"materialise.py"))["materialise"]
    finally:
        sys.path.pop(0)
    return support,generate


def instrumentation(bench, steps):
    visits=[]
    for lane,instance in enumerate(LANES):
        parent=f"dut.core.{instance}"
        node=parent+".scalar"
        visits.append(f"        active += count_div({lane},{node}.state,{node}.return_state,"
                      f"{node}.remaining,{node}.numerator,{node}.denominator,{parent}.state,dut.core_phase);")
    declarations = """    integer prof,union_ticks=0,overlap_ticks=0,ff_dense_overlap=0;
    string prof_path;
    int ticks[5][5],completions[5][5],width_n[5][5],width_d[5][5];
    function automatic int bits(input logic [63:0] v);
        for(int i=63;i>=0;i--) if(v[i]) return i+1;
        return 0;
    endfunction
    function automatic int count_div(input int lane,input logic [4:0] state,ret,
        input logic [6:0] remaining,input logic [63:0] n,d,input logic [4:0] parent,top);
        int kind, expected_top, expected_parent;
        if(state!=5'd2) return 0;
        case(ret)
            5'd4: kind=0;
            5'd5: kind=1;
            5'd6: kind=2;
            5'd10: kind=3;
            5'd12: kind=4;
            default: begin $fatal(1,"Unexpected division return"); return 0; end
        endcase
        case(lane)
            0: begin expected_top=4;expected_parent=6;end  // Norm1 RSQRT_WAIT
            1: begin expected_top=12;expected_parent=6;end // Norm2 RSQRT_WAIT
            2: begin expected_top=16;expected_parent=6;end // Final norm RSQRT_WAIT
            3: begin expected_top=8;expected_parent=kind==0 ? 11 : 8;end // Attention normalise or exponent
            default: begin expected_top=14;expected_parent=kind==0 ? 5 : 3;end // FF sigmoid or exponent
        endcase
        if(int'(top)!=expected_top || int'(parent)!=expected_parent)
            $fatal(1,"Divider is not in its parent wait state lane=%0d kind=%0d top=%0d parent=%0d",lane,kind,top,parent);
        ticks[lane][kind]++;
        if(remaining==7'dSTEPS)begin
            if(bits(n)>width_n[lane][kind])width_n[lane][kind]=bits(n);
            if(bits(d)>width_d[lane][kind])width_d[lane][kind]=bits(d);
        end
        if(remaining==1)completions[lane][kind]++;
        return 1;
    endfunction
    task automatic dump_div(input string boundary);
        $fwrite(prof,"%s %0d %0d %0d\\n",boundary,union_ticks,overlap_ticks,ff_dense_overlap);
        for(int lane=0;lane<5;lane++)for(int kind=0;kind<5;kind++)
            $fwrite(prof,"%0d %0d %0d %0d\\n",ticks[lane][kind],completions[lane][kind],width_n[lane][kind],width_d[lane][kind]);
    endtask
""".replace("STEPS",str(steps))
    def insert(old,new):
        nonlocal bench
        if bench.count(old)!=1:
            raise ValueError(f"Changed archived fixture: {old}")
        bench=bench.replace(old,new)
    insert("    task automatic dump_cache",declarations+"    task automatic dump_cache")
    insert("        count=int'(dut.core_context_count);","        dump_div(boundary);\n        count=int'(dut.core_context_count);")
    insert("        if(dut.auto_state==4 && !done_recorded)begin","""        int active;
        active=0;
"""+"\n".join(visits)+"""
        if(active>0)union_ticks++;
        if(active>1)overlap_ticks++;
        if(dut.core.ff.scalar.state==5'd2 &&
          ((dut.core.ff.g_busy && !dut.core.ff.g_valid) || (dut.core.ff.u_busy && !dut.core.ff.u_valid)))
            ff_dense_overlap++;
        if(dut.auto_state==4 && !done_recorded)begin""")
    insert("        $readmemh(modelfile,words);",'''        if(!$value$plusargs("PROF=%s",prof_path))$fatal(1,"Missing divider profile path");
        prof=$fopen(prof_path,"w");
        if(!prof)$fatal(1,"Cannot open divider profile");
        $readmemh(modelfile,words);''')
    insert("        $fclose(dumpfile);","        $fclose(prof);\n        $fclose(dumpfile);")
    return bench


def read_profile(path,steps):
    lines=iter(path.read_text().splitlines())
    output={}
    for boundary in ("prefix","done"):
        tag,active,overlap,dense_overlap=next(lines).split()
        if tag!=boundary:
            raise ValueError("Unexpected profile boundary")
        per_instance={}
        for lane in LANES:
            per_instance[lane]={}
            for origin in ORIGINS:
                count,completed,width_n,width_d=map(int,next(lines).split())
                if count!=steps*completed or not 0<=width_n<=64 or not 0<=width_d<=64:
                    raise ValueError("Unexpected divider iteration or operand profile")
                per_instance[lane][origin]=dict(cycles=count,divisions=completed,max_num_bits=width_n,max_den_bits=width_d)
        output[boundary]=dict(active=int(active),overlap=int(overlap),ff_dense_overlap=int(dense_overlap),instances=per_instance)
    if next(lines,None) is not None:
        raise ValueError("Unexpected profile residue")
    return output


def main(a):
    deadline=time.monotonic()+1500
    if a.mode=="candidate" and a.control is None:
        raise ValueError("Supply the exact matched control profile")
    helpers,generate=prior(a.kv260)
    env=helpers["simulator"](a.verilator.resolve(),a.kv260)
    run,boundaries=helpers["run"],helpers["boundaries"]
    root=a.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    pinned(a.archive,PRIOR_ARCHIVE)
    files={"model-sim/model.hex","model-sim/bos.hex","model-sim/autonomous_core_tb.sv","model-sim/profile-results.json"}
    for label in CASES:
        files.update(f"model-sim/{label}/{name}" for name in ("input.hex","output.hex","scores.hex","candidate-scalar.kv"))
    with tarfile.open(a.archive) as archive:
        for name in sorted(files):
            member=archive.getmember(name)
            if not member.isfile():
                raise ValueError("Unexpected prior archive member")
            path=root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    work=root/"model-sim"
    archived=json.loads((work/"profile-results.json").read_bytes())
    rtl=root/"rtl"
    steps=64
    if a.mode=="candidate":
        candidate=runpy.run_path(str(Path(__file__).parent/"make_division.py"))
        generate=candidate["materialise"]
        steps=candidate["DIV_STEPS"]
    names=generate(a.kv260,rtl)
    bench=root/"division_profile_tb.sv"
    bench.write_text(instrumentation((work/"autonomous_core_tb.sv").read_text(),steps))
    binary=rtl/"obj/simulation"
    run([str(a.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal",
         "--top-module","autonomous_core_tb","-j","2","--Mdir",str(binary.parent),"-o","simulation",
         *[str(rtl/(name+".sv")) for name in names],str(bench)],root,env,root/"compile.log",150,deadline)
    rows={}
    control=json.loads(a.control.read_bytes()) if a.control is not None else {}
    for label in CASES:
        name,cap=label.rsplit("-cap",1)
        cap=int(cap)
        fixtures=work/label
        result=root/label
        result.mkdir()
        historic=archived[label]
        reference=boundaries(fixtures/"candidate-scalar.kv")
        kwargs=dict(MODEL=work/"model.hex",SCORES=work/"bos.hex",CSV=result/"bus.events",
                    RETURNS=result/"bos.csv",INPUT=fixtures/"input.hex",OUTPUT=fixtures/"output.hex",
                    ALLSCORES=fixtures/"scores.hex",PREFIX=reference["prefix"]["positions"],
                    OUTPUTS=historic["outputs"],POSITIONS=reference["done"]["positions"],CAP=cap,
                    REASON=1 if cap==255 else 2 if name=="full-context" else 4,SKIP=1,
                    CACHE=result/"cache.kv",PROF=result/"division.profile")
        run([str(binary),*[f"+{key}={value}" for key,value in kwargs.items()]],root,env,result/"simulation.log",600,deadline)
        profile=read_profile(kwargs["PROF"],steps)
        for boundary,seen in boundaries(kwargs["CACHE"]).items():
            expected=reference[boundary]
            if seen["positions"]!=expected["positions"] or seen["kv"]!=expected["kv"]:
                raise ValueError(f"Exact cache differed: {label} {boundary}")
            row=profile[boundary]
            row.update(cycles=seen["cycles"],positions=seen["positions"])
            if a.mode=="control":
                if row["cycles"]!=expected["cycles"]:
                    raise ValueError("Divider profiler changed the original timing")
            else:
                left=control[label][boundary]
                for lane in LANES:
                    for origin in ORIGINS:
                        x,y=(v["instances"][lane][origin] for v in (left,row))
                        if any(x[k]!=y[k] for k in ("divisions","max_num_bits","max_den_bits")):
                            raise ValueError("Observed division calls or range changed")
                row["cycle_savings"]=left["cycles"]-row["cycles"]
                if not 0<row["cycle_savings"]<=left["active"]-row["active"]:
                    raise ValueError("Unexpected end-to-end divider cycle delta")
        rows[label]=profile
        print(label,a.mode,[(v["cycles"],v["active"],v["ff_dense_overlap"]) for v in profile.values()],flush=True)
        (root/"profile-results.json").write_text(json.dumps(rows,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","archive","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--mode",choices=("control","candidate"),required=True)
    parser.add_argument("--control",type=Path)
    main(parser.parse_args())
