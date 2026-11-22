"""Pin the qualified replay and directed arithmetic for an offline route."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

PROTOCOL=Path("hardware/research/inference/experiments/kv260-attention-value-pair-v1.md")
PROTOCOL_PIN="4ea8a1374c41941a281656c6f2d614673585d23ab6105e49e8c1240037be2b7a"
EXPECTED=("attention","frontend","kv_cache","transformer")
NAME="attention-value-pair-v1"
PROMPTS=("encoded-hello-cap255","encoded-fu2p2q-cap255","encoded-max48-cap255")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def save(path,value):
    with path.open("x") as stream:
        stream.write(json.dumps(value,indent=2,sort_keys=True)+"\n")


def invoke(args):
    model=args.replay/"matched.json"
    depth=args.replay/"depth-results.json"
    directed=args.directed/"summary.json"
    cases=json.loads(model.read_bytes())
    observations=json.loads(depth.read_bytes())
    checked=json.loads(directed.read_bytes())
    assert len(cases)==7 and set(map(int,observations))=={1,16,64,128,256} and checked["all_exact"]
    for case in PROMPTS:
        row=cases[case]
        count=row["control"]["done"]["positions"]
        assert row["stop_reason"]==1 and row["saved_clocks"]==16*count*(count+2)
        for key,n in (("first",row["control"]["prefix"]["positions"]),("last",count-1),("done",count)):
            a,b=(row[arm]["done"][key] for arm in ("control","candidate"))
            assert a-b==16*n*(n+2)
    for d,values in observations.items():
        a,b=(values[arm] for arm in ("control","candidate"))
        assert a["scored_step_cycles"]-b["scored_step_cycles"]==32*int(d)+16
        assert a["value_phase_cycles"]-b["value_phase_cycles"]==32*int(d)+16
    manifests={}
    report={}
    for arm in ("control","candidate"):
        path=args.replay/arm/"rtl/source-manifest.json"
        assert path.read_bytes()==(args.directed/arm/"rtl/source-manifest.json").read_bytes()
        report[arm+"_rtl_manifest_sha256"]=digest(path)
        manifests[arm]=json.loads(path.read_bytes())
    assert sorted(k for k,v in manifests["control"].items() if v!=manifests["candidate"][k])==list(EXPECTED)
    assert digest(args.repo/PROTOCOL)==PROTOCOL_PIN
    args.output.mkdir()
    qualification=args.output/"qualification-summary.json"
    save(qualification,{**report,"candidate":NAME,"passed":True,"model_cases":7,
                        "evidence":[{"name":name,"path":str(path),"sha256":digest(path)} for name,path in
                                    (("model-results.json",model),("depth-results.json",depth),("directed-results.json",directed))]})
    gate=args.output/"rtl-build-gate.json"
    save(gate,{**report,"candidate":NAME,"protocol":str(PROTOCOL),"protocol_sha256":PROTOCOL_PIN,
               "qualification_summary":str(qualification),"qualification_summary_sha256":digest(qualification),
               "changed_rtl":list(EXPECTED),"selected_sites":["frontend.cache","transformer.att"]})
    print(gate,digest(gate),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("repo","replay","directed","output"):
        parser.add_argument("--"+arg,type=lambda value:Path(value).resolve(),required=True)
    invoke(parser.parse_args())
