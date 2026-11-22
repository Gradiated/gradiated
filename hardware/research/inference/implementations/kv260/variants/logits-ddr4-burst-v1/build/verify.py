"""Verify Exp16 firmware and the two exact routed resource hierarchies."""

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys
import tarfile

from prepare import FIRMWARE, PROGRAM, DMA

CONTROL_DCP = "edd6815b335a5aed10e1e1e30847351655754ac56798440cb15218df169d3b6f"
CONTROL_ARCHIVE = "7ed800eb74f957dff3647f679a48dadbe70921d176c6887a1bbf4f639c714362"
CONTROL_RUN = "61c505f49c81a1f3f351861e3e688a8111943f667251222ea92432365dfaf5de"
SHELL_ARCHIVE = "4f2e6168fd7f59997062894fef05616a8dc3028df09c59766902c591a8914956"
SHELL_AUDIT = "88f84f11a0ffff7d0315b3127a02ed9a2ee4c12902ea475c3b26f298fc23f74c"
PSU_INIT = ("build/generate/project/tiny_ps_axi_build.gen/sources_1/bd/tiny_ps_axi/ip/"
            "tiny_ps_axi_ps_0/psu_init.tcl")
RESOURCE_COLUMNS = ("lut","logic_lut","lutram","srl","register","ramb36","ramb18","uram","dsp")

def load_module(path, name):
    saved = sys.modules.get("prepare")
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(path.parent))
    sys.modules.pop("prepare",None)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
        if saved:
            sys.modules["prepare"]=saved
    return module

def load(path):
    return json.loads(path.read_text())

def row(report, name):
    hits = [line.split("|")[1:-1] for line in report.splitlines() if line.startswith("|")]
    hits = [parts for parts in hits if parts and parts[0].strip()==name]
    if len(hits)!=1 or len(hits[0])!=len(RESOURCE_COLUMNS)+2:
        raise ValueError(f"Expected one utilization row {name}")
    return {key:int(value.strip()) for key,value in zip(RESOURCE_COLUMNS,hits[0][2:])}

def primitive_counts(path):
    rows = [line.split("\t") for line in path.read_text().splitlines()]
    return {
        "logits":dict(Counter(kind for name,kind in rows if "/core/logits/" in name)),
        "embedding":dict(Counter(kind for name,kind in rows if "/core/embedding_memory" in name)),
        "reader":dict(Counter(kind for name,kind in rows if "/projection_reader/" in name)),
    }

def account(v, control_census, candidate):
    control_report = (control_census/"utilization-hierarchical.rpt").read_text()
    cand_report = (candidate/"utilization-hierarchical.rpt").read_text()
    sections = {name:{
        "control": row(control_report,instance),"candidate":row(cand_report,instance),
    } for name,instance in (("fpga","tiny_ps_axi_wrapper"),("accelerator","actual"),("logits","logits"))}
    sections["reader"] = {"candidate":row(cand_report,"projection_reader")}
    control = primitive_counts(control_census/"primitive-census.tsv")
    changed = primitive_counts(candidate/"ddr-primitives.tsv")
    v.check(control["logits"].get("RAMB36E2")==8 and sections["logits"]["control"]["ramb36"]==8,
            "Control does not show eight score matrix banks")
    v.check(not any(key.startswith(("RAMB","URAM")) for key in changed["logits"]),
            "Candidate still has logits BRAM or URAM")
    v.check(all(sections["logits"]["candidate"][key]==0 for key in ("ramb36","ramb18","uram")),
            "Block storage still exists in the logits hierarchy")
    v.check(control["embedding"]==changed["embedding"]=={"RAMB36E2":6,"RAMB18E2":1},
            "Original embedding BRAM inventory changed")
    return {"hierarchy":sections,"primitive_counts":{"control":control,"candidate":changed}}

