"""Generate the exact one-lane control or one final-score banked variant."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL_GENERATOR = "1dbb63687097ca0a44dbaa6548cd3be4afd7ded23f31f2d06f4bcf5a4dc39a44"
CONTROL_MANIFEST = "c2d75fa5f849f744de17cf18ebbaf6006394ec83749f5d4cce7fd3c6569136cd"


def pinned(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Source changed: {path}")
    return data


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source location: {old}")
    return text.replace(old,new)


def specialised(transformer, module, lanes):
    core, separator, prior = transformer.partition("\nmodule logits_dense #(")
    if not separator or "\nmodule " in prior or not prior.rstrip().endswith("endmodule"):
        raise ValueError("Unexpected one-lane closure")
    core = replace_once(core,
        "    logits_dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(32)) logits (",
        f"    logits_parallel #(.LANES({lanes})) logits (")
    core = replace_once(core,
        """        .result_row(l_row),.result(l_result),.saturated(l_clip),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());""",
        "        .result_row(l_row),.result(l_result),.saturated(l_clip));")
    return core+"\n"+module


def materialise(kv260, output, lanes):
    if lanes not in (1,2,4):
        raise ValueError("Expected one, two or four lanes")
    control = kv260/"variants/logits-pipeline-v1"
    generator = control/"materialise.py"
    pinned(generator,CONTROL_GENERATOR)
    source = json.loads(pinned(control/"manifest.json",CONTROL_MANIFEST))
    names = runpy.run_path(str(generator))["materialise"](kv260,output)
    for name in names:
        pinned(output/(name+".sv"),source[name])
    if lanes != 1:
        transform = output/"transformer.sv"
        module = (HERE/"logits_parallel.sv").read_text()
        generated = specialised(transform.read_text(),module,lanes).encode()
        expected = json.loads((HERE/"manifest.json").read_text())
        if sha256(module.encode()).hexdigest() != expected["parallel_module_sha256"]:
            raise ValueError("Parallel source template changed")
        source["transformer"] = sha256(generated).hexdigest()
        if source["transformer"] != expected["arms"][str(lanes)]:
            raise ValueError("Candidate transformer closure changed")
        transform.write_bytes(generated)
    (output/"source-manifest.json").write_text(json.dumps(source,indent=2)+"\n")
    return names


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kv260",type=Path,default=HERE.parents[1])
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--lanes",type=int,choices=(1,2,4),required=True)
    a=p.parse_args()
    materialise(a.kv260,a.output,a.lanes)
