"""Prepare the separate Exp16 DDR logits implementation from pinned routes."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile

CONTROL_INPUT_SHA = "4339b7b6f7b5129c6137055a205feedee2c9b7f8806e8a3a2028acc1a9033064"
SHELL_INPUT_SHA = "a72ca2df860ac61bb04b5d733dada3983584e271a8c5f42b1c264a73a5a95eb1"
BASE_FIRMWARE = "gradiated-tiny-output-projection-ddr4-burst-v1-50mhz"
FIRMWARE = "gradiated-tiny-logits-ddr4-burst-v1-50mhz"
BASE_PROGRAM = "kv260-output-projection-ddr4-burst-program.dtbo"
PROGRAM = "kv260-logits-ddr4-burst-program.dtbo"
BASE_DMA = "kv260-ddr4-burst-dma-direct"
DMA = "kv260-logits-ddr4-dma-direct"
PROTOCOL = "hardware/research/inference/experiments/kv260-logits-ddr4-burst-v1.md"
PREFIX = "implementation/rtl/"

def sha(data):
    return sha256(data).hexdigest()

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one anchor: {old}")
    return text.replace(old, new)

def archive(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError(f"Archive identity differs: {path}")
    with tarfile.open(fileobj=BytesIO(data)) as source:
        files = {entry.name.removeprefix("./"):source.extractfile(entry).read() for entry in source.getmembers() if entry.isfile() and not Path(entry.name).name.startswith("._")}
    manifest = json.loads(files.pop("source-manifest.json"))
    if {name:sha(data) for name,data in files.items()} != manifest["files"]:
        raise ValueError(f"Archive closure differs: {path}")
    return files,manifest

def generated(root):
    manifest = json.loads((root/"source-manifest.json").read_text())
    files = {p.stem:p.read_bytes() for p in root.glob("*.sv")}
    if {name:sha(data) for name,data in files.items()} != manifest:
        raise ValueError(f"Generated RTL closure differs: {root}")
    return files

def prepare(args):
    if not re.fullmatch(r"logits-ddr4-burst-build-[0-9]{8}T[0-9]{6}Z", args.attempt):
        raise ValueError("Unexpected attempt ID")
    _, prior = archive(args.control_archive, CONTROL_INPUT_SHA)
    legacy = {Path(name).stem:sha for name,sha in prior["files"].items()
              if name.startswith(PREFIX) and name.endswith(".sv")}
    control = generated(args.control_rtl)
    if {name:sha(data) for name,data in control.items()} != legacy or len(legacy) != 11:
        raise ValueError("Materialised BRAM control differs from the routed Exp13 module sources")
    rtl = generated(args.candidate_rtl)
    if rtl.keys() != (legacy.keys() | {"logits_group_reader"}):
        raise ValueError("Unexpected candidate HDL source list")
    changed = {name for name,pin in legacy.items() if sha(rtl[name]) != pin}
    if changed != {"axi_transformer","transformer"}:
        raise ValueError(f"Unexpected required-module differences: {changed}")

    files,manifest = archive(args.shell_archive,SHELL_INPUT_SHA)
    existing = {Path(name).stem:sha for name,sha in manifest["files"].items()
                if name.startswith(PREFIX) and name.endswith(".sv")}
    for name in existing:
        del files[f"{PREFIX}{name}.sv"]
    for name,data in rtl.items():
        files[f"{PREFIX}{name}.sv"] = data
    shell = "implementation/tools/ddr-shell.tcl"
    files[shell] = once(files[shell].decode(),
                        "dense_ddr_projection projection_ddr_reader",
                        "logits_group_reader").encode()
    build = "implementation/tools/autonomous-build.tcl"
    tcl = files[build].decode()
    slash = chr(92)
    for name,pin in existing.items():
        old = f"    {name} {pin}"
        if name not in rtl:
            tcl = once(tcl, old+" "+slash+"\n", "")
        else:
            tcl = once(tcl, old, f"    {name} {sha(rtl[name])}")
    top_line = f"    axi_transformer {sha(rtl['axi_transformer'])}"
    tcl = once(tcl,top_line, f"    logits_group_reader {sha(rtl['logits_group_reader'])} {slash}\n" + top_line)
    tcl = once(tcl, "REF_NAME =~ RAM* || REF_NAME == DSP48E2 || REF_NAME == PS8",
               "REF_NAME =~ RAM* || REF_NAME =~ URAM* || REF_NAME == DSP48E2 || REF_NAME == PS8")
    files[build] = tcl.encode()
    old_root = manifest["remote_root"]
    new_root = f"{old_root.rsplit('/',1)[0]}/{args.attempt}"
    for name in ("run-all.py","run-phase.py","convert-bit.py","autonomous-program.dts"):
        files[name] = files[name].decode().replace(old_root,new_root).replace(
            BASE_FIRMWARE,FIRMWARE).replace(BASE_PROGRAM,PROGRAM).replace(BASE_DMA,DMA).encode()
    del files[BASE_DMA+".dts"]
    files[DMA+".dts"] = args.dma.read_bytes()
    manifest.update(remote_root=new_root,
                    files={name:sha(body) for name,body in files.items()},
                    protocol_sha256=sha((args.repo/PROTOCOL).read_bytes()),
                    reused_control_input_sha256=CONTROL_INPUT_SHA,
                    reused_control_modules=legacy)
    manifest_bytes = (json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode()
    files["source-manifest.json"] = manifest_bytes
    args.destination.mkdir(parents=True)
    for name,body in files.items():
        target = args.destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(body)
    print(json.dumps({"remote":new_root,"manifest_sha256":sha(manifest_bytes)}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo","control_archive","shell_archive","control_rtl","candidate_rtl","destination"):
        parser.add_argument(arg,type=Path)
    parser.add_argument("attempt")
    parser.add_argument("--dma",type=Path,required=True)
    prepare(parser.parse_args())
