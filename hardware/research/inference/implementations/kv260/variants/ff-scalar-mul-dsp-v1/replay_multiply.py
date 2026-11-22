"""Measure exact candidate FF products and seven paired full-model clocks."""

import argparse
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_partial_multiply import HERE, checked, materialise

ARCHIVE_SHA256="6be001afaadce8ef883ca5206bef8bf4093e8dd9475927cc9162c210c923c76e"
ADOPTED_TRACES=("attention-events.txt","attention-pairs.txt","bos.csv","cache-addresses.bin",
                "cache.kv","divider-values.txt","down-profile.txt","overlap-profile.txt",
                "phases.txt","probability-profile.txt")
SAVED_PER_PRODUCT=11


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def extract(archive_path,dest):
    checked(archive_path,ARCHIVE_SHA256)
    with tarfile.open(archive_path) as archive:
        reference=json.load(archive.extractfile("replay/matched.json"))
        oracle="replay/gold/predecessor/pinned"
        files=["replay/autonomous_core_tb.sv",f"{oracle}/model.hex",f"{oracle}/bos.hex"]
        for case in reference:
            files.extend(f"{oracle}/{case}/{name}.hex" for name in ("input","output","scores"))
            files.extend(f"replay/candidate/{case}/{name}" for name in ADOPTED_TRACES)
        for name in files:
            item=archive.getmember(name)
            if not item.isfile():
                raise ValueError(f"Expected a regular archive member: {name}")
            path=dest/name
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.extractfile(item).read())
    return reference


def integer_rows(path):
    return [list(map(int,line.split())) for line in path.read_text().splitlines()]


def verify_products(path,depths):
    counts=[[0,0,0] for _ in range(depths)]
    with path.open() as stream:
        rows=iter(stream)
        for launch in rows:
            a,depth,row,source,left,right=launch.split()
            p,seen_depth,seen_row,seen_source,magnitude=next(rows).split()
            assert a=="A" and p=="P" and [depth,row,source]==[seen_depth,seen_row,seen_source]
            assert 1<=int(depth)<=depths and 0<=int(row)<128 and 0<=int(source)<3
            assert int(magnitude,16)==int(left,16)*int(right,16)
            counts[int(depth)-1][int(source)]+=1
    return counts


def verify_profile(case,control,candidate,depths):
    files=[integer_rows(folder/"feedforward-profile.txt") for folder in (control,candidate)]
    down=[integer_rows(folder/"down-profile.txt") for folder in (control,candidate)]
    assert all(len(rows)==depths for rows in [*files,*down])
    counts=verify_products(candidate/"feedforward-products.txt",depths)
    profile={}
    savings=[0]
    for depth,(old,new,before_down,after_down,products) in enumerate(zip(*files,*down,counts,strict=True),1):
        assert old[0]==new[0]==before_down[0]==after_down[0]==depth
        assert old[3:6]==new[3:6]==products and products[1:]==[128,128]
        assert old[6:]==[count*16 for count in products] and new[6:]==[count*5 for count in products]
        new_stalls=new[2]-old[2]
        saved=sum(products)*SAVED_PER_PRODUCT-new_stalls
        assert old[1]-new[1]==saved and before_down[1]-after_down[1]==saved, (case,depth,old,new)
        assert before_down[2:]==after_down[2:], (case,depth)
        savings.append(savings[-1]+saved)
        profile[depth]=dict(control_feedforward=old[1],candidate_feedforward=new[1],
                            control_gate_up_stalls=old[2],candidate_gate_up_stalls=new[2],
                            products=dict(exp=products[0],gate=products[1],hidden=products[2]),
                            control_mul_steps=sum(old[6:]),candidate_mul_steps=sum(new[6:]))
    assert len(integer_rows(candidate/"feedforward-elements.txt"))==128*depths
    return savings,profile


