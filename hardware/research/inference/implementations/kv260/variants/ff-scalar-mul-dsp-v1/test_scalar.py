"""Qualify candidate widths, signs, raw products, latency and command behaviour."""

import argparse
import json
from pathlib import Path
import random
import runpy
import sys
import time

from materialise_partial_multiply import HERE, checked, materialise

MODEL_SHA256="e0c4910071fb1577fea78e1b6cc7474bcfb2d64898713ec945bf1ed8dcc2df43"


def load(path):
    sys.path.insert(0,str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def fixtures(oracle, model_file, output):
    words=[int(line,16) for line in checked(model_file,MODEL_SHA256).splitlines()]
    offset=sum((10240,1024,1024,1024,1024,4096,4096,4096,32,32,32,2048))
    exp=words[offset:offset+257]
    rsqrt=words[offset+257:]
    assert len(words)==29281 and len(exp)==257 and len(rsqrt)==256
    for name,values in (("exp",exp),("rsqrt",rsqrt)):
        (output/(name+".hex")).write_text("".join(f"{value:08x}\n" for value in values))
    inputs={(entry["op"],entry["a"],entry["b"],entry["shift"])
            for entry in oracle["scalar_vivado_cases"](exp,rsqrt)}
    inputs.update((op,0,0,0) for op in (5,6,7))
    limb_edges={0,-(1<<63),(1<<63)-1}
    for bits in (1,15,16,17,31,32,33,47,48,49,62):
        for delta in (-1,0,1):
            value=(1<<bits)+delta
            limb_edges.update((-value,value))
    inputs.update((2,a,b,0) for a in limb_edges for b in limb_edges)
    rng=random.Random(2026111919)
    for _ in range(4096):
        a_bits=rng.randrange(1,64)
        b_bits=rng.randrange(1,64)
        a=rng.randrange(-(1<<a_bits),1<<a_bits)
        b=rng.randrange(-(1<<b_bits),1<<b_bits)
        inputs.add((2,a,b,0))
    rows=[]
    counts={"rows":len(inputs),"multiply_rows":0,"valid_multiply":0,"overflow_multiply":0}
    for op,a,b,shift in sorted(inputs):
        try:
            result,exponent=oracle["scalar_reference"](op,a,b,shift,exp,rsqrt)
            error=0
        except (ValueError,OverflowError):
            result=exponent=0
            error=1
        product=abs(a)*abs(b) if op==2 else 0
        products=0
        if op==2:
            products=1
            counts["multiply_rows"]+=1
            counts["overflow_multiply" if error else "valid_multiply"]+=1
        elif op==3 and not error:
            products=int(-1048576<=a<=0)
        elif op==4 and not error:
            products=6
        elif op in (3,4):
            products=-1  # Compare control/candidate in case an internal operation rejected.
        values=(op,a,b,shift,result,exponent,error,product)
        widths=(4,64,64,8,64,8,4,128)
        row=" ".join(f"{v&((1<<n)-1):0{n//4}x}" for v,n in zip(values,widths,strict=True))
        rows.append(f"{row} {products}\n")
    (output/"scalar.hex").write_text("".join(rows))
    return counts


def main(args):
    kv260=args.repo/"hardware/research/inference/implementations/kv260"
    model=load(kv260/"variants/scalar-mul-v1/test_model.py")
    oracle=load(kv260/"tools/rtl.py")
    env=model["simulator"](args.verilator,kv260)
    deadline=time.monotonic()+min(350,args.deadline_epoch-time.time())
    out=args.output
    out.mkdir()
    files=[]
    for mode in ("control","candidate"):
        rtl=out/mode
        materialise(kv260,rtl,mode=="candidate")
        source=(rtl/"feedforward.sv").read_text()
        marker="module fixed_scalar_ff_exp ("
        assert source.count(marker)==1
        original,helper=source.split(marker)
        assert original.rstrip().endswith("`timescale 1ns/1ps")
        helper=helper.split("\nendmodule",1)[0]+"\nendmodule\n"
        name="fixed_scalar_mul_control" if mode=="control" else "fixed_scalar_ff_exp"
        path=out/(name+".sv")
        path.write_text("`timescale 1ns/1ps\nmodule "+name+" ("+helper)
        files.append(path)
    cases=fixtures(oracle,args.model,out)
    exe=out/"obj/simulation"
    run=model["run"]
    run([str(args.verilator/"bin/verilator"),"--binary","--timing","--assert","-Wno-fatal","-j","2",
         "--top-module","partial_multiply_scalar_tb","--Mdir",str(exe.parent),"-o","simulation",
         *map(str,files),str(HERE/"scalar_tb.sv")],out,env,out/"compile.log",150,deadline)
    run([str(exe),f"+FIXTURES={out}",f"+ROWS={cases['rows']}"],out,env,out/"simulation.log",120,deadline)
    assert f"PASS scalar: {cases['rows']}" in (out/"simulation.log").read_text()
    (out/"summary.json").write_text(json.dumps(dict(cases,all_exact=True,reset_states=5,control_steps=16,
                                                   candidate_steps=5),indent=2)+"\n")
    print(cases,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("repo","verilator","model","output"):
        parser.add_argument("--"+key,type=lambda value:Path(value).resolve(),required=True)
    parser.add_argument("--deadline-epoch",type=float,required=True)
    main(parser.parse_args())
