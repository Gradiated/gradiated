"""Reproduce the scalar-mul closure with a radix-four restoring divider."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
BASELINE_MANIFEST = "46220377267d0dada7e2dbc57a4e2a159e644b2ed5ceed1923df0528e2a87f8a"
BASELINE_GENERATOR = "1d73a8acb7158002c8ddb7e92b4ea67c4a8624e756bb91a9ed08559ffac44193"
DIV_STEPS = 32


def pin(path, wanted):
    data = path.read_bytes()
    if sha256(data).hexdigest()!=wanted:
        raise ValueError(f"Baseline source changed: {path}")
    return data


def divider(text):
    changes=(
        ("64-by-4 digit multiplier and bit-serial division.",
         "64-by-4 digit multiplier and two-bit restoring division."),
        ("RSQ_FACTOR, RSQ_UPDATE", "RSQ_FACTOR, RSQ_UPDATE, DIV_FINISH"),
        ("logic [63:0] numerator, denominator, quotient;",
         """logic [63:0] numerator, denominator, denominator_three, quotient;
    logic [63:0] trial_remainder;
    logic [64:0] difference_one, difference_two, difference_three;"""),
        ("logic [64:0] remainder, trial_remainder, next_remainder, rounded_quotient;",
         "logic [64:0] remainder, next_remainder, doubled_remainder, rounded_quotient;"),
        ("""        trial_remainder={remainder[63:0],numerator[63]};
        next_remainder=trial_remainder;
        next_quotient={quotient[62:0],1'b0};
        if(trial_remainder>={1'b0,denominator})begin
            next_remainder=trial_remainder-{1'b0,denominator};
            next_quotient[0]=1;
        end
        rounded_quotient={1'b0,next_quotient};
        if(rounding && (next_remainder>({1'b0,denominator}-next_remainder) ||
           (next_remainder==({1'b0,denominator}-next_remainder) && next_quotient[0])))
            rounded_quotient=rounded_quotient+65'd1;""",
         """        // 0 <= remainder < denominator <= 2**62. Appending two
        // numerator bits gives a 64-bit trial smaller than four denominators.
        trial_remainder={remainder[61:0],numerator[63:62]};
        difference_one={1'b0,trial_remainder}-{1'b0,denominator};
        difference_two={1'b0,trial_remainder}-{denominator,1'b0};
        difference_three={1'b0,trial_remainder}-{1'b0,denominator_three};
        next_quotient={quotient[61:0],2'b00};
        next_remainder={1'b0,trial_remainder};
        // Bit 64 records the borrow. Select the largest digit that fits.
        if(!difference_three[64])begin
            next_remainder=difference_three;
            next_quotient[1:0]=2'd3;
        end else if(!difference_two[64])begin
            next_remainder=difference_two;
            next_quotient[1:0]=2'd2;
        end else if(!difference_one[64])begin
            next_remainder=difference_one;
            next_quotient[1:0]=2'd1;
        end
        // Round only after the final quotient and remainder are registered.
        doubled_remainder=remainder<<1;
        rounded_quotient={1'b0,quotient};
        if(rounding && (doubled_remainder>{1'b0,denominator} ||
           (doubled_remainder=={1'b0,denominator} && quotient[0])))
            rounded_quotient=rounded_quotient+65'd1;"""),
        ("denominator<=b;quotient<=0;remainder<=0;remaining<=64;",
         "denominator<=b;denominator_three<=b+(b<<1);quotient<=0;remainder<=0;remaining<=32;"),
        ("numerator<=0;denominator<=0;quotient<=0;remainder<=0;",
         "numerator<=0;denominator<=0;denominator_three<=0;quotient<=0;remainder<=0;"),
        ("""                DIV_STEP: begin
                    numerator<={numerator[62:0],1'b0};quotient<=next_quotient;remainder<=next_remainder;
                    remaining<=remaining-7'd1;
                    if(remaining==1)begin
                        if(rounded_quotient>(negative ? 65'h08000_0000_0000_0000 : {1'b0,SIGNED_MAX}))reject();
                        else begin
                            math_value<=negative ? -$signed(rounded_quotient[63:0]) : $signed(rounded_quotient[63:0]);
                            state<=return_state;
                        end
                    end
                end""",
         """                DIV_STEP: begin
                    numerator<={numerator[61:0],2'b00};quotient<=next_quotient;remainder<=next_remainder;
                    remaining<=remaining-7'd1;
                    if(remaining==1)state<=DIV_FINISH;
                end
                DIV_FINISH: begin
                    if(rounded_quotient>(negative ? 65'h08000_0000_0000_0000 : {1'b0,SIGNED_MAX}))reject();
                    else begin
                        math_value<=negative ? -$signed(rounded_quotient[63:0]) : $signed(rounded_quotient[63:0]);
                        state<=return_state;
                    end
                end"""),
    )
    for old,new in changes:
        if text.count(old)!=1:
            raise ValueError(f"Unexpected scalar-mul content: {old}")
        text=text.replace(old,new)
    return text


def materialise(kv260, output):
    baseline=kv260/"variants/scalar-mul-v1"
    original=json.loads(pin(baseline/"manifest.json",BASELINE_MANIFEST))
    script=baseline/"materialise.py"
    pin(script,BASELINE_GENERATOR)
    names=runpy.run_path(str(script))["materialise"](kv260,output)
    source=output/"fixed_scalar.sv"
    target=divider(pin(source,original["fixed_scalar"]).decode()).encode()
    original["fixed_scalar"]=sha256(target).hexdigest()
    if original!=json.loads((HERE/"manifest.json").read_bytes()):
        raise ValueError("Divider source closure differs")
    source.write_bytes(target)
    (output/"source-manifest.json").write_text(json.dumps(original,indent=2)+"\n")
    return names


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kv260",type=Path,default=HERE.parents[1])
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    materialise(a.kv260,a.output)