def verify_pins(v, path):
    rows = {line.split("\t")[0].rsplit("/",1)[-1]:line.split("\t")[1:]
            for line in path.read_text().splitlines()}
    def constant(name,value):
        net, _, refs, _ = rows[name]
        v.check(net.rsplit("/",1)[-1]==f"<const{value}>" and
                set(refs.split())=={"VCC" if value else "GND"}, f"Unexpected AXI constant at {name}")
    for name,bits in (("ARID",(0,)*6),("ARLEN",(1,1,1,0,0,0,0,0)),("ARPROT",(0,1,0)),
                      ("ARSIZE",(1,1,0)),("ARBURST",(1,0)),("ARCACHE",(1,1,0,0))):
        for bit,value in enumerate(bits):
            constant(f"SAXIGP2{name}[{bit}]",value)
    for name in ("AWVALID","WVALID","ARUSER"):
        constant("SAXIGP2"+name,0)
    address_pins = {key for key in rows if re.fullmatch(r"SAXIGP2ARADDR\[\d+\]",key)}
    v.check(address_pins=={f"SAXIGP2ARADDR[{bit}]" for bit in range(49)},
            "Unexpected physical address width")
    for name in ("ARVALID","ARREADY","RREADY","RVALID","RLAST"):
        net,driver,_,_ = rows["SAXIGP2"+name]
        v.check(net and driver,f"Missing routed read channel signal {name}")
    data = {key for key in rows if re.fullmatch(r"SAXIGP2RDATA\[\d+\]",key)}
    v.check(data=={f"SAXIGP2RDATA[{bit}]" for bit in range(64)},"Expected 64 native data pins")
    _,_,refs,clocks=rows["SAXIGP2RCLK"]
    v.check(set(refs.split())=={"BUFG_PS"} and clocks=="clk_pl_0","Expected 50 MHz HP0 clock")
    return dict(arlen=7, arid=0, arsize=3, arprot=2, arburst=1, clock=clocks, read_data_width=64)

def verify_package(v, root, shell, compatible):
    expected=load(shell/"offline-acceptance.json")["firmware_assets"]
    name=FIRMWARE+".bit.bin"
    firmware=root/"offline-package"/name
    bit = firmware.with_suffix("").read_bytes()
    raw = firmware.read_bytes()
    offset=len(bit)-len(raw)
    v.check(len(raw)==7797692 and offset>4 and
            int.from_bytes(bit[offset-4:offset],"big")==len(raw) and
            raw==b"".join(bit[i:i+4][::-1] for i in range(offset,len(bit),4)), "Bootgen conversion differs")
    prog=v.read_overlay(root/PROGRAM)
    node="/fragment@0/__overlay__"
    v.require_props(prog[node],{"firmware-name":name.encode()+b"\0","resets":v.cells(0xFFFFFFFF,119)})
    v.require_props(prog["/__fixups__"],{"fpga_full":b"/fragment@0:target:0\0",
                                      "zynqmp_reset":b"/fragment@0/__overlay__:resets:0\0"})
    fixed=("kv260-ddr4-interface.dtbo","kv260-ddr4-afi-restore.dtbo")
    for filename in fixed:
        v.check(v.sha(root/filename)==expected[filename], f"Expected byte-identical {filename}")
    dma=v.read_overlay(root/(DMA+".dtbo"))
    v.check(dma[node+"/ddr4-weights@a0000060"]=={
        "compatible":compatible.encode()+b"\0","reg":v.cells(0,0xa0000060,0,0x30),
        "gradiated,verified-direct-dma":b"",
    },"Unexpected platform DMA resource or addressing attributes")
    v.require_props(dma["/__fixups__"],{"amba":b"/fragment@0:target:0\0"})
    return {p.name:v.sha(p) for p in (firmware,root/PROGRAM,root/(DMA+".dtbo"),*(root/f for f in fixed))}

