"""Replace the pinned eight logits weight banks with one staged DDR group."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CORE = """    input logic ddr_valid, ddr_fault,
    input logic [127:0] ddr_weights,
    output logic ddr_request, ddr_operand_read, ddr_mac,
    output logic [5:0] ddr_group,
    output logic [4:0] ddr_coordinate,
    output logic ddr_extra_clock, projection_start, projection_busy,
"""
LANES = """    input logic fetch_valid, fetch_fault,
    input logic [127:0] fetched_weights,
    output logic fetch_request, operand_read, mac_active,
    output logic [5:0] fetch_group,
    output logic [4:0] fetch_coordinate,
    output logic fetch_wait, invocation_start,
"""


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin differs: {path}")
    return data


def substitute(source, *changes):
    for old, new in changes:
        if source.count(old) != 1:
            raise ValueError(f"Unexpected adopted source: {old}")
        source = source.replace(old, new)
    return source


def transformer(source):
    control, marker, logits = source.partition("// Parallel rows of the final 320-by-32 score projection.")
    if not marker:
        raise ValueError("Adopted score array missing")
    control = substitute(control,
        ("module transformer (\n", "module transformer (\n"+CORE),
        ("logic l_input_ready,l_weight_ready,l_start_ready", "logic l_input_ready,l_start_ready"),
        ("0:load_target_ready=l_weight_ready;", "0:load_target_ready=1'b1;"),
        ("    logits_parallel #(.LANES(8)) logits (", """    assign projection_busy = l_busy;
    logits_parallel_ddr #(.LANES(8)) logits (
        .fetch_valid(ddr_valid),.fetch_fault(ddr_fault),.fetched_weights(ddr_weights),
        .fetch_request(ddr_request),.fetch_group(ddr_group),.fetch_coordinate(ddr_coordinate),
        .operand_read(ddr_operand_read),.mac_active(ddr_mac),.fetch_wait(ddr_extra_clock),
        .invocation_start(projection_start),"""),
        ("        .weight_valid(weight_offer && weight_bank==0),.weight_ready(l_weight_ready),.weight_row(weight_address[13:5]),\n"
         "        .weight_address({3'd0,weight_address[4:0]}),.weight_value(weight_value[15:0]),\n",""),
        ("||(ff_valid && ff_error))begin","||(ff_valid && ff_error)||(state==LOGIT_WAIT && ddr_fault))begin"))
    logits = substitute(logits,
        ("module logits_parallel #(", "module logits_parallel_ddr #("),
        ("parameter integer LANES = 2","parameter integer LANES = 8"),
        ("    input logic clk, reset,\n", "    input logic clk, reset,\n"+LANES),
        ("""    input logic weight_valid,
    output logic weight_ready,
    input logic [8:0] weight_row,
    input logic [7:0] weight_address,
    input logic signed [15:0] weight_value,
