"""Bit-exact seven-case model replay and direct scored-step context sweep."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_value_pair import HERE, checked, materialise
from verify_values import audit_values, integers

ARCHIVE_SHA256="281305e4fa105441a2d7e513a505a288b1b4cbe9383e709349e94b8a6d11449d"
SELECTED="projections-read-ahead-v1"
NATURAL=("encoded-hello-cap255","encoded-fu2p2q-cap255","encoded-max48-cap255")
DEPTHS=(1,16,64,128,256)
EXACT=("attention-events.txt","attention-pairs.txt","bos.csv","divider-values.txt",
       "down-profile.txt","feedforward-elements.txt","feedforward-products.txt","feedforward-profile.txt",
       "norm-outputs.txt","norm-ownership.txt","norm-products.txt","projection-gate-up-wait.txt",
       "projection-outputs.txt","projection-profile.txt")
TRACES=(*EXACT,"cache.kv","phases.txt","probability-profile.txt","overlap-profile.txt","cache-addresses.bin")


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def signature(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def extract(path,dest):
    checked(path,ARCHIVE_SHA256)
    with tarfile.open(path) as archive:
        info=json.load(archive.extractfile("selection/model-results.json"))
        old=Path("replay")/SELECTED
        oracle=Path("replay/gold/replay/gold")
        files=[old/"autonomous_core_tb.sv",oracle/"model.hex",oracle/"bos.hex"]
        for name in info:
            files.extend(oracle/name/f"{leaf}.hex" for leaf in ("input","output","scores"))
            files.extend(old/name/leaf for leaf in TRACES)
        for member in files:
            item=archive.getmember(str(member))
            if not (item.isfile() or item.islnk()):
                raise ValueError(f"Unexpected archive member {member}")
            path=dest/member
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.extractfile(item).read())
    return info,dest/oracle,dest/old


def harness(origin,arm):
    if arm=="candidate":
        fragment="dut.core.front.cache.v_memory[i]"
        assert origin.count(fragment)==1
        origin=origin.replace(fragment,"(i%2 ? dut.core.front.cache.v_odd[i/2] : dut.core.front.cache.v_even[i/2])")
    assert origin.endswith("\nendmodule\n") and origin.count("endmodule")==1
    return origin.removesuffix("endmodule\n")+(HERE/"value_monitor.svh").read_text()+"endmodule\n"


def save(n):
    return 16*n*(n+2)


def read_cache_profile(folder,gold,paired,positions):
    traces=list(integers(folder/"overlap-profile.txt"))
    probability=list(integers(folder/"probability-profile.txt"))
    assert len(traces)==len(probability)==positions
    if gold is not None:
        old=list(integers(gold/"probability-profile.txt"))
        assert len(old)==positions
    for index,(overlap,p) in enumerate(zip(traces,probability,strict=True),1):
        groups=16 if paired else 32
        assert overlap==(index,2*index,32*index,32*index,30*index,groups,groups*index,groups*index,groups*(index-1))
        assert p[0]==index
        if gold is not None:
            assert p[:-1]==old[index-1][:-1]
            assert old[index-1][-1]-p[-1]==((32*index+16) if paired else 0)


def audit(case,ref,gold,before,after,pair,prior,sweep=False):
    if not sweep:
        for name in TRACES:
            assert signature(before/name)==signature(gold/name),(case,name,"control")
    for name in (*EXACT,"value-cache-appends.txt","value-results.txt"):
        assert signature(before/name)==signature(after/name),(case,name,"numerical")
    depths=ref["done"]["positions"]
    cache={}
    phases={}
    profiles={}
    for arm,folder in (("control",before),("candidate",after)):
        cache[arm]=pair["cache"](folder/"cache.kv")
        phases[arm]=prior["phase_rows"](folder,pair["cache"],pair["get_phases"])
        read_cache_profile(folder,before,arm=="candidate",depths)
        profiles[arm]=audit_values(folder,cache[arm]["done"][2],depths,arm=="candidate")
    for point in ("prefix","done"):
        a,b=(phases[arm][point] for arm in ("control","candidate"))
        if not sweep:
            assert a==ref[point],(case,point)
        n=a["positions"]
        assert b["positions"]==n and cache["control"][point][2]==cache["candidate"][point][2]
        assert a["cycles"]-b["cycles"]==save(n)
        assert a["first_valid"]==b["first_valid"]
        for stage,(old,new) in enumerate(zip(a["phases"],b["phases"],strict=True)):
            assert old-new==(save(n) if stage==8 else 0),(case,point,stage)
        assert b["done"]==(a["done"]-save(n) if a["done"] else 0)
        if a["first_valid"]:
            prefix=ref["prefix"]["positions"]
            last=prefix+ref["outputs"]-1
            assert a["first"]-b["first"]==save(prefix) and a["last"]-b["last"]==save(last)
        else:
            assert b["first"]==b["last"]==0
    step={arm:list(integers(folder/"scored-steps.txt"))
          for arm,folder in (("control",before),("candidate",after))}
    assert len(step["control"])==len(step["candidate"])==ref["scored_values"]//320
    for (d,old),(n,new) in zip(step["control"],step["candidate"],strict=True):
        assert d==n and old-new==32*d+16,(case,d,old,new)
    print(case,phases["control"]["done"]["done"],phases["candidate"]["done"]["done"],save(depths),flush=True)
    return {**phases,**{k:ref[k] for k in ("outputs","scored_values","skipped_positions","stop_reason")},
            "saved_clocks":save(depths),"value_profile":profiles,"scored_steps":step}


def trial(arms,case,ref,oracle,scope,env,model,deadline):
    for arm,exe in arms.items():
        folder=scope/arm/case
        folder.mkdir(parents=True)
        params=dict(MODEL=oracle/"model.hex",SCORES=oracle/"bos.hex",INPUT=oracle/case/"input.hex",
                    OUTPUT=oracle/case/"output.hex",ALLSCORES=oracle/case/"scores.hex",
                    CSV=folder/"bus.events",RETURNS=folder/"bos.csv",PREFIX=ref["prefix"]["positions"],
                    OUTPUTS=ref["outputs"],POSITIONS=ref["done"]["positions"],CAP=int(case.rsplit("-cap",1)[1]),
                    SKIP=1,CACHE=folder/"cache.kv",PHASE=folder/"phases.txt",REASON=ref["stop_reason"])
        model["run"]([str(exe),*[f"+{key}={value}" for key,value in params.items()]],
                     folder,env,folder/"simulation.log",180,deadline)
        count=re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                        r"reason=(\d+) legacy_BOS_scores=640",(folder/"simulation.log").read_text())
        assert count and tuple(map(int,count.groups()))==(params["POSITIONS"],ref["scored_values"],
                                                         params["OUTPUTS"],params["REASON"]),(arm,case)


def invoke(args):
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    pair=load(kv260/"variants/attention-exp-pair-v2/replay_pair.py")
    prior=load(kv260/"variants/probability-div-v1/replay_probability.py")
    model=prior["load_model"](kv260)
    env=model["simulator"](args.verilator,kv260)
    out=args.output
    out.mkdir()
    reference,oracle,gold=extract(args.archive,out/"gold")
    origin=(gold/"autonomous_core_tb.sv").read_text()
    arms={}
    deadline=time.monotonic()+1800
    for arm in ("control","candidate"):
        work=out/arm
        work.mkdir()
        rtl=work/"rtl"
        names=materialise(kv260,rtl,arm)
        bench=work/"autonomous_core_tb.sv"
        bench.write_text(harness(origin,arm))
        exe=work/"obj/simulation"
        arms[arm]=exe
        macros=["+define+PARTIAL_MULTIPLIER"]+(["+define+PAIRED_VALUES"] if arm=="candidate" else [])
        model["run"]([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
                      "--top-module","autonomous_core_tb","--Mdir",str(exe.parent),"-o","simulation",*macros,
                      *[str(rtl/(name+".sv")) for name in names],str(bench)],
                     work,env,work/"compile.log",150,deadline)
    results={}
    for case in (*NATURAL,*(name for name in reference if name not in NATURAL)):
        row=reference[case]
        ref={**row["candidate"],**{k:row[k] for k in ("outputs","scored_values","skipped_positions","stop_reason")}}
        trial(arms,case,ref,oracle,out,env,model,deadline)
        results[case]=audit(case,ref,gold/case,out/"control"/case,out/"candidate"/case,pair,prior)
        (out/"matched.json").write_text(json.dumps(results,indent=2)+"\n")
    full=oracle/"full-context-cap0"
    original=(full/"input.hex").read_text().splitlines()
    assert len(original)==256
    sweep={}
    for d in DEPTHS:
        if d==256:
            observed=results["full-context-cap0"]
        else:
            case=f"depth-{d}-cap0"
            in_folder=out/"fixed-prefix"/case
            in_folder.mkdir(parents=True)
            for name in ("model.hex","bos.hex"):
                (in_folder.parent/name).write_bytes((oracle/name).read_bytes())
            (in_folder/"input.hex").write_text("\n".join(original[:d])+"\n")
            for name in ("scores.hex","output.hex"):
                (in_folder/name).write_bytes((full/name).read_bytes())
            ref=dict(prefix=dict(positions=d),done=dict(positions=d),outputs=0,scored_values=320,
                     skipped_positions=d-1,stop_reason=4)
            trial(arms,case,ref,in_folder.parent,out/"depth-replay",env,model,deadline)
            observed=audit(case,ref,None,out/"depth-replay/control"/case,out/"depth-replay/candidate"/case,pair,prior,True)
        rows={}
        for arm in arms:
            steps=observed["scored_steps"][arm]
            assert len(steps)==1 and steps[0][0]==d
            rows[arm]={"scored_step_cycles":steps[0][1],**observed["value_profile"][arm][d-1]}
        sweep[d]=rows
    (out/"depth-results.json").write_text(json.dumps(sweep,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("repo","verilator","archive","output"):
        p.add_argument("--"+arg,type=lambda value:Path(value).resolve(),required=True)
    invoke(p.parse_args())
