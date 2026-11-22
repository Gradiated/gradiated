"""Generate the DDR4 comparison fixture from the pinned adopted circuit."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
CONTROL = "attention-exp-pair-v2"
DENSE_PORTS = """    input logic external_mode, external_valid, external_fault,
    input logic signed [15:0] external_weight,
    output logic external_request,
    output logic [9:0] external_index,
    output logic external_extra_clock, invocation_start,
"""
CORE_PORTS = """    input logic ddr_mode, ddr_valid, ddr_fault,
    input logic signed [15:0] ddr_weight,
    output logic ddr_request,
    output logic [9:0] ddr_index,
    output logic ddr_extra_clock, projection_start, projection_busy,
"""


def checked(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != expected:
        raise ValueError(f"Source pin changed: {path}")
    return data


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"Unexpected adopted source: {before}")
    return source.replace(before, after, 1)


def projection(source):
    source = replace_once(source, "module dense #(", "module dense_ddr_projection #(")
    source = replace_once(source, "    input logic clk, reset,\n", "    input logic clk, reset,\n" + DENSE_PORTS)
    source = replace_once(source, "    logic signed [15:0] operand_x, operand_w;",
        """    logic signed [15:0] operand_x, operand_w, bram_weight, ddr_operand;
    assign operand_w = external_mode ? ddr_operand : bram_weight;
    assign external_request = state == READ && external_mode && !reset;
    assign external_index = 10'(read_weight_address);
    assign external_extra_clock = external_request && !external_valid && !external_fault;
    assign invocation_start = state == IDLE && start && start_ready && !reset;
    always_ff @(posedge clk) begin
        if (state == READ && !external_mode && !reset)
            bram_weight <= weight_memory[read_weight_address];
    end""")
    source = replace_once(source, "operand_x <= 0; operand_w <= 0;", "operand_x <= 0; ddr_operand <= 0;")
    return replace_once(source, """                READ: begin
                    operand_x <= input_memory[address];
                    operand_w <= weight_memory[read_weight_address];
                    state <= MAC;
                end""",
        """                READ: begin
                    if (external_mode && external_fault) state <= IDLE;
                    else if (!external_mode || external_valid) begin
                        operand_x <= input_memory[address];
                        if (external_mode) ddr_operand <= external_weight;
                        state <= MAC;
                    end
                end""")


def transformer(source):
    source = replace_once(source, "module transformer (\n", "module transformer (\n" + CORE_PORTS)
    source = replace_once(source, "    dense #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) output_projection (",
        """    assign projection_busy = o_busy;
    dense_ddr_projection #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) output_projection (
        .external_mode(ddr_mode),.external_valid(ddr_valid),.external_fault(ddr_fault),
        .external_weight(ddr_weight),.external_request(ddr_request),.external_index(ddr_index),
        .external_extra_clock(ddr_extra_clock),.invocation_start(projection_start),""")
    return replace_once(source, "||(ff_valid && ff_error))begin",
        "||(ff_valid && ff_error)||(state==O_WAIT && ddr_mode && ddr_fault))begin")


def axi_ports():
    params = ("XIL_INTERFACENAME M_AXI, PROTOCOL AXI4, DATA_WIDTH 64, ADDR_WIDTH 49, "
              "ID_WIDTH 6, READ_WRITE_MODE READ_ONLY, NUM_READ_OUTSTANDING 1, MAX_BURST_LENGTH 1, FREQ_HZ 50000000")
    ports = []
    for name, width, direction in (
        ("ARADDR", 49, "output"), ("ARID", 6, "output"), ("ARLEN", 8, "output"),
        ("ARSIZE", 3, "output"), ("ARBURST", 2, "output"), ("ARLOCK", 1, "output"),
        ("ARCACHE", 4, "output"), ("ARPROT", 3, "output"), ("ARQOS", 4, "output"),
        ("ARVALID", 1, "output"), ("ARREADY", 1, "input"), ("RDATA", 64, "input"),
        ("RID", 6, "input"), ("RRESP", 2, "input"), ("RLAST", 1, "input"),
        ("RVALID", 1, "input"), ("RREADY", 1, "output"),
    ):
        attribute = f'X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 M_AXI {name}"'
        if name == "ARADDR":
            attribute += f',\n       X_INTERFACE_PARAMETER="{params}"'
        width_decl = f" [{width-1}:0]" if width > 1 else ""
        ports.append(f'    (* {attribute} *) {direction} logic{width_decl} m_axi_{name.lower()}')
    return ",\n".join(ports)


def adapter(source, registers):
    source = replace_once(source, "module axi_transformer (", "module axi_transformer #(parameter integer DDR_MAX_WAIT = 4096) (")
    source = replace_once(source, "ASSOCIATED_BUSIF S_AXI,", "ASSOCIATED_BUSIF S_AXI:M_AXI,")
    source = replace_once(source, "input logic s_axi_rready\n);",
        "input logic s_axi_rready,\n" + axi_ports() + "\n);")
    source = replace_once(source, "    always_comb begin\n        write_ok=0;", registers + "\n    always_comb begin\n        write_ok=0;")
    source = replace_once(source, "                8'h38:write_ok=auto_start;", """                8'h38:write_ok=auto_start;
                8'h60:write_ok=ddr_idle && !ddr_mode && write_data[2:0]==0 && write_data<=32'h7ffff800;
                8'h64:write_ok=ddr_idle && (write_data==0 || (write_data==1 && ddr_base!=0 && !ddr_fault));""")
    source = replace_once(source, "        .clk(aclk),.reset(!aresetn || soft_reset),",
        """        .clk(aclk),.reset(!aresetn || soft_reset),
        .ddr_mode(ddr_mode),.ddr_valid(ddr_valid),.ddr_fault(ddr_fault),.ddr_weight(ddr_weight),
        .ddr_request(ddr_request),.ddr_index(ddr_index),.ddr_extra_clock(ddr_extra_clock),
        .projection_start(projection_start),.projection_busy(projection_busy),""")
    return replace_once(source, "                    8'h5c:s_axi_rdata<={23'd0,skipped_positions};",
        """                    8'h5c:s_axi_rdata<={23'd0,skipped_positions};
                    8'h60:s_axi_rdata<=ddr_base;
                    8'h64:s_axi_rdata<={27'd0,counter_full,(!ddr_mode && !ddr_busy),ddr_fault,ddr_busy,ddr_mode};
                    8'h68:s_axi_rdata<=useful_bytes;
                    8'h6c:s_axi_rdata<=accepted_reads;
                    8'h70:s_axi_rdata<=accepted_beats;
                    8'h74:s_axi_rdata<=faults;
                    8'h78:s_axi_rdata<=extra_clocks;
                    8'h7c:s_axi_rdata<=ar_stalls;
                    8'h80:s_axi_rdata<=response_waits;
                    8'h84:s_axi_rdata<=projections;
                    8'h88:s_axi_rdata<=projection_clocks;
                    8'h8c:s_axi_rdata<=32'h44445231;""")