""",""),
        ("    logic [GROUP_BITS+4:0] read_weight_address, write_weight_address;\n",""),
        ("    assign weight_ready = state == IDLE && !start && weight_row < 320 && weight_address < 32;\n",""),
        ("state == IDLE && !input_valid && !weight_valid","state == IDLE && !input_valid"),
        ("    assign read_pair = state == PRIME || advance_mac;", """    assign fetch_request = state == PRIME && !reset;
    assign fetch_group = group_index;
    assign fetch_wait = fetch_request && !fetch_valid && !fetch_fault;
    assign invocation_start = launch && !reset;
    assign mac_active = state == MAC && !reset;
    assign read_pair = (state == PRIME && fetch_valid) || advance_mac;
    assign operand_read = read_pair;
    assign fetch_coordinate = read_coordinate;"""),
        ("    assign read_weight_address = {group_index, read_coordinate};\n"
         "    assign write_weight_address = {weight_row[8:LANE_BITS], weight_address[4:0]};\n",""),
        ("    // Consecutive output rows use different banks. Each bank gets one read\n"
         "    // address and the same activation is broadcast to every lane.\n",
         "    // The DDR reader supplies one signed coefficient per lane and coordinate.\n"),
        ('        (* ram_style = "block" *) logic signed [15:0] weights [0:GROUPS*32-1];\n',''),
        ("        assign product = input_operand * weight_operand;",
         "        assign weight_operand = $signed(fetched_weights[lane*16 +: 16]);\n"
         "        assign product = input_operand * weight_operand;"),
        ("            if (!reset && weight_valid && weight_ready && weight_row[LANE_BITS-1:0] == LANE_BITS'(lane))\n"
         "                weights[write_weight_address] <= weight_value;\n\n",""),
        ("                weight_operand <= 0;\n",""),
        ("                if (read_pair)\n                    weight_operand <= weights[read_weight_address];\n",""),
        ("                PRIME: state <= MAC;",
         "                PRIME: if (fetch_fault) state <= IDLE;\n                       else if (fetch_valid) state <= MAC;"))
    return control+marker+logits


def adapter(source, regs, original_adapter):
    source = original_adapter(source, regs)
    return substitute(source,
        ("MAX_BURST_LENGTH 1,", "MAX_BURST_LENGTH 8,"),
        ("        .ddr_mode(ddr_mode),.ddr_valid(ddr_valid),.ddr_fault(ddr_fault),.ddr_weight(ddr_weight),\n"
         "        .ddr_request(ddr_request),.ddr_index(ddr_index),.ddr_extra_clock(ddr_extra_clock),",
         "        .ddr_valid(ddr_valid),.ddr_fault(ddr_fault),.ddr_weights(ddr_weights),\n"
         "        .ddr_request(ddr_request),.ddr_group(ddr_group),.ddr_coordinate(ddr_coordinate),\n"
         "        .ddr_operand_read(ddr_operand_read),.ddr_mac(ddr_mac),.ddr_extra_clock(ddr_extra_clock),"),
        ("write_data[2:0]==0 && write_data<=32'h7ffff800", "write_data[5:0]==0 && write_data<=32'h7fffb000"),
        ("32'h44445231;", "32'h44445233;"),
        ("assign auto_start=write_execute &&", "assign auto_start=ddr_mode && !ddr_fault && write_execute &&"),
        ("assign token_push=write_execute &&", "assign token_push=ddr_mode && !ddr_fault && write_execute &&"),
        ("8'h10:write_ok=write_data", "8'h10:write_ok=ddr_mode && !ddr_fault && write_data"),
        ("(core_configured && !core_busy && !core_error && core_context_count<256 && !soft_reset",
         "(ddr_mode && !ddr_fault && core_configured && !core_busy && !core_error && core_context_count<256 && !soft_reset"))


def materialise(kv260, output, candidate):
    spec = json.loads((HERE/"manifest.json").read_bytes())
    adopted = kv260/"variants/attention-exp-pair-v2"
    generator = adopted/"materialise_attention_pair.py"
    checked(generator,spec["control_generator_sha256"])
    checked(adopted/"manifest.json",spec["control_manifest_sha256"])
    runpy.run_path(str(generator))["materialise"](kv260,output,True)
    ledger = output/"source-manifest.json"
    hashes = json.loads(checked(ledger,spec["control_closure_sha256"]))
    if candidate:
        fixture = kv260/"variants/output-projection-ddr4-v1/materialise_projection_ddr.py"
        checked(fixture,spec["fixture_generator_sha256"])
        original_adapter = runpy.run_path(str(fixture))["adapter"]
        regs = checked(HERE/"ddr_registers.svh",spec["registers_sha256"]).decode()
        rtl = {
            "axi_transformer":adapter(checked(output/"axi_transformer.sv",hashes["axi_transformer"]).decode(), regs, original_adapter).encode(),
            "transformer":transformer(checked(output/"transformer.sv",hashes["transformer"]).decode()).encode(),
            "logits_group_reader":checked(HERE/"logits_group_reader.sv",spec["reader_sha256"]),
        }
        for name,data in rtl.items():
            pin = sha256(data).hexdigest()
            if pin != spec["candidate_sources"][name]:
                raise ValueError(f"Generated source changed: {name}")
            (output/f"{name}.sv").write_bytes(data)
            hashes[name] = pin
        ledger.write_text(json.dumps(hashes,indent=2)+"\n")
    return tuple(hashes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=("control","candidate"),required=True)
    args = parser.parse_args()
    materialise(args.kv260,args.output,args.arm=="candidate")
