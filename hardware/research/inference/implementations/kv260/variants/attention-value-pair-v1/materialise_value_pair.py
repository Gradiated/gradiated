"""Generate the paired attention value-sum and parity-banked cache variant."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE=Path(__file__).resolve().parent
CONTROL="variants/projections-read-ahead-v1"


def digest(data):
    return sha256(data).hexdigest()


def checked(path,expected):
    data=path.read_bytes()
    if path.is_symlink() or digest(data)!=expected:
        raise ValueError(f"Source pin differs: {path}")
    return data


def replace(text,before,after):
    if text.count(before)!=1:
        raise ValueError(f"Expected one adopted RTL match: {before}")
    return text.replace(before,after,1)


def ports(text,cache=False):
    """Add the internal pair request and response fields to a scoped clone."""
    if cache:
        fields=(
            ("    input logic [5:0] read_coordinate,","    input logic [5:0] read_coordinate,\n    input logic read_pair,"),
            ("    output logic signed [15:0] output_k, output_v,",
             "    output logic signed [15:0] output_k, output_v, output_v_second,\n    output logic output_pair,"),
        )
    else:
        fields=(
            ("    output logic [5:0] cache_read_coordinate,",
             "    output logic [5:0] cache_read_coordinate,\n    output logic cache_read_pair,"),
            ("    input logic signed [15:0] cache_output_k, cache_output_v,",
             "    input logic signed [15:0] cache_output_k, cache_output_v, cache_output_v_second,\n"
             "    input logic cache_output_pair,"),
        )
    for before,after in fields:
        text=replace(text,before,after)
    return text


def cache_variant(original):
    text=ports(original,cache=True)
    for before,after in (
        ("module kv_cache (","module kv_cache_value_pair ("),
        ("    logic signed [15:0] k_memory [0:8191], v_memory [0:8191];",
         """    logic signed [15:0] k_memory [0:8191];
    logic signed [15:0] v_even [0:4095], v_odd [0:4095];
    logic signed [15:0] value_even, value_odd;
    logic [11:0] value_write_address, value_read_address;
    logic key_read_enable, even_read_enable, odd_read_enable;

    assign value_write_address={write_position[7:0],write_coordinate[4:1]};
    assign value_read_address={read_position[7:0],read_coordinate[4:1]};
    assign output_v=output_coordinate[0] ? value_odd : value_even;
    assign output_v_second=output_pair ? value_odd : 16'sd0;
    assign key_read_enable=read_valid && read_ready;
    assign even_read_enable=key_read_enable && (read_pair || !read_coordinate[0]);
    assign odd_read_enable=key_read_enable && (read_pair || read_coordinate[0]);"""),
        ("read_position < token_count && read_coordinate < 6'd32;",
         "read_position < token_count &&\n                        read_coordinate < 6'd32 && (!read_pair || !read_coordinate[0]);"),
        ("            v_memory[{write_position[7:0],write_coordinate[4:0]}] <= write_v;",
         "            if (write_coordinate[0]) v_odd[value_write_address] <= write_v;\n"
         "            else v_even[value_write_address] <= write_v;"),
        ("            output_position <= 0; output_coordinate <= 0; output_k <= 0; output_v <= 0;",
         "            output_position <= 0; output_coordinate <= 0; output_k <= 0;\n"
         "            output_pair <= 0; value_even <= 0; value_odd <= 0;"),
        ("            if (read_valid && read_ready) begin",
         "            if (key_read_enable) begin"),
        ("                output_v <= v_memory[{read_position[7:0],read_coordinate[4:0]}];",
         """                if (even_read_enable) value_even <= v_even[value_read_address];
                if (odd_read_enable) value_odd <= v_odd[value_read_address];
                output_pair <= read_pair;"""),
    ):
        text=replace(text,before,after)
    return original+"\n"+text


def frontend_variant(original):
    controller,rest=original.split("endmodule",1)
    text=ports(controller,cache=True)
    for before,after in (
        ("module frontend (","module frontend_value_pair ("),
        ("    kv_cache cache (","    kv_cache_value_pair cache ("),
        (".read_coordinate(read_coordinate),",
         ".read_coordinate(read_coordinate),.read_pair(read_pair),"),
        (".output_v(output_v),.token_count(token_count)",
         ".output_v(output_v),.output_v_second(output_v_second),.output_pair(output_pair),.token_count(token_count)"),
    ):
        text=replace(text,before,after)
    assert "module mac32_read_ahead #(" in rest
    return original+"\n"+text+"endmodule\n"


def attention_variant(original):
    controller,helpers=original.split("endmodule",1)
    text=ports(controller)
    for before,after in (
        ("module attention (","module attention_value_pair ("),
        ("    output logic signed [47:0] step_sum\n);",
         """    output logic signed [47:0] step_sum,
    output logic step_pair_valid,
    output logic signed [15:0] step_pair_weight,
    output logic signed [32:0] step_pair_product,
    output logic signed [47:0] step_pair_sum
);"""),
        ("    logic signed [15:0] weight;",
         """    logic signed [15:0] weight, second_weight;
    (* keep = "true", use_dsp = "yes" *) logic signed [32:0] second_product;
    logic signed [47:0] second_accumulator;
    (* use_dsp = "no" *) logic signed [47:0] second_next_sum;"""),
        ("    assign cache_read_position={1'b0,position}+{8'd0,next_value_position};",
         """    assign cache_read_position={1'b0,position}+{8'd0,next_value_position};
    assign cache_read_pair=state==CONTEXT_REQ || next_value_position;"""),
        ("    assign next_sum=accumulator+{{15{product[32]}},product};",
         """    assign next_sum=accumulator+{{15{product[32]}},product};
    assign second_product=operand*second_weight;
    assign second_next_sum=second_accumulator+{{15{second_product[32]}},second_product};"""),
        ("            maximum<=32'sh8000_0000;exp_sum<=0;operand<=0;weight<=0;accumulator<=0;",
         "            maximum<=32'sh8000_0000;exp_sum<=0;operand<=0;weight<=0;accumulator<=0;\n"
         "            second_weight<=0;second_accumulator<=0;"),
        ("            step_input<=0;step_weight<=0;step_product<=0;step_sum<=0;",
         """            step_input<=0;step_weight<=0;step_product<=0;step_sum<=0;
            step_pair_valid<=0;step_pair_weight<=0;step_pair_product<=0;step_pair_sum<=0;"""),
        ("            score_valid<=0;exp_valid<=0;probability_valid<=0;step_valid<=0;",
         "            score_valid<=0;exp_valid<=0;probability_valid<=0;step_valid<=0;step_pair_valid<=0;"),
        ("if(cache_output_position!=position || cache_output_coordinate!={head,coordinate})fail();\n"
         "                    else begin\n"
         "                        operand<={query_memory",
         "if(cache_output_position!=position || cache_output_coordinate!={head,coordinate} || cache_output_pair)fail();\n"
         "                    else begin\n"
         "                        operand<={query_memory"),
        ("                            position<=0;coordinate<=0;accumulator<=0;state<=CONTEXT_REQ;",
         "                            position<=0;coordinate<=0;accumulator<=0;second_accumulator<=0;state<=CONTEXT_REQ;"),
        ("""                    if(cache_output_position!=position || cache_output_coordinate!={head,coordinate})fail();
                    else begin
                        operand<=$signed({1'b0,probabilities[position]});weight<=cache_output_v;state<=CONTEXT_MAC;
                    end""",
         """                    if(cache_output_position!=position || cache_output_coordinate!={head,coordinate} || !cache_output_pair)fail();
                    else begin
                        operand<=$signed({1'b0,probabilities[position]});
                        weight<=cache_output_v;second_weight<=cache_output_v_second;state<=CONTEXT_MAC;
                    end"""),
        ("""                CONTEXT_MAC: begin
                    accumulator<=next_sum;step_valid<=1;step_mode<=1;step_head<=head;""",
         """                CONTEXT_MAC: begin
                    accumulator<=next_sum;step_valid<=1;step_mode<=1;step_head<=head;
                    second_accumulator<=second_next_sum;
                    step_pair_valid<=1;step_pair_weight<=second_weight;
                    step_pair_product<=second_product;step_pair_sum<=second_next_sum;"""),
        ("""                    if(error)state<=IDLE;
                    else if(coordinate==15)begin""",
         """                    if(error)state<=IDLE;
                    // Keep serial rounding and ordered output retirement for both coordinates.
                    else if(!coordinate[0])begin
                        coordinate<=coordinate+1'b1;
                        scalar_shift_start(second_accumulator,-8'sd15,CONTEXT_SEND);
                    end else if(coordinate==15)begin"""),
        ("                    end else begin position<=0;coordinate<=coordinate+1'b1;accumulator<=0;state<=CONTEXT_REQ;end",
         """                    end else begin
                        position<=0;coordinate<=coordinate+1'b1;
                        accumulator<=0;second_accumulator<=0;state<=CONTEXT_REQ;
                    end"""),
    ):
        text=replace(text,before,after)
    assert "module fixed_scalar_attention_exp" in helpers
    return original+"\n"+text+"endmodule\n"


def transformer_variant(text):
    for before,after in (
        ("    logic [5:0] cache_read_coordinate;",
         "    logic [5:0] cache_read_coordinate;\n    logic cache_read_pair, cache_output_pair;"),
        ("    logic signed [15:0] cache_k,cache_v;",
         "    logic signed [15:0] cache_k,cache_v,cache_v_second;"),
        ("    frontend front (","    frontend_value_pair front ("),
        (".read_valid(cache_read_valid),.read_ready(cache_read_ready),.read_position(cache_read_position),.read_coordinate(cache_read_coordinate),",
         ".read_valid(cache_read_valid),.read_ready(cache_read_ready),.read_position(cache_read_position),.read_coordinate(cache_read_coordinate),\n"
         "        .read_pair(cache_read_pair),"),
        (".output_k(cache_k),.output_v(cache_v),.token_count(context_count)",
         ".output_k(cache_k),.output_v(cache_v),.output_v_second(cache_v_second),.output_pair(cache_output_pair),.token_count(context_count)"),
        ("    attention att (","    attention_value_pair att ("),
        (".cache_read_valid(cache_read_valid),.cache_read_ready(cache_read_ready),",
         ".cache_read_valid(cache_read_valid),.cache_read_ready(cache_read_ready),.cache_read_pair(cache_read_pair),"),
        (".cache_output_k(cache_k),.cache_output_v(cache_v),",
         ".cache_output_k(cache_k),.cache_output_v(cache_v),.cache_output_v_second(cache_v_second),.cache_output_pair(cache_output_pair),"),
        (".step_input(),.step_weight(),.step_product(),.step_sum());\n    dense_attention_output_read_ahead",
         ".step_input(),.step_weight(),.step_product(),.step_sum(),\n"
         "        .step_pair_valid(),.step_pair_weight(),.step_pair_product(),.step_pair_sum());\n"
         "    dense_attention_output_read_ahead"),
    ):
        text=replace(text,before,after)
    return text


CHANGED={"kv_cache":cache_variant,"frontend":frontend_variant,"attention":attention_variant,"transformer":transformer_variant}


def materialise(kv260,output,arm):
    spec=json.loads((HERE/"manifest.json").read_bytes())
    control=kv260/CONTROL
    maker=control/"materialise_projections.py"
    checked(maker,spec["control_generator_sha256"])
    checked(control/"manifest.json",spec["control_variant_sha256"])
    names=runpy.run_path(str(maker))["materialise"](kv260,output,"projections-read-ahead-v1")
    ledger=output/"source-manifest.json"
    pins=json.loads(checked(ledger,spec["control_rtl_manifest_sha256"]))
    for name,stamp in pins.items():
        checked(output/(name+".sv"),stamp)
    if arm=="candidate":
        for name,change in CHANGED.items():
            path=output/(name+".sv")
            value=change(path.read_text()).encode()
            stamp=digest(value)
            if stamp!=spec["candidate_sources"][name]:
                raise ValueError(f"Generated {name} source differs: {stamp}")
            path.write_bytes(value)
            pins[name]=stamp
        data=(json.dumps(pins,indent=2)+"\n").encode()
        if digest(data)!=spec["candidate_rtl_manifest_sha256"]:
            raise ValueError("Generated candidate RTL manifest differs")
        ledger.write_bytes(data)
    return names


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm)
