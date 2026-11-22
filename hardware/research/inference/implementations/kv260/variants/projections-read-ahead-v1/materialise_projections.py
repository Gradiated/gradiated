"""Select scoped within-row read-ahead for on-chip input and weight pairs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import runpy
import tempfile

HERE=Path(__file__).resolve().parent
SHARED="variants/norm-mul-shared-v1"
DEDICATED="variants/norm-mul-dsp-v1"
PIPELINE="variants/logits-pipeline-v1/materialise.py"
ARMS={
    "control":(),
    "qkv-read-ahead-v1":("qkv",),
    "attention-output-read-ahead-v1":("output",),
    "ff-gate-up-read-ahead-v1":("gate_up",),
    "projections-read-ahead-v1":("qkv","output","gate_up"),
    "qkv-attention-output-read-ahead-v1":("qkv","output"),
}
SOURCES={"qkv":"frontend","output":"transformer","gate_up":"feedforward"}


def digest(data):
    return sha256(data).hexdigest()


def checked(path,expected):
    data=path.read_bytes()
    if path.is_symlink() or digest(data)!=expected:
        raise ValueError(f"Source pin differs: {path}")
    return data


def replace(text,target,replacement):
    if text.count(target)!=1:
        raise ValueError(f"Expected one pinned RTL match: {target}")
    return text.replace(target,replacement,1)


def mac_pipeline(mac):
    text=mac[mac.index("module mac32 #("):]
    for target,replacement in (
        ("module mac32 #(","module mac32_read_ahead #("),
        ("    logic [4:0] address;",
         "    logic [4:0] address, read_address;\n    logic advance_mac;"),
        ("    assign result_row = row;",
         "    assign result_row = row;\n"
         "    assign advance_mac = state == MAC && address != 5'd31;\n"
         "    assign read_address = address + {4'd0,advance_mac};"),
        ("            step_valid <= 1'b0;\n            case (state)",
         """            step_valid <= 1'b0;
            // Prime the row, then register only its next unconsumed pair.
            if (state == READ || advance_mac) begin
                operand_x <= input_memory[read_address];
                operand_w <= weight_memory[WEIGHT_BITS'({row,read_address})];
            end
            case (state)"""),
        ("""                READ: begin
                    // Synchronous reads: consume these registers next cycle.
                    operand_x <= input_memory[address];
                    operand_w <= weight_memory[WEIGHT_BITS'({row,address})];
                    state <= MAC;
                end""",
         "                READ: state <= MAC;"),
        ("""                    else begin
                        address <= address + 5'd1;
                        state <= READ;
                    end""","                    else address <= read_address;"),
    ):
        text=replace(text,target,replacement)
    return text


def specialise(data,scope,pipeline):
    if scope=="qkv":
        module=data["frontend"].decode()
        module=replace(module,"    mac32 #(.ROWS(96)) projection (",
                       "    mac32_read_ahead #(.ROWS(96)) projection (")
        return (module+"\n"+mac_pipeline(data["mac32"].decode())).encode()
    dense=pipeline(data["dense"].decode())
    if scope=="output":
        name="dense_attention_output_read_ahead"
        module=data["transformer"].decode()
        target="    dense #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) output_projection ("
        module=replace(module,target,target.replace("dense #",name+" #"))
    else:
        name="dense_ff_gate_up_read_ahead"
        module=data["feedforward"].decode()
        for shift,instance in ((16,"gate_dense"),(15,"up_dense")):
            target=f"    dense #(.INPUTS(32),.OUTPUTS(128),.SHIFT({shift}),.RESULT_BITS(16)) {instance} ("
            module=replace(module,target,target.replace("dense #",name+" #"))
    clone=replace(dense,"module logits_dense #(",f"module {name} #(")
    return (module+"\n"+clone).encode()


def materialise(kv260,output,arm):
    spec=json.loads((HERE/"manifest.json").read_bytes())
    providers=spec["provider_sha256"]
    for path,stamp in providers.items():
        checked(kv260/path,stamp)
    dedicated=runpy.run_path(str(kv260/DEDICATED/"materialise_norm_multiply.py"))["materialise"]
    shared=runpy.run_path(str(kv260/SHARED/"materialise_shared_norm_multiply.py"))["materialise"]
    with tempfile.TemporaryDirectory(prefix="projections-baseline-") as tmp:
        parked=Path(tmp)/"dedicated"
        dedicated(kv260,parked,True)
        names=shared(kv260,parked,output,True)
    ledger=output/"source-manifest.json"
    hashes=json.loads(checked(ledger,spec["control_rtl_manifest_sha256"]))
    data={name:checked(output/(name+".sv"),stamp) for name,stamp in hashes.items()}
    pipeline=runpy.run_path(str(kv260/PIPELINE))["pipeline"]
    for scope in ARMS[arm]:
        module=SOURCES[scope]
        result=specialise(data,scope,pipeline)
        stamp=digest(result)
        if stamp!=spec["scope_rtl_sha256"][scope]:
            raise ValueError(f"Generated source differs for {scope}: {stamp}")
        (output/(module+".sv")).write_bytes(result)
        hashes[module]=stamp
    artifact=(json.dumps(hashes,indent=2)+"\n").encode()
    if digest(artifact)!=spec["arm_rtl_manifest_sha256"][arm]:
        raise ValueError(f"Generated RTL manifest differs for {arm}")
    ledger.write_bytes(artifact)
    return names


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kv260",type=Path,default=HERE.parents[1])
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--arm",choices=ARMS,required=True)
    args=parser.parse_args()
    materialise(args.kv260,args.output,args.arm)
