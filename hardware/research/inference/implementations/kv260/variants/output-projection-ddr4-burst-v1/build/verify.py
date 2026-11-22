"""Verify the burst fixture's archive, routed native HP0 and firmware package."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import tarfile

from prepare import FIRMWARE, PROGRAM

CONTROL_ARCHIVE = "2ea0ace6ad9f05f4f093d6764305e85c32a0d1a7d424739bf37b787e413fc5c6"
CONTROL_AUDIT = "1a679030f7b28fe6cf47b3da0f8be33d7cf713f698f8585195b3d83f0fbdd887"
CONTROL_PSU = (
    "build/generate/project/tiny_ps_axi_build.gen/sources_1/bd/tiny_ps_axi/ip/"
    "tiny_ps_axi_ps_0/psu_init.tcl"
)

def common_tools(path):
    spec = importlib.util.spec_from_file_location("exp14_build_verify", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def verify_bd(v, root):
    report = (root / "build/generate/ddr-interfaces.txt").read_text()
    hp, master = report.split("INTERFACE ")[1:]
    for side in (hp, master):
        for key, val in (
            ("ADDR_WIDTH", "49"), ("ID_WIDTH", "6"), ("DATA_WIDTH", "64"),
            ("CLK_DOMAIN", "tiny_ps_axi_ps_0_pl_clk0"), ("FREQ_HZ", "49999500"),
            ("PROTOCOL", "AXI4"), ("MAX_BURST_LENGTH", "8"),
        ):
            v.check(re.search(rf"(?m)^CONFIG\.{key} +\S+ +\S+ +{val}$", side),
                    f"Unexpected interface value: {key}={val}")
        v.check("\nNET /neural_M_AXI\n" in side, "Expected direct HP0 connection")
    v.check("READ_ONLY" in master and master.count("\nADDRESS ") == 1 and
            "SEG_ps_HP0_DDR_LOW" in master, "Expected exclusively the low DDR address segment")
    for key, val in (("OFFSET", 0), ("RANGE", 0x80000000), ("REMAPPED", 0)):
        match = re.search(rf"(?m)^{key} +\S+ +\S+ +(\S+)$", master)
        v.check(match and int(match[1], 0) == val, f"Unexpected DDR {key}")

def verify_routed(v, report):
    rows = {}
    for line in report.read_text().splitlines():
        pin, net, driver, refs, clocks = line.split("\t")
        name = pin.rsplit("/", 1)[-1]
        v.check(name not in rows, f"Duplicate pin {name}")
        rows[name] = (net, driver, refs, clocks)
    def constant(key, value):
        net, _, refs, _ = rows[key]
        v.check(net.rsplit("/", 1)[-1] == f"<const{value}>" and
                set(refs.split()) == {"VCC" if value else "GND"}, f"Unexpected constant {key}")
    for key, values in (("ARID", (0,)*6), ("ARSIZE", (1,1,0)), ("ARPROT", (0,1,0)),
                        ("ARBURST", (1,0))):
        for bit, value in enumerate(values):
            constant(f"SAXIGP2{key}[{bit}]", value)
    for bit in range(3, 8):
        constant(f"SAXIGP2ARLEN[{bit}]", 0)
    for bit in range(32, 49):
        constant(f"SAXIGP2ARADDR[{bit}]", 0)
    for key in ("AWVALID", "ARUSER", "WVALID"):
        constant(f"SAXIGP2{key}", 0)
    length_nets = [rows[f"SAXIGP2ARLEN[{bit}]"][:3] for bit in range(3)]
    for net, driver, refs in length_nets:
        v.check(net and driver and refs and not {"GND", "VCC"}.intersection(refs.split()),
                "Low ARLEN bits must use a placed logic source")
    # Vivado may preserve separate net segments at native encodings. The actual
    # primitive driver must be identical so the field can encode only 0 or 7.
    v.check(len({tuple(sorted(driver.split())) for _,driver,_ in length_nets}) == 1,
            "Low ARLEN bits do not share the routed selector")
    for signal in ("ARVALID","ARREADY","RREADY","RVALID","RLAST"):
        net, driver, _, _ = rows[f"SAXIGP2{signal}"]
        v.check(net and driver, f"Missing native signal {signal}")
    data = [name for name in rows if re.fullmatch(r"SAXIGP2RDATA\[\d+\]", name)]
    v.check(set(data) == {f"SAXIGP2RDATA[{bit}]" for bit in range(64)},
            "Routed read data pins differ from 64 native lanes")
    _, _, refs, clocks = rows["SAXIGP2RCLK"]
    v.check(set(refs.split()) == {"BUFG_PS"} and clocks == "clk_pl_0",
            "HP0 read clock does not use native 50 MHz PL0")
    return dict(arlen_values=[0,7], arlen_driver=length_nets[0][1], read_data_width=64,
                arid=0, arprot=2, arburst=1, arsize=3, awvalid=0, wvalid=0, clock=clocks)

def verify_overlays(v, root, control):
    fw = FIRMWARE+".bit.bin"
    program = v.read_overlay(root/PROGRAM)
    base = "/fragment@0/__overlay__"
    v.require_props(program[base], {"firmware-name":fw.encode()+b"\0",
                                    "resets":v.cells(0xFFFFFFFF,119)})
    v.require_props(program["/__fixups__"], {"fpga_full":b"/fragment@0:target:0\0",
                                             "zynqmp_reset":b"/fragment@0/__overlay__:resets:0\0"})
    fixed = ("kv260-ddr4-interface.dtbo","kv260-ddr4-afi-restore.dtbo")
    for filename in fixed:
        v.check(v.sha(root/filename)==control["firmware_assets"][filename], f"{filename} drifted")
    dma = "kv260-ddr4-burst-dma-direct.dtbo"
    nodes = v.read_overlay(root/dma)
    v.check(nodes[base+"/ddr4-weights@a0000060"]=={
        "compatible":b"gradiated,kv260-ddr4-burst-v1\0", "reg":v.cells(0,0xa0000060,0,0x30),
        "gradiated,verified-direct-dma":b"",
    }, "Unexpected direct DMA properties")
    v.require_props(nodes["/__fixups__"], {"amba":b"/fragment@0:target:0\0"})
    return {p.name:v.sha(p) for p in (root/PROGRAM, *(root/n for n in fixed),root/dma)}

def verify_firmware(v, root, control):
    fw = FIRMWARE+".bit.bin"
    asset = root/"offline-package"/fw
    bit = asset.with_suffix("").read_bytes()
    raw = asset.read_bytes()
    offset = len(bit)-len(raw)
    v.check(len(raw)==7797692 and offset>4 and
            int.from_bytes(bit[offset-4:offset], "big")==len(raw), "Invalid payload length")
    v.check(raw==b"".join(bit[i:i+4][::-1] for i in range(offset,len(bit),4)),
            "Bootgen output differs from independent byte swap")
    return {fw:v.sha(asset), **verify_overlays(v, root, control)}


def verify_rtl(v, root, tested_manifest, replay):
    record = json.loads(replay.read_text())
    sha = v.sha(tested_manifest)
    manifest = json.loads((root/"source-manifest.json").read_text())
    v.check(record["status"]=="passed" and record["implementation"]["sha256"]==sha and
            record["protocol"]["sha256"]==manifest["protocol_sha256"],
            "Tested source manifest or protocol differs from the admitted implementation")
    compiled = {Path(name).stem:pin for name,pin in manifest["files"].items()
                if name.startswith("implementation/rtl/") and name.endswith(".sv")}
    v.check(compiled==json.loads(tested_manifest.read_text()),
            "Vivado source closure differs from the exact tested RTL")
    return {"run":record["id"],"rtl_source_manifest_sha256":sha}

def validate(v, root, receipt, control):
    v.check(v.sha(control/"offline-acceptance.json")==CONTROL_AUDIT, "Exp14 acceptance drifted")
    v.check(v.sha(control/"server.tar.gz")==CONTROL_ARCHIVE, "Exp14 archive drifted")
    v.check(receipt["passed"] and json.loads((root/"build-outcome.json").read_text())["passed"],
            "Build did not complete")
    for phase in v.PHASES:
        info = json.loads((root/f"build/{phase}/phase.json").read_text())
        v.check(info["phase"]==phase and info["returncode"]==0 and not info["timed_out"]
                and info["expected_output_exists"], f"Incomplete {phase}")
    reports = root/"build/reports"
    timing = dict(line.split(maxsplit=1) for line in (reports/"metrics.txt").read_text().splitlines())
    v.check(timing["clock"]=="clk_pl_0 period_ns 20.000" and
            all(timing[k]=="1" for k in ("fully_placed","fully_routed")) and
            all(timing[k]=="0" for k in v.ZERO_METRICS) and
            all(float(timing[k])>=0 for k in ("setup_slack_ns","hold_slack_ns")), "20 ns route failed")
    utilization = (reports/"utilization.rpt").read_text()
    resources = {}
    for key,label in (("lut","CLB LUTs"),("register","CLB Registers"),("dsp","DSPs"),
                      ("bram_tile","Block RAM Tile")):
        match = re.search(rf"(?m)^\|\s*{label}\s*\|\s*(\d+(?:\.\d+)?)\s*\|",utilization)
        v.check(match, f"No utilization row: {label}")
        resources[key]=float(match[1])
    verify_bd(v,root)
    pins = verify_routed(v,reports/"ddr-routed-hp0.tsv")
    with tarfile.open(control/"server.tar.gz") as archive:
        adopted_psu = archive.extractfile(CONTROL_PSU).read().decode()
    v.check(v.ps_writes((root/CONTROL_PSU).read_text())==v.ps_writes(adopted_psu),
            "Exp15 generated PS writes differ from Exp14")
    projection_ram = [row for row in (reports/"ddr-primitives.tsv").read_text().splitlines()
                      if "/output_projection/" in row and row.split("\t")[-1] in {"RAMB18E2","RAMB36E2"}]
    v.check(bool(projection_ram), "Missing BRAM control storage")
    return dict(passed=True, board_programmed=False, timing=timing, resources=resources,
                routed_hp0=pins, projection_brams=projection_ram, generated_psu_matches_exp14=True,
                firmware_assets=verify_firmware(v,root,json.loads((control/"offline-acceptance.json").read_text())))

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("archive","receipt","destination","exp14_run","result"):
        parser.add_argument(key,type=Path)
    parser.add_argument("--manifest-pin",required=True)
    parser.add_argument("--rtl-manifest",type=Path,required=True)
    parser.add_argument("--rtl-run",type=Path,required=True)
    parser.add_argument("--common-verifier",type=Path,
                        default=Path(__file__).resolve().parents[2]/"output-projection-ddr4-v1"/"build"/"verify.py")
    args=parser.parse_args()
    common=common_tools(args.common_verifier)
    receipt=common.recover(args.archive,args.receipt,args.destination,args.manifest_pin)
    evidence=validate(common,args.destination,receipt,args.exp14_run)
    evidence["rtl_replay"]=verify_rtl(common,args.destination,args.rtl_manifest,args.rtl_run)
    with args.result.open("x") as out:
        json.dump(evidence,out,indent=2,sort_keys=True)
        out.write("\n")
