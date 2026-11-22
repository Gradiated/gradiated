"""Run bounded dense-oracle tests and the archived exact seven-case model replay."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import runpy
import sys
import tarfile
import time

from materialise_ff_down import HERE, materialise, pinned

BASELINE = "ff-exp-div-rtl-20261116T214222Z"
BASELINE_PINS = {
    "model-results.json": "f223af06107bb811aa70af80ff87edae74954264b7b3b42d88e140e9f74f34d1",
    "source-closure.json": "883cb8e163da4a9ca05f3be0aacba8c7dd056a1031d5780fcf97aa7a0b6773c3",
    "simulation.tar.gz": "ec0fa44523269c854a7150667384910e0a6c65935ebc9c6d2f343218e6139ac9",
}
PREVIOUS_DRIVER = "a4620274518d87901d1d91e7ec75dd9bf95f05e944fa836bbb4f365abdcd777d"
SAVING = 4064


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data,out,indent=2,sort_keys=True)
        out.write("\n")


def driver(kv260):
    root=kv260/"variants/ff-exp-div-v1"
    path=root/"test_experiment.py"
    pinned(path,PREVIOUS_DRIVER)
    sys.path.insert(0,str(root))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def recover(old, target, cases):
    ledger=json.loads((old/"source-closure.json").read_bytes())["members"]
    paths={"oracle/autonomous_core_tb.sv":"prior-testbench.sv"}
    for file in ("model.hex","bos.hex"):
        paths[f"oracle/{file}"]=f"fixtures/model/reference/{file}"
    for case in cases:
        for file in ("input.hex","output.hex","scores.hex"):
            paths[f"oracle/{case}/{file}"]=f"fixtures/model/reference/{case}/{file}"
        for file in ("bos.csv","bus.events","cache.kv","phases.txt"):
            paths[f"candidate/{case}/{file}"]=f"{case}/{file}"
    with tarfile.open(old/"simulation.tar.gz") as archive:
        for name,rel in paths.items():
            member=archive.getmember(name)
            if not member.isfile() or member.size!=ledger[name]["bytes"]:
                raise ValueError(f"Invalid archived replay input {name}")
            data=archive.extractfile(member).read()
            if sha256(data).hexdigest()!=ledger[name]["sha256"]:
                raise ValueError(f"Archived replay input differs: {name}")
            dest=target/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open("xb") as file:
                file.write(data)
    bench=(target/"prior-testbench.sv").read_bytes()
    first,middle,last=bench.rpartition(b"endmodule")
    if not middle or last not in (b"", b"\n"):
        raise ValueError("Unexpected verified testbench terminator")
    (target/"autonomous_core_tb.sv").write_bytes(first+(HERE/"monitor.svh").read_bytes()+middle+last)


def component(args, root, prior, helper, env, deadline):
    output=root/"component"
    output.mkdir()
    fixture=runpy.run_path(str(HERE/"fixtures.py"))
    counts=fixture["write_fixtures"](output)
    binary=prior["compile_bench"](args,output/"obj",helper,env,
             (root/"control/rtl/dense.sv",root/"candidate/rtl/feedforward.sv"),
             HERE/"down_tb.sv","ff_down_tb",deadline)
    helper["run"]([str(binary),"+FIXTURES="+str(output)],output,env,output/"simulation.log",120,deadline)
    log=(output/"simulation.log").read_text()
    annotated=re.findall(r"^DOWN_PASS (\S+) stalled=(\d) control=(\d+) candidate=(\d+) terms=(\d+)$",log,re.M)
    observed=[(shape,int(stall),int(control),int(candidate),int(terms)) for shape,stall,control,candidate,terms in annotated]
    expected=[]
    for shape, spec in counts.items():
        rows=int(shape.split("x")[1])
        for stall in (0,1):
            extra=sum(2+row%4 for row in range(rows)) if stall else 0
            expected.append((shape,stall,spec["control_clocks"]+extra,spec["candidate_clocks"]+extra,spec["terms_per_pass"]))
    expected.extend([expected[1]]*3)
    resets=sorted(int(index) for index in re.findall(r"^DOWN_RESET_PASS phase=(\d)$",log,re.M))
    if sorted(expected)!=sorted(observed) or resets!=[0,1,2]:
        raise ValueError("Component receipt has unexpected run coverage or cycles")
    save(output/"counts.json",{"passed":True,"fixtures":counts,"observed":observed,"resets":resets,
         "oracle_terms_checked":2*sum(r[-1] for r in observed),"outputs_checked":2*sum(int(r[0].split("x")[1]) for r in observed)})
    print("Exact per-term, result, load-guard, stall and reset checks passed.",flush=True)


def compare(root,a,b,predictions):
    if a.keys()!=b.keys() or a.keys()!=predictions["cases"].keys():
        raise ValueError("Model label set changed")
    summaries={}
    for name,left in a.items():
        right=b[name]
        p=predictions["cases"][name]
        if left["outputs"]!=right["outputs"] or left["outputs"]!=p["outputs"]:
            raise ValueError("Output geometry changed")
        for field,value in p["candidate_cycles"].items():
            if right["done"][field]!=value:
                raise ValueError(f"Preregistered {field} count differs: {name}")
        for boundary in ("prefix","done"):
            x,y=left[boundary],right[boundary]
            expected=x["positions"]*SAVING
            if any(x[k]!=y[k] for k in ("first_valid","positions")) or x["cycles"]-y["cycles"]!=expected:
                raise ValueError("Cache boundary geometry or cycle law differs")
            if boundary=="done":
                for key in ("first","last","done"):
                    if x[key]-y[key]!=p["predicted_saved_cycles"][key]:
                        raise ValueError(f"Preregistered cycle saving differs: {name}/{key}")
            elif any(x[k]!=y[k] for k in ("first","last","done")):
                raise ValueError("Prefix emitted a timing counter")
            for i,(u,v) in enumerate(zip(x["phases"],y["phases"],strict=True)):
                if u-v!=(expected if i==14 else 0):
                    raise ValueError(f"Unexpected phase change: {name}/{boundary}/{i}")
        count=left["done"]["positions"]
        for arm,ff,read in (("control",24962,4096),("candidate",20898,32)):
            path=root/arm/name/"down-profile.txt"
            rows=[list(map(int,x.split())) for x in path.read_text().splitlines()]
            expected=[[i,ff,read,4096,32,32,0] for i in range(1,count+1)]
            if rows!=expected:
                raise ValueError(f"Observed internal down profile differs: {arm}/{name}")
        summaries[name]={"positions":count,"control_down_clocks":8256,"candidate_down_clocks":4192}
    return summaries


def main(args):
    deadline=time.monotonic()+min(1100,args.deadline_epoch-time.time())
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    prior=driver(kv260)
    helper=prior["previous_replay"](kv260)["load_helper"](kv260)
    env=helper["simulator"](args.verilator,kv260)
    old=args.repo/".agents/runtime/hardware/inference/outputs"/BASELINE
    for name,pin in BASELINE_PINS.items():
        pinned(old/name,pin)
    spec=json.loads((HERE/"manifest.json").read_bytes())
    prediction=json.loads(pinned(args.predictions,spec["preregistered_prediction_sha256"]))
    reference=json.loads((old/"model-results.json").read_bytes())["candidate"]
    root=args.output
    root.mkdir()
    for arm in ("control","candidate"):
        (root/arm).mkdir()
        names=materialise(kv260,root/arm/"rtl",arm=="candidate")
    generated=lambda n,arm:(root/arm/"rtl"/(n+".sv")).read_bytes()
    if len(names)!=11 or [x for x in names if generated(x,"control")!=generated(x,"candidate")]!=["feedforward"]:
        raise ValueError("Generated RTL change escaped the feed-forward source")
    old_source=generated("feedforward","control")
    new_source=generated("feedforward","candidate")
    prefix=b"module fixed_scalar_ff_exp ("
    if old_source[old_source.index(prefix):].rstrip()!=new_source[new_source.index(prefix):new_source.index(b"module dense_ff_down_pipeline #(")].rstrip():
        raise ValueError("Prior exact exponential clone changed")
    archived=root/"pinned"
    recover(old,archived,reference)
    component(args,root,prior,helper,env,deadline)
    control=prior["model"](args,root/"control",archived,reference,helper,env,False,names,deadline)
    if control!=reference:
        raise ValueError("Regenerated selected control differs from archived measurements")
    candidate=prior["model"](args,root/"candidate",archived,reference,helper,env,True,names,deadline)
    profiles=compare(root,control,candidate,prediction)
    save(root/"matched.json",{"control":control,"candidate":candidate})
    save(root/"observed-down-profile.json",profiles)
    print("Seven matched cases and all internal down profiles passed.",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("repo","verilator","output","predictions"):
        p.add_argument("--"+name,type=lambda value:Path(value).resolve(),required=True)
    p.add_argument("--deadline-epoch",type=float,required=True)
    main(p.parse_args())
