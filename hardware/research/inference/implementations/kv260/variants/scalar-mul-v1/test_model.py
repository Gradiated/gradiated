"""Profile and compare the complete AU02 circuit against the pinned RTL archive."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import tarfile
import time

from materialise import materialise, pin

ARCHIVE_PIN = "b925432197f98a7a3f3784d9e6b179bcfeda30e7b932ba215ef6e67764973bc0"
SCALARS = ("norm1", "norm2", "normfinal", "att", "ff")
ORIGINS = ("command", "exp", "rsqrt")
CASE_NAMES = (
    ("encoded-hello", 255), ("encoded-fu2p2q", 255), ("encoded-max48", 255),
    ("encoded-hello", 0), ("encoded-hello", 1), ("bos-only", 0), ("full-context", 0),
)


def simulator(tool, kv260):
    tree = {str(f.relative_to(tool)): sha256(f.read_bytes()).hexdigest()
            for f in sorted(tool.rglob("*")) if f.is_file()}
    identity = json.loads((kv260 / "rtl/toolchain.json").read_text())
    c = json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()
    if len(tree) != identity["tree_files"] or sha256(c).hexdigest() != identity["tree_sha256"]:
        raise ValueError("Simulator differs from the pinned Verilator distribution")
    return dict(os.environ, VERILATOR_ROOT=str(tool / "share/verilator"),
                PATH="/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                SDKROOT="/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")


def run(args, directory, env, log, limit, deadline):
    timeout = min(limit, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError("Local experiment deadline reached")
    with log.open("xb") as stream, subprocess.Popen(
        args, cwd=directory, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True
    ) as p:
        try:
            status = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=5)
            raise
    if status:
        raise ValueError(f"Simulation command exited {status}, see {log}")


def instrument(bench, steps):
    # These enum values and hierarchical names are part of the pinned closure.
    calls = []
    for index, instance in enumerate(SCALARS):
        node = f"dut.core.{instance}.scalar"
        operand = f"{node}.multiplier" if steps == 64 else f"{node}.product_sum[63:0]"
        calls.append(f"            cycles = cycles + count_mul({index}, {node}.state, {node}.return_state, "
                     f"{node}.remaining, {node}.multiplicand[63:0], {operand});")
    declarations = """    integer profile, mul_union=0, mul_overlap=0;
    string profile_path;
    int ticks[5][3], calls[5][3], width_a[5][3], width_b[5][3];
    function automatic integer bits(input logic [63:0] value);
        for(int i=63;i>=0;i--) if(value[i]) return i+1;
        return 0;
    endfunction
    function automatic int count_mul(input int lane, input logic [4:0] state, resume_state,
                                 input logic [6:0] remaining, input logic [63:0] a,b);
        int origin, a_bits, b_bits;
        if(state!=3) return 0;
        case(resume_state)
            4: origin=0;       // SIMPLE_DONE
            9: origin=1;       // EXP_INTERP
            14,15,16: origin=2;// RSQ_MY, RSQ_FACTOR, RSQ_UPDATE
            default: begin $fatal(1,"Unexpected scalar return state"); return 0; end
        endcase
        ticks[lane][origin]++;
        if(remaining==7'dSTEPS)begin
            a_bits=bits(a);b_bits=bits(b);
            if(a_bits>width_a[lane][origin])width_a[lane][origin]=a_bits;
            if(b_bits>width_b[lane][origin])width_b[lane][origin]=b_bits;
        end
        if(remaining==1)calls[lane][origin]++;
        return 1;
    endfunction
    task automatic write_profile(input string boundary);
        $fwrite(profile,"%s %0d %0d\\n",boundary,mul_union,mul_overlap);
        for(int lane=0;lane<5;lane++)for(int origin=0;origin<3;origin++)
            $fwrite(profile,"%0d %0d %0d %0d\\n",ticks[lane][origin],calls[lane][origin],
                    width_a[lane][origin],width_b[lane][origin]);
    endtask
""".replace("STEPS", str(steps))
    def change(old, new):
        nonlocal bench
        if bench.count(old) != 1:
            raise ValueError(f"Unexpected pinned bench fragment: {old}")
        bench = bench.replace(old, new)
    change("    task automatic dump_cache", declarations + "    task automatic dump_cache")
    change("        count=int'(dut.core_context_count);", "        write_profile(boundary);\n"
           "        count=int'(dut.core_context_count);")
    change("        if(dut.auto_state==4 && !done_recorded)begin",
           "        int cycles;\n        if(!done_recorded)begin\n            cycles=0;\n"
           + "\n".join(calls)
           + "\n            if(cycles>0)mul_union++;\n            if(cycles>1)mul_overlap++;\n        end\n"
           "        if(dut.auto_state==4 && !done_recorded)begin")
    change("        $readmemh(modelfile,words);",
           '        if(!$value$plusargs("PROFILE=%s",profile_path))$fatal(1,"Missing profile path");\n'
           '        profile=$fopen(profile_path,"w");\n'
           '        if(!profile)$fatal(1,"Cannot open profile");\n'
           '        $readmemh(modelfile,words);')
    change("        $fclose(dumpfile);","        $fclose(profile);\n        $fclose(dumpfile);")
    return bench


def profile(path, steps):
    rows = iter(path.read_text().splitlines())
    records = {}
    for boundary in ("prefix", "done"):
        name, busy, overlap = next(rows).split()
        if name != boundary:
            raise ValueError(f"Unexpected profile boundary {name}")
        entries = {}
        for block in SCALARS:
            entries[block] = {}
            for origin in ORIGINS:
                ticks, calls, width_a, width_b = map(int, next(rows).split())
                if ticks != steps*calls or not 0 <= width_a <= 64 or not 0 <= width_b <= 64:
                    raise ValueError("Unexpected scalar count or precision")
                entries[block][origin] = dict(cycles=ticks, products=calls, max_a_bits=width_a, max_b_bits=width_b)
        records[boundary] = dict(busy=int(busy), overlap=int(overlap), instances=entries)
    if next(rows, None) is not None:
        raise ValueError("Unexpected extra profile entries")
    return records


def boundaries(path):
    rows = iter(path.read_text().splitlines())
    result = {}
    for line in rows:
        name, positions, cycles = line.split()
        positions = int(positions)
        result[name] = dict(positions=positions, cycles=int(cycles), kv=[next(rows) for _ in range(32*positions)])
    return result


def main(a):
    deadline=time.monotonic()+25*60
    tool = a.verilator.resolve()
    env = simulator(tool, a.kv260)
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    pin(a.archive, ARCHIVE_PIN)
    with tarfile.open(a.archive) as archive:
        wanted = {"model.hex", "bos.hex", "autonomous_core_tb.sv", "result.json"}
        for name, cap in CASE_NAMES:
            wanted.update(f"{name}-cap{cap}/{leaf}" for leaf in
                          ("input.hex", "scores.hex", "output.hex", "candidate.kv"))
        for name in sorted(wanted):
            member=archive.getmember(name)
            if not member.isfile():
                raise ValueError(f"Expected archive to contain a regular file: {name}")
            path=output/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    baseline_records=json.loads((output/"result.json").read_text())["cases"]
    original_bench=(output/"autonomous_core_tb.sv").read_text()
    baseline=runpy.run_path(str(a.kv260 / "variants/prefill-skip-v1/materialise.py"))
    cases = {}
    for mode, steps in (("control",64),("candidate",16)):
        build=output/mode
        generated=baseline["materialise"](a.kv260,build) if mode=="control" else materialise(a.kv260,build)
        bench=build/"autonomous_core_tb.sv"
        bench.write_text(instrument(original_bench,steps))
        executable=build/"obj/simulation"
        run([str(tool/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","--top-module",
             "autonomous_core_tb","-j","2","--Mdir",str(executable.parent),"-o","simulation",
             *[str(build/(module+".sv")) for module in generated],str(bench)],
            output,env,build/"compile.log",150,deadline)
        for historic in baseline_records:
            name,cap=historic["case"],historic["cap"]
            label=f"{name}-cap{cap}"
            case=output/label
            measure=case/(mode+"-scalar")
            reference=boundaries(case/"candidate.kv")
            kwargs=dict(MODEL=output/"model.hex",SCORES=output/"bos.hex",CSV=measure.with_suffix(".events"),
                        RETURNS=measure.with_suffix(".bos"),INPUT=case/"input.hex",OUTPUT=case/"output.hex",
                        ALLSCORES=case/"scores.hex",PREFIX=reference["prefix"]["positions"],
                        OUTPUTS=historic["outputs"],POSITIONS=reference["done"]["positions"],CAP=cap,
                        REASON=1 if cap==255 else 2 if name=="full-context" else 4,SKIP=1,
                        CACHE=measure.with_suffix(".kv"),PROFILE=measure.with_suffix(".profile"))
            run([str(executable),*[f"+{k}={v}" for k,v in kwargs.items()]],
                output,env,measure.with_suffix(".log"),600,deadline)
            stats=profile(kwargs["PROFILE"],steps)
            for boundary,observed in boundaries(kwargs["CACHE"]).items():
                expected=reference[boundary]
                if observed["kv"]!=expected["kv"] or observed["positions"]!=expected["positions"]:
                    raise ValueError(f"Exact KV state differs at {label} {boundary}")
                if mode=="control" and observed["cycles"]!=expected["cycles"]:
                    raise ValueError("Profiling changed the control clock count")
                stats[boundary].update(cycles=observed["cycles"],positions=observed["positions"])
            saved=cases.setdefault(label,{"retained_scores":historic["candidate_exact_scores"],"outputs":historic["outputs"]})
            saved[mode]=stats
            if mode=="candidate":
                for boundary in ("prefix","done"):
                    control,candidate=(saved[arm][boundary] for arm in ("control","candidate"))
                    delta=control["cycles"]-candidate["cycles"]
                    count=0
                    for block in SCALARS:
                        for origin in ORIGINS:
                            left=control["instances"][block][origin]
                            right=candidate["instances"][block][origin]
                            keys=("products","max_a_bits","max_b_bits")
                            if any(left[key]!=right[key] for key in keys):
                                raise ValueError(f"Scalar calls diverged at {label} {boundary}")
                            count+=left["products"]
                    if not 0<delta<=48*count:
                        raise ValueError(f"Unexpected end-to-end cycle delta at {label} {boundary}")
            print(label,mode,stats["prefix"]["cycles"],stats["done"]["cycles"],
                  stats["prefix"]["busy"],stats["done"]["busy"],flush=True)
            (output/"profile-results.json").write_text(json.dumps(cases,indent=2)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("kv260","verilator","archive","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    main(parser.parse_args())
