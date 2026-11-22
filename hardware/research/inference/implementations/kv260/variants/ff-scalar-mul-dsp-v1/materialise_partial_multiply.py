"""Replace one Exp18 feed-forward scalar multiplier with registered DSP partial products."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL = "variants/probability-div-v1"


def digest(data):
    return sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or digest(data) != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Unexpected adopted scalar source: {old}")
    return source.replace(old,new,1)


def specialise(source, datapath):
    changes = (
        (
            "RSQ_INDEX, RSQ_LOAD, RSQ_YY, RSQ_MY, RSQ_FACTOR, RSQ_UPDATE, DIV_FINISH",
            "RSQ_INDEX, RSQ_LOAD, RSQ_YY, RSQ_MY, RSQ_FACTOR, RSQ_UPDATE, DIV_FINISH,\n"
            "        MUL_ROWS, MUL_PAIRS, MUL_REDUCE, MUL_FINISH",
        ),
        (
            """    logic [63:0] multiplicand;
    logic [127:0] product_sum, next_product;
    logic [67:0] digit_product, upper_sum;""",
            """    logic [63:0] multiplicand, multiplier;
    logic [79:0] product_rows[0:3];
    logic [95:0] product_halves[0:1];
    logic [127:0] product_sum;""",
        ),
        (
            """        // Consume one base-16 digit. The lower half initially contains |b|.
        // Add the digit product into an extended upper half before shifting.
        digit_product=68'(multiplicand)*product_sum[3:0];
        upper_sum={4'd0,product_sum[127:64]}+digit_product;
        next_product={upper_sum,product_sum[63:4]};
""",
            "",
        ),
        (
            "    task automatic multiply_start",
            datapath+"    task automatic multiply_start",
        ),
        (
            "            product_sum<={64'd0,magnitude(b)};remaining<=16;",
            "            multiplier<=magnitude(b);",
        ),
        (
            "            multiplicand<=0;product_sum<=0;",
            "            multiplicand<=0;multiplier<=0;",
        ),
        (
            """                MUL_STEP: begin
                    product_sum<=next_product;
                    remaining<=remaining-7'd1;
                    if(remaining==1)begin
                        if(next_product>{64'd0,SIGNED_MAX})reject();
                        else begin
                            math_value<=negative ? -$signed(next_product[63:0]) : $signed(next_product[63:0]);
                            state<=return_state;
                        end
                    end
                end""",
            """                MUL_STEP: state<=MUL_ROWS;
                MUL_ROWS: state<=MUL_PAIRS;
                MUL_PAIRS: state<=MUL_REDUCE;
                MUL_REDUCE: state<=MUL_FINISH;
                MUL_FINISH: begin
                    if(product_sum>{64'd0,SIGNED_MAX})reject();
                    else begin
                        math_value<=negative ? -$signed(product_sum[63:0]) : $signed(product_sum[63:0]);
                        state<=return_state;
                    end
                end""",
        ),
    )
    for old,new in changes:
        source=replace_once(source,old,new)
    return source


def materialise(kv260,output,candidate):
    spec=json.loads((HERE/"manifest.json").read_bytes())
    prior=kv260/CONTROL
    maker=prior/"materialise_probability_div.py"
    checked(maker,spec["control_generator_sha256"])
    checked(prior/"manifest.json",spec["control_variant_sha256"])
    names=runpy.run_path(str(maker))["materialise"](kv260,output,True)
    ledger=output/"source-manifest.json"
    hashes=json.loads(checked(ledger,spec["control_rtl_manifest_sha256"]))
    for name,expected in hashes.items():
        checked(output/(name+".sv"),expected)
    if candidate:
        feedforward=output/"feedforward.sv"
        datapath=checked(HERE/"multiply_datapath.svh",spec["datapath_sha256"]).decode()
        data=specialise(feedforward.read_text(),datapath).encode()
        stamp=digest(data)
        if stamp!=spec["candidate_feedforward_sha256"]:
            raise ValueError("Generated feed-forward scalar source differs")
        feedforward.write_bytes(data)
        hashes["feedforward"]=stamp
        ledger.write_text(json.dumps(hashes,indent=2)+"\n")
    return names


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm=="candidate")