def validate(v, burst, root, receipt, shell, control, control_evidence, control_record,
             candidate_rtl, control_rtl, tested_rtl, frozen_protocol, compatible):
    v.check(v.sha(shell/"offline-acceptance.json")==SHELL_AUDIT and
            v.sha(shell/"server.tar.gz")==SHELL_ARCHIVE, "Exp15 shell pins differ")
    v.check(v.sha(control/"server.tar.gz")==CONTROL_ARCHIVE and v.sha(control_record)==CONTROL_RUN,
            "Exp13 control archive or record differs")
    prior = load(control_record)
    v.check(prior["status"]=="passed" and prior["device"]["configuration"]["clock_hz"]==50000000
            and prior["device"]["configuration"]["threads"]==2, "Control configuration differs")
    checkpoint=dict(line.split(maxsplit=1) for line in (control_evidence/"checkpoint.txt").read_text().splitlines())
    v.check(checkpoint["checkpoint_sha256"]==CONTROL_DCP and checkpoint["tool"]=="2025.2" and
            checkpoint["part"]=="xck26-sfvc784-2LV-c" and float(checkpoint["clock_period_ns"])==20.0 and
            checkpoint["route_complete"]=="1", "Control checkpoint admission failed")
    v.check(receipt["passed"] and load(root/"build-outcome.json")["passed"], "Build did not complete")
    for phase in v.PHASES:
        info=load(root/f"build/{phase}/phase.json")
        v.check(info["phase"]==phase and not info["timed_out"] and info["returncode"]==0 and
                info["expected_output_exists"], f"Incomplete implementation phase {phase}")
    reports=root/"build/reports"
    timing=dict(line.split(maxsplit=1) for line in (reports/"metrics.txt").read_text().splitlines())
    v.check(timing["clock"]=="clk_pl_0 period_ns 20.000" and
            all(timing[k]=="1" for k in ("fully_placed","fully_routed")) and
            all(timing[k]=="0" for k in v.ZERO_METRICS) and
            all(float(timing[k])>=0 for k in ("setup_slack_ns","hold_slack_ns")), "Candidate route failed")
    with tarfile.open(shell/"server.tar.gz") as archive:
        prior_ps=archive.extractfile(PSU_INIT).read().decode()
    v.check(v.ps_writes((root/PSU_INIT).read_text())==v.ps_writes(prior_ps), "Generated PS writes differ")
    burst.verify_bd(v,root)
    pins=verify_pins(v,reports/"ddr-routed-hp0.tsv")
    accounting=account(v,control_evidence,reports)
    item=accounting["hierarchy"]["fpga"]["control"]
    measured=prior["conditions"]["resources"]
    v.check(item["lut"]==measured["lut"] and item["register"]==measured["register"] and
            item["dsp"]==measured["dsp"] and item["ramb36"]+item["ramb18"]/2==measured["bram_tile"],
            "Fresh control census differs from adopted run")
    original_pins={
        Path(name).stem:pin for name,pin in load(control/"server/source-manifest.json")["files"].items()
        if name.startswith("implementation/rtl/") and name.endswith(".sv")
    }
    manifest=load(root/"source-manifest.json")
    v.check(manifest["reused_control_modules"]==original_pins==load(control_rtl) and
            load(tested_rtl)["conditions"]["control_source_manifest_sha256"]==v.sha(control_rtl),
            "Routed control sources differ from the exact paired replay")
    v.check(manifest["protocol_sha256"]==v.sha(frozen_protocol),"Admitted protocol differs")
    firmware_name="gradiated-tiny-attention-exp-pair-v2-50mhz.bit.bin"
    firmware_path=control/"server/offline-package"/firmware_name
    program_path=control/"server/kv260-attention-exp-pair-v2-program.dtbo"
    control_package={p.name:v.sha(p) for p in (firmware_path,program_path)}
    archived={Path(item["path"]).name:item["sha256"] for item in prior["artifacts"]}
    v.check(all(archived[name]==digest for name,digest in control_package.items()),
            "Control firmware or programming overlay differs")
    replay=burst.verify_rtl(v,root,candidate_rtl,tested_rtl)
    firmware=verify_package(v,root,shell,compatible)
    def device_resources(arm):
        cells = accounting["hierarchy"]["fpga"][arm]
        return dict(lut=cells["lut"], register=cells["register"], dsp=cells["dsp"],
                    bram_tile=cells["ramb36"]+cells["ramb18"]/2)
    return dict(passed=True, board_programmed=False, control_checkpoint_sha256=CONTROL_DCP,
                resources=device_resources("candidate"), control_resources=device_resources("control"),
                timing=timing,routed_hp0=pins,resource_accounting=accounting,
                generated_psu_matches_exp15=True, rtl_replay=replay, firmware_assets=firmware,
                control_firmware_assets=control_package)

if __name__=="__main__":
    args=argparse.ArgumentParser(description=__doc__)
    for key in ("archive","receipt","destination","shell","control","control_evidence",
                "control_record","candidate_rtl","control_rtl","tested_rtl","frozen_protocol","result"):
        args.add_argument(key,type=Path)
    args.add_argument("--manifest-pin",required=True)
    args.add_argument("--compatible",default="gradiated,kv260-ddr4-logits-v1")
    build=Path(__file__).resolve().parents[2]
    args.add_argument("--exp14-verifier",type=Path,default=build/"output-projection-ddr4-v1"/"build"/"verify.py")
    args.add_argument("--exp15-verifier",type=Path,default=build/"output-projection-ddr4-burst-v1"/"build"/"verify.py")
    o=args.parse_args()
    common=load_module(o.exp14_verifier,"exp14_release")
    burst=load_module(o.exp15_verifier,"exp15_release")
    receipt=common.recover(o.archive,o.receipt,o.destination,o.manifest_pin)
    record=validate(common,burst,o.destination,receipt,o.shell,o.control,o.control_evidence,
                    o.control_record,o.candidate_rtl,o.control_rtl,o.tested_rtl,o.frozen_protocol,o.compatible)
    with o.result.open("x") as stream:
        json.dump(record,stream,indent=2,sort_keys=True)
        stream.write("\n")
