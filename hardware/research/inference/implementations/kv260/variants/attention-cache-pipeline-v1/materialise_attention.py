"""Generate attention-only cache scheduling from the adopted down-projection source."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL_PIN = "3aa9cb030aae469ba235ae9092ea255866cc960ab57adb666117e8e799cbf93d"
PRIOR = "variants/ff-down-pipeline-v1"


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Source pin changed: {path}")
    return data


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source match: {old}")
    return text.replace(old, new)


def pipeline(text):
    text = once(text, "    logic scalar_table_ready, scalar_error;",
                "    logic scalar_table_ready, scalar_error;\n"
                "    logic next_score_coordinate, next_value_position;")
    text = once(text, """    assign cache_read_valid=!reset && (state==SCORE_REQ || state==CONTEXT_REQ);
    assign cache_read_position={1'b0,position};
    assign cache_read_coordinate={1'b0,head,coordinate};""",
                """    // DATA has consumed the sole pending cache response. On MAC we can
    // request the next term while the current registered operands are used.
    // A refused request keeps its address through the following REQ state.
    assign next_score_coordinate=state==SCORE_MAC && coordinate!=4'd15;
    assign next_value_position=state==CONTEXT_MAC && {1'b0,position}+9'd1<length;
    assign cache_read_valid=!reset &&
        (state==SCORE_REQ || state==CONTEXT_REQ || next_score_coordinate || next_value_position);
    assign cache_read_position={1'b0,position}+{8'd0,next_value_position};
    assign cache_read_coordinate={1'b0,head,coordinate+{3'd0,next_score_coordinate}};""")
    text = once(text, "else begin coordinate<=coordinate+1'b1;state<=SCORE_REQ;end",
                """else begin
                        coordinate<=coordinate+1'b1;
                        state<=cache_read_ready ? SCORE_DATA : SCORE_REQ;
                    end""")
    return once(text, "else begin position<=position+1'b1;state<=CONTEXT_REQ;end",
                """else begin
                        position<=position+1'b1;
                        state<=cache_read_ready ? CONTEXT_DATA : CONTEXT_REQ;
                    end""")


def materialise(kv260, output, candidate):
    spec=json.loads((HERE/"manifest.json").read_bytes())
    generator=kv260/PRIOR/"materialise_ff_down.py"
    checked(generator,spec["control_generator_sha256"])
    checked(kv260/PRIOR/"manifest.json",spec["control_manifest_sha256"])
    names=runpy.run_path(str(generator))["materialise"](kv260,output,True)
    ledger=output/"source-manifest.json"
    pins=json.loads(ledger.read_bytes())
    if pins!=spec["control_rtl"]:
        raise ValueError("Generated adopted closure differs from the archived baseline")
    for name in names:
        checked(output/(name+".sv"),pins[name])
    if candidate:
        path=output/"attention.sv"
        before=checked(path,CONTROL_PIN).decode()
        result=pipeline(before).encode()
        if sha256(result).hexdigest()!=spec["candidate_attention_sha256"]:
            raise ValueError("Unexpected cache scheduling source")
        path.write_bytes(result)
        pins["attention"]=spec["candidate_attention_sha256"]
        ledger.write_text(json.dumps(pins,indent=2)+"\n")
    return names


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm=="candidate")
