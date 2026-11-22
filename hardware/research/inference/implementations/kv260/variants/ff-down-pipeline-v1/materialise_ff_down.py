"""Generate the adopted divider RTL with an isolated pipelined down projection."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL = "variants/ff-exp-div-v1"
CONTROL_PINS = {
    "manifest.json": "5991b5472be92b0cab51f4422c52e9e1cfe443369909f967c9b8d8af8989934c",
    "materialise_ff_exp.py": "49557f97d15202b3a00bbdcb2930dc127d2455df222fc36bce4087e4e09607b6",
}
PIPELINE_GENERATOR_PIN = "1dbb63687097ca0a44dbaa6548cd3be4afd7ded23f31f2d06f4bcf5a4dc39a44"
RTL_PINS = {
    "feedforward": "e6401554a7b4f44b60613880e4f0fd59756f9edf45acfa7fb0b81f4bfb0c1a64",
    "dense": "561e82c83a15071ed45e251329a15fc212b9b1dca4fdb30ed24b33d878613ac9",
    "transformer": "dc5851764926a6b5e3638aea760eb025d86da844241497a175e125c6210d0e2d",
}


def pinned(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Artifact changed: {path}")
    return data


def replace_one(text, old, new):
    if text.count(old)!=1:
        raise ValueError(f"Expected one RTL source match: {old}")
    return text.replace(old,new,1)


def specialise(kv260, feedforward, dense):
    prior=kv260/"variants/logits-pipeline-v1/materialise.py"
    pinned(prior, PIPELINE_GENERATOR_PIN)
    pipeline=runpy.run_path(str(prior))["pipeline"]
    clone=replace_one(pipeline(dense),"module logits_dense #(","module dense_ff_down_pipeline #(")
    feedforward=replace_one(feedforward,"    dense #(.INPUTS(128),.OUTPUTS(32)",
                           "    dense_ff_down_pipeline #(.INPUTS(128),.OUTPUTS(32)")
    return feedforward+"\n"+clone

def materialise(kv260, output, candidate):
    control=kv260/CONTROL
    for name,expected in CONTROL_PINS.items():
        pinned(control/name,expected)
    generator=runpy.run_path(str(control/"materialise_ff_exp.py"))["materialise"]
    names=generator(kv260,output,True)
    for name,expected in RTL_PINS.items():
        pinned(output/(name+".sv"),expected)
    if candidate:
        manifest=json.loads((HERE/"manifest.json").read_bytes())
        path=output/"feedforward.sv"
        result=specialise(kv260,path.read_text(),(output/"dense.sv").read_text()).encode()
        observed=sha256(result).hexdigest()
        if observed!=manifest["feedforward_sha256"]:
            raise ValueError(f"Candidate feed-forward closure changed: {observed}")
        path.write_bytes(result)
        ledger=output/"source-manifest.json"
        hashes=json.loads(ledger.read_bytes())
        hashes["feedforward"]=observed
        ledger.write_text(json.dumps(hashes,indent=2)+"\n")
    return names


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm=="candidate")
