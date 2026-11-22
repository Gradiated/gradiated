"""Verify three serial normalization waits and exact seven-case model replays."""

import argparse
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_norm_multiply import HERE, checked, materialise

ARCHIVE_SHA256="497dd939c88eaab38672722b85ac96fcf4df493ec2d3d73d66d4569ec6b2ff5d"
ADOPTED_TRACES=("attention-events.txt","attention-pairs.txt","bos.csv","cache-addresses.bin",
                "cache.kv","divider-values.txt","down-profile.txt","overlap-profile.txt","phases.txt",
                "probability-profile.txt","feedforward-elements.txt","feedforward-products.txt",
                "feedforward-profile.txt")
NORM_TRACES=("norm-products.txt","norm-results.txt","norm-scalar-results.txt")
LANES=("norm1","norm2","normfinal")
NORM_PHASES=(4,12,16)
PRODUCTS_PER_LANE=102
SAVING_PER_LANE=11*PRODUCTS_PER_LANE
NATURAL=("encoded-hello-cap255","encoded-fu2p2q-cap255","encoded-max48-cap255")


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def extract(archive_path,dest):
    checked(archive_path,ARCHIVE_SHA256)
    oracle="replay/gold/replay/gold/predecessor/pinned"
    with tarfile.open(archive_path) as archive:
        reference=json.load(archive.extractfile("replay/matched.json"))
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
    return reference,dest/oracle


def verify_products(path,depths):
    expected=[(0,coord,4,None) for coord in range(32)]
    expected.extend((1,0,resume,iteration) for iteration in range(2) for resume in (14,15,16))
    expected.extend((origin,coord,4,None) for coord in range(32) for origin in (2,3))
    assert len(expected)==PRODUCTS_PER_LANE
    with path.open() as stream:
        rows=iter(stream)
        for depth in range(1,depths+1):
            for lane in range(len(LANES)):
                for origin,coord,resume,iteration in expected:
                    a,*launch,left,right=next(rows).split()
                    p,*finish,magnitude=next(rows).split()
                    assert a=="A" and p=="P" and launch==finish
                    values=list(map(int,launch))
                    assert values[:5]==[lane,depth,origin,coord,resume]
                    assert iteration is None or values[5]==iteration
                    assert int(magnitude,16)==int(left,16)*int(right,16)
        assert next(rows,None) is None


def verify_profile(control,candidate,depths):
    verify_products(candidate/"norm-products.txt",depths)
    profile={}
    with (control/"norm-profile.txt").open() as before, (candidate/"norm-profile.txt").open() as after:
        for depth in range(1,depths+1):
            lanes={}
            for lane,name in enumerate(LANES):
                old,new=[list(map(int,next(stream).split())) for stream in (before,after)]
                assert old[:2]==new[:2]==[lane,depth] and old[4:]==new[4:]==[32,6,32,32]
                assert old[3]==16*PRODUCTS_PER_LANE and new[3]==5*PRODUCTS_PER_LANE
                assert old[2]-new[2]==SAVING_PER_LANE
                lanes[name]=dict(control_wait=old[2],candidate_wait=new[2],control_steps=old[3],
                                 candidate_steps=new[3],direct_products=96,rsqrt_products=6)
            profile[depth]=lanes
        assert next(before,None) is None and next(after,None) is None
    with (candidate/"norm-results.txt").open() as stream:
        for depth in range(1,depths+1):
            for lane in range(len(LANES)):
                for coordinate in range(32):
                    matching=list(map(int,next(stream).split()))
                    assert matching[:3]==[lane,depth,coordinate] and matching[-1]==0
        assert next(stream,None) is None
    return profile


def check_case(case,reference,gold,control,candidate,pair,prior,receipts):
    ref=reference["candidate"]
    depths=ref["done"]["positions"]
    for name in ADOPTED_TRACES:
        assert (control/name).read_bytes()==(gold/name).read_bytes(), (case,name)
        if name not in ("cache.kv","phases.txt"):
            assert (control/name).read_bytes()==(candidate/name).read_bytes(), (case,name)
    for name in NORM_TRACES:
        assert (control/name).read_bytes()==(candidate/name).read_bytes(), (case,name)
    profile=verify_profile(control,candidate,depths)
    assert receipts["control"]==receipts["candidate"]
    assert receipts["candidate"]==(depths,reference["scored_values"],reference["outputs"],reference["stop_reason"])
    phases={}
    cache={}
    for arm,folder in (("control",control),("candidate",candidate)):
        cache[arm]=pair["cache"](folder/"cache.kv")
        phases[arm]=prior["phase_rows"](folder,pair["cache"],pair["get_phases"])
    per_position=len(LANES)*SAVING_PER_LANE
    for boundary in ("prefix","done"):
        old,new=(phases[arm][boundary] for arm in ("control","candidate"))
        assert old==ref[boundary], (case,boundary)
        depth=old["positions"]
        saving=depth*per_position
        assert new["positions"]==depth and old["cycles"]-new["cycles"]==saving
        assert cache["control"][boundary][2]==cache["candidate"][boundary][2]
        assert old["first_valid"]==new["first_valid"]
        for stage,(left,right) in enumerate(zip(old["phases"],new["phases"],strict=True)):
            assert left-right==(depth*SAVING_PER_LANE if stage in NORM_PHASES else 0), (case,boundary,stage)
        for arm,sample in (("control",old),("candidate",new)):
            for name,phase in zip(LANES,NORM_PHASES,strict=True):
                assert sample["phases"][phase]==sum(profile[d][name][arm+"_wait"] for d in range(1,depth+1))
        assert new["done"]==(old["done"]-saving if old["done"] else 0)
        if old["first_valid"]:
            prefix=ref["prefix"]["positions"]
            assert old["first"]-new["first"]==per_position*prefix
            assert old["last"]-new["last"]==per_position*(prefix+reference["outputs"]-1)
        else:
            assert new["first"]==new["last"]==0
    print(case,phases["control"]["done"]["done"],phases["candidate"]["done"]["done"],
          "saved",depths*per_position,flush=True)
    return {**phases,**{name:reference[name] for name in ("outputs","scored_values","skipped_positions","stop_reason")},
            "saved_clocks":depths*per_position,"normalization_profile":profile}


def main(args):
    deadline=time.monotonic()+min(1800,args.deadline_epoch-time.time())
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    pair=load(kv260/"variants/attention-exp-pair-v2/replay_pair.py")
    prior=load(kv260/"variants/probability-div-v1/replay_probability.py")
    model=prior["load_model"](kv260)
    env=model["simulator"](args.verilator,kv260)
    out=args.output
    out.mkdir()
    reference,oracle=extract(args.archive,out/"gold")
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
        macros=["+define+PARTIAL_MULTIPLIER"]
        if arm=="candidate":
            macros.append("+define+DSP_NORMALIZATION")
        run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
             "--top-module","autonomous_core_tb","--Mdir",str(exe[arm].parent),"-o","simulation",*macros,
             *[str(rtl/(name+".sv")) for name in names],str(bench)],work,env,work/"compile.log",150,deadline)
    measured={}
    for case in (*NATURAL,*(name for name in reference if name not in NATURAL)):
        ref=reference[case]
        receipts={}
        for arm in ("control","candidate"):
            folder=out/arm/case
            folder.mkdir()
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
                                  out/"candidate"/case,pair,prior,receipts)
        (out/"matched.json").write_text(json.dumps(measured,indent=2)+"\n")
    assert len(measured)==7


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","archive","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