def materialise(kv260, output):
    spec = json.loads((HERE / "manifest.json").read_bytes())
    adopted = kv260 / "variants" / CONTROL
    generator = adopted / "materialise_attention_pair.py"
    checked(generator, spec["control_generator_sha256"])
    checked(adopted / "manifest.json", spec["control_manifest_sha256"])
    runpy.run_path(str(generator))["materialise"](kv260, output, True)
    ledger = output / "source-manifest.json"
    hashes = json.loads(ledger.read_bytes())
    original = {name: checked(output / f"{name}.sv", pin) for name, pin in spec["control_sources"].items()}
    registers = checked(HERE / "ddr_registers.svh", spec["ddr_registers_sha256"]).decode()
    generated = {
        "dense_ddr_projection": projection(original["dense"].decode()).encode(),
        "transformer": transformer(original["transformer"].decode()).encode(),
        "axi_transformer": adapter(original["axi_transformer"].decode(), registers).encode(),
        "projection_ddr_reader": checked(HERE / "projection_ddr_reader.sv", spec["reader_sha256"]),
    }
    for name, data in generated.items():
        pin = sha256(data).hexdigest()
        if pin != spec["fixture_sources"][name]:
            raise ValueError(f"Generated fixture source changed: {name}")
        (output / f"{name}.sv").write_bytes(data)
        hashes[name] = pin
    ledger.write_text(json.dumps(hashes, indent=2) + "\n")
    return tuple(hashes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260", type=Path, default=HERE.parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    materialise(args.kv260, args.output)
