"""Measure isolated projection read-ahead and verify their combined cycle law."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_projections import ARMS, HERE, checked, materialise

ARCHIVE_SHA256="0d24aaf34d27854610d4d421e86000b4164452d508a13f0da71cb781fee89bb3"
TRACES=("attention-events.txt","attention-pairs.txt","bos.csv","cache-addresses.bin","cache.kv",
        "divider-values.txt","down-profile.txt","overlap-profile.txt","phases.txt","probability-profile.txt",
        "feedforward-elements.txt","feedforward-products.txt","feedforward-profile.txt",
        "norm-products.txt","norm-outputs.txt","norm-ownership.txt")
NUMERICAL=tuple(name for name in TRACES if name not in
                ("cache.kv","phases.txt","down-profile.txt","feedforward-profile.txt"))
LANES=(("qkv","front.projection",96),("output","output_projection",32),
       ("gate_up","ff.gate_dense",128),("gate_up","ff.up_dense",128))
NATURAL=("encoded-hello-cap255","encoded-fu2p2q-cap255","encoded-max48-cap255")
SINGLES=("qkv-read-ahead-v1","attention-output-read-ahead-v1","ff-gate-up-read-ahead-v1")
COMBOS=("projections-read-ahead-v1","qkv-attention-output-read-ahead-v1")
PREDICTION={"qkv":2976,"output":992,"gate_up":31}


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def signature(path):
    with path.open("rb") as stream:
        return file_digest(stream,"sha256").hexdigest()


def extract(archive_path,dest):
    checked(archive_path,ARCHIVE_SHA256)
    with tarfile.open(archive_path) as archive:
        reference=json.load(archive.extractfile("replay/matched.json"))
        files=["replay/candidate/autonomous_core_tb.sv","replay/gold/model.hex","replay/gold/bos.hex"]
        for case in reference:
            files.extend(f"replay/gold/{case}/{name}.hex" for name in ("input","output","scores"))
            files.extend(f"replay/candidate/{case}/{name}" for name in TRACES)
        for name in files:
            item=archive.getmember(name)
            if not item.isfile():
                raise ValueError(f"Expected a regular archive member: {name}")
            path=dest/name
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as stream:
                stream.write(archive.extractfile(item).read())
    return reference


def monitor(scopes):
    rows=[]
    for lane,(scope,name,_) in enumerate(LANES):
        node=f"dut.core.{name}"
        fields={
            "state":"state","row":"row","consumed_row":"result_row",
            "step_row":"step_row","step_index":"step_index","valid":"result_valid",
            "ready":"result_ready","clipped":"saturated","step":"step_valid","result":"result",
            "address":"read_address" if scope in scopes else "address",
        }
        for signal,field in fields.items():
            rows.append(f"assign pr_{signal}[{lane}] = {node}.{field};")
        advance=f"{node}.advance_mac" if scope in scopes else "1'b0"
        rows.append(f"assign pr_advance[{lane}] = {advance};")
    return (HERE/"monitor.svh").read_text().replace("// PROJECTION_CONNECTIONS","\n".join(rows))


def text_rows(path):
    with path.open() as stream:
        for line in stream:
            yield tuple(map(int,line.split()))


def lane_profile(folder,scopes,depths):
    results=[[] for _ in LANES]
    for lane,depth,reads,mac,rounds,holds,issues,rows in text_rows(folder/"projection-profile.txt"):
        scope,_,wanted=LANES[lane]
        expected_reads=wanted*(1 if scope in scopes else 32)
        assert depth==len(results[lane])+1
        assert (reads,mac,rounds,issues,rows)==(expected_reads,32*wanted,wanted,32*wanted,wanted)
        results[lane].append(dict(reads=reads,mac=mac,round=rounds,holds=holds,issues=issues,rows=rows))
    assert all(len(lane)==depths for lane in results)
    first=list(text_rows(folder/"projection-gate-up-wait.txt"))
    assert len(first)==depths
    for depth,(reported,_,early,late) in enumerate(first,1):
        assert reported==depth and early==(34 if "gate_up" in scopes else 65) and late==0
        gate,up=(results[lane][depth-1] for lane in (2,3))
        assert gate==up
    return results,first


def matching_results(path,depths):
    progress=[0]*len(LANES)
    for lane,depth,row,value,clip in text_rows(path):
        _,_,rows=LANES[lane]
        assert progress[lane] == (depth-1)*rows+row and -32768<=value<=32767 and clip in (0,1)
        progress[lane]+=1
    assert progress==[depths*rows for _,_,rows in LANES]


def ff_profile(control,candidate,delta,depths):
    for name,absolute,pairwait in (("down-profile.txt",1,None),("feedforward-profile.txt",1,2)):
        before=text_rows(control/name)
        after=text_rows(candidate/name)
        count=0
        for old,new in zip(before,after,strict=True):
            assert len(old)==len(new)
            assert all(a-b==(delta if i in (absolute,pairwait) else 0)
                       for i,(a,b) in enumerate(zip(old,new,strict=True)))
            count+=1
        assert count==depths


def audit(case,row,gold,control,candidate,scopes,receipt,pair,prior):
    ref=row["candidate"]
    depths=ref["done"]["positions"]
    assert receipt==(depths,row["scored_values"],row["outputs"],row["stop_reason"])
    stage_deltas={6:PREDICTION["qkv"] if "qkv" in scopes else 0,
                  10:PREDICTION["output"] if "output" in scopes else 0,
                  14:PREDICTION["gate_up"] if "gate_up" in scopes else 0}
    per_position=sum(stage_deltas.values())
    if not scopes:
        for name in TRACES:
            assert signature(control/name)==signature(gold/name), (case,name)
        matching_results(control/"projection-outputs.txt",depths)
    for name in (*NUMERICAL,"projection-outputs.txt"):
        assert signature(control/name)==signature(candidate/name), (case,name)
    before=pair["cache"](control/"cache.kv")
    after=pair["cache"](candidate/"cache.kv")
    old=prior["phase_rows"](control,pair["cache"],pair["get_phases"])
    new=prior["phase_rows"](candidate,pair["cache"],pair["get_phases"])
    lane_data,gate=lane_profile(candidate,scopes,depths)
    if scopes:
        original_gates=list(text_rows(control/"projection-gate-up-wait.txt"))
        for source,target in zip(original_gates,gate,strict=True):
            assert source[0]==target[0] and source[1]-target[1]==source[2]-target[2]==stage_deltas[14]
        ff_profile(control,candidate,stage_deltas[14],depths)
    for boundary in ("prefix","done"):
        a,b=old[boundary],new[boundary]
        assert a==ref[boundary], (case,boundary)
        count=a["positions"]
        assert b["positions"]==count and a["cycles"]-b["cycles"]==count*per_position
        assert before[boundary][2]==after[boundary][2]
        assert a["first_valid"]==b["first_valid"]
        for stage,(x,y) in enumerate(zip(a["phases"],b["phases"],strict=True)):
            assert x-y==count*stage_deltas.get(stage,0), (case,boundary,stage,x,y)
        assert b["done"]==(a["done"]-count*per_position if a["done"] else 0)
        if a["first_valid"]:
            prefix=ref["prefix"]["positions"]
            assert a["first"]-b["first"]==per_position*prefix
            assert a["last"]-b["last"]==per_position*(prefix+row["outputs"]-1)
        else:
            assert b["first"]==b["last"]==0
    last=lane_data[0][-1]
    assert last["rows"]==96
    return {**new,**{name:row[name] for name in ("outputs","scored_values","skipped_positions","stop_reason")},
            "saved_clocks":depths*per_position,
            "projection_profile":dict(lanes=[dict(label=name,reads=sum(entry["reads"] for entry in records),
                      mac=sum(entry["mac"] for entry in records),holds=sum(entry["holds"] for entry in records),
                      rows=sum(entry["rows"] for entry in records),issues=sum(entry["issues"] for entry in records))
                                              for (_,name,_),records in zip(LANES,lane_data,strict=True)],
                                      consumer_first_pair_wait=sum(row[2] for row in gate),
                                      consumer_next_pair_wait=sum(row[3] for row in gate),
                                      saved_per_position={str(k):v for k,v in stage_deltas.items()})}


def trial(arm,reference,origin,out,kv260,verilator,model,env,pair,prior):
    deadline=time.monotonic()+1800
    run=model["run"]
    work=out/arm
    work.mkdir()
    rtl=work/"rtl"
    names=materialise(kv260,rtl,arm)
    bench=work/"autonomous_core_tb.sv"
    bench.write_text(origin.removesuffix("endmodule\n")+monitor(ARMS[arm])+"endmodule\n")
    exe=work/"obj/simulation"
    run([str(verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","autonomous_core_tb","--Mdir",str(exe.parent),"-o","simulation",
         "+define+PARTIAL_MULTIPLIER",*[str(rtl/(name+".sv")) for name in names],str(bench)],
        work,env,work/"compile.log",150,deadline)
    measured={}
    for case in (*NATURAL,*(name for name in reference if name not in NATURAL)):
        ref=reference[case]
        folder=work/case
        folder.mkdir()
        oracle=out/"gold/replay/gold"
        params=dict(MODEL=oracle/"model.hex",SCORES=oracle/"bos.hex",INPUT=oracle/case/"input.hex",
                    OUTPUT=oracle/case/"output.hex",ALLSCORES=oracle/case/"scores.hex",
                    CSV=folder/"bus.events",RETURNS=folder/"bos.csv",PREFIX=ref["candidate"]["prefix"]["positions"],
                    OUTPUTS=ref["outputs"],POSITIONS=ref["candidate"]["done"]["positions"],
                    CAP=int(case.rsplit("-cap",1)[1]),SKIP=1,CACHE=folder/"cache.kv",
                    PHASE=folder/"phases.txt",REASON=ref["stop_reason"])
        run([str(exe),*[f"+{key}={value}" for key,value in params.items()]],folder,env,
            folder/"simulation.log",150,deadline)
        completion=re.search(r"PASS autonomous_real_core positions=(\d+) exact_scores=(\d+) outputs=(\d+) "
                             r"reason=(\d+) legacy_BOS_scores=640",(folder/"simulation.log").read_text())
        assert completion,(arm,case)
        measured[case]=audit(case,ref,out/"gold/replay/candidate"/case,out/"control"/case,folder,ARMS[arm],
                             tuple(map(int,completion.groups())),pair,prior)
        print(arm,case,measured[case]["done"]["done"],measured[case]["saved_clocks"],flush=True)
        (work/"matched.json").write_text(json.dumps(measured,indent=2)+"\n")
    return measured


def main(args):
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    pair=load(kv260/"variants/attention-exp-pair-v2/replay_pair.py")
    prior=load(kv260/"variants/probability-div-v1/replay_probability.py")
    model=prior["load_model"](kv260)
    env=model["simulator"](args.verilator,kv260)
    out=args.output
    out.mkdir()
    reference=extract(args.archive,out/"gold")
    origin=(out/"gold/replay/candidate/autonomous_core_tb.sv").read_text()
    assert origin.endswith("\nendmodule\n") and origin.count("endmodule")==1
    results={}
    for arm in ("control",*SINGLES,*COMBOS):
        results[arm]=trial(arm,reference,origin,out,kv260,args.verilator,model,env,pair,prior)
        if arm in COMBOS:
            for case,row in results[arm].items():
                wanted=sum(results[earlier][case]["saved_clocks"]
                           for earlier in SINGLES if ARMS[earlier][0] in ARMS[arm])
                assert row["saved_clocks"]==wanted,(arm,case)
        (out/"all-arms.json").write_text(json.dumps(results,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","archive","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    main(parser.parse_args())