def check_case(case,reference,gold,control,candidate,prior,pair,receipts):
    ref=reference["candidate"]
    depths=ref["done"]["positions"]
    for name in ADOPTED_TRACES:
        assert (control/name).read_bytes()==(gold/name).read_bytes(), (case,name)
        if name not in ("cache.kv","phases.txt","down-profile.txt"):
            assert (control/name).read_bytes()==(candidate/name).read_bytes(), (case,name)
    for name in ("feedforward-products.txt","feedforward-elements.txt"):
        assert (control/name).read_bytes()==(candidate/name).read_bytes(), (case,name)
    accumulated,profile=verify_profile(case,control,candidate,depths)
    assert receipts["control"]==receipts["candidate"]
    assert receipts["candidate"]==(depths,reference["scored_values"],reference["outputs"],reference["stop_reason"])
    phases={}
    cache={}
    for arm,folder in (("control",control),("candidate",candidate)):
        cache[arm]=pair["cache"](folder/"cache.kv")
        phases[arm]=prior["phase_rows"](folder,pair["cache"],pair["get_phases"])
    for boundary in ("prefix","done"):
        old,new=(phases[arm][boundary] for arm in ("control","candidate"))
        assert old==ref[boundary], (case,boundary)
        depth=old["positions"]
        savings=accumulated[depth]
        assert new["positions"]==depth and old["cycles"]-new["cycles"]==savings
        assert cache["control"][boundary][2]==cache["candidate"][boundary][2]
        assert old["first_valid"]==new["first_valid"]
        for stage,(before,after) in enumerate(zip(old["phases"],new["phases"],strict=True)):
            assert before-after==(savings if stage==14 else 0), (case,boundary,stage)
        for arm,sample in (("control",old),("candidate",new)):
            assert sample["phases"][14]==sum(profile[d][arm+"_feedforward"] for d in range(1,depth+1))
        assert new["done"]==(old["done"]-savings if old["done"] else 0)
        if old["first_valid"]:
            prefix=ref["prefix"]["positions"]
            assert old["first"]-new["first"]==accumulated[prefix]
            assert old["last"]-new["last"]==accumulated[prefix+reference["outputs"]-1]
        else:
            assert new["first"]==new["last"]==0
    print(case,phases["control"]["done"]["done"],phases["candidate"]["done"]["done"],
          "saved",accumulated[-1],flush=True)
    return {**phases,**{name:reference[name] for name in ("outputs","scored_values","skipped_positions","stop_reason")},
            "saved_clocks":accumulated[-1],"feedforward_profile":profile}


def main(args):
    deadline=time.monotonic()+min(1100,args.deadline_epoch-time.time())
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    pair=load(kv260/"variants/attention-exp-pair-v2/replay_pair.py")
    prior=load(kv260/"variants/probability-div-v1/replay_probability.py")
    model=prior["load_model"](kv260)
    env=model["simulator"](args.verilator,kv260)
    out=args.output
    out.mkdir()
    reference=extract(args.archive,out/"gold")
    original=(out/"gold/replay/autonomous_core_tb.sv").read_text()
    assert original.endswith("\nendmodule\n") and original.count("endmodule")==1
    bench=out/"autonomous_core_tb.sv"
    bench.write_text(original.removesuffix("endmodule\n")+(HERE/"monitor.svh").read_text()+"endmodule\n")
    exe={}
    run=model["run"]
    for arm in ("control","candidate"):
        work=out/arm
        work.mkdir()
        rtl=work/"rtl"
        names=materialise(kv260,rtl,arm=="candidate")
        exe[arm]=work/"obj/simulation"
        define=["+define+PARTIAL_MULTIPLIER"] if arm=="candidate" else []
        run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
             "--top-module","autonomous_core_tb","--Mdir",str(exe[arm].parent),"-o","simulation",*define,
             *[str(rtl/(name+".sv")) for name in names],str(bench)],work,env,work/"compile.log",150,deadline)
    measured={}
    for case,ref in reference.items():
        receipts={}
        for arm in ("control","candidate"):
            folder=out/arm/case
            folder.mkdir()
            oracle=out/"gold/replay/gold/predecessor/pinned"
            params=dict(MODEL=oracle/"model.hex",SCORES=oracle/"bos.hex",INPUT=oracle/case/"input.hex",
                        OUTPUT=oracle/case/"output.hex",ALLSCORES=oracle/case/"scores.hex",
                        CSV=folder/"bus.events",RETURNS=folder/"bos.csv",PREFIX=ref["candidate"]["prefix"]["positions"],
                        OUTPUTS=ref["outputs"],POSITIONS=ref["candidate"]["done"]["positions"],
                        CAP=int(case.rsplit("-cap",1)[1]),SKIP=1,CACHE=folder/"cache.kv",
                        PHASE=folder/"phases.txt",REASON=ref["stop_reason"])
            run([str(exe[arm]),*[f"+{key}={value}" for key,value in params.items()]],folder,env,
                folder/"simulation.log",120,deadline)
            match=re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                            r"reason=(\d+) legacy_BOS_scores=640",(folder/"simulation.log").read_text())
            assert match, (arm,case)
            receipts[arm]=tuple(map(int,match.groups()))
        measured[case]=check_case(case,ref,out/"gold/replay/candidate"/case,out/"control"/case,
                                  out/"candidate"/case,prior,pair,receipts)
        (out/"matched.json").write_text(json.dumps(measured,indent=2)+"\n")
    assert len(measured)==7


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","archive","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
