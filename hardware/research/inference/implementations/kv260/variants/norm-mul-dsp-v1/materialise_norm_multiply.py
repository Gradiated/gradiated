"""Use the verified five-clock multiplier in each dedicated normalization scalar."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE=Path(__file__).resolve().parent
CONTROL="variants/ff-scalar-mul-dsp-v1"


def digest(data):
    return sha256(data).hexdigest()


def checked(path,expected):
    data=path.read_bytes()
    if path.is_symlink() or digest(data)!=expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def specialise(controller,scalar,datapath,prior):
    replace=prior["replace_once"]
    clone=prior["specialise"](scalar,datapath)
    clone=replace(clone,"module fixed_scalar (","module fixed_scalar_norm_dsp (")
    return replace(controller,"    fixed_scalar scalar(","    fixed_scalar_norm_dsp scalar(")+"\n"+clone


def materialise(kv260,output,candidate):
    spec=json.loads((HERE/"manifest.json").read_bytes())
    control=kv260/CONTROL
    generator=control/"materialise_partial_multiply.py"
    checked(generator,spec["control_generator_sha256"])
    checked(control/"manifest.json",spec["control_variant_manifest_sha256"])
    prior=runpy.run_path(str(generator))
    names=prior["materialise"](kv260,output,True)
    ledger=output/"source-manifest.json"
    hashes=json.loads(checked(ledger,spec["control_rtl_manifest_sha256"]))
    for name,expected in hashes.items():
        checked(output/(name+".sv"),expected)
    if candidate:
        datapath=checked(control/"multiply_datapath.svh",spec["datapath_sha256"]).decode()
        rmsnorm=output/"rmsnorm.sv"
        data=specialise(rmsnorm.read_text(),(output/"fixed_scalar.sv").read_text(),datapath,prior).encode()
        stamp=digest(data)
        if stamp!=spec["candidate_rmsnorm_sha256"]:
            raise ValueError("Generated normalization source differs")
        rmsnorm.write_bytes(data)
        hashes["rmsnorm"]=stamp
        ledger.write_text(json.dumps(hashes,indent=2)+"\n")
    return names


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm=="candidate")
