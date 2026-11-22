"""Verify recovered Experiment 14 implementation, PS deltas and board assets."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tarfile

PHASES = ("generate", "synth", "opt", "place", "route", "reports", "bitstream")
ZERO_METRICS = (
    "drc_errors_or_critical_warnings", "routing_errors", "unrouted_nets",
    "partially_routed_nets", "routing_gap_nets", "unclocked_active_pins",
    "unconstrained_internal_endpoints",
)
EXPECTED_PSU_CHANGES = {
    (0xfd380000, 3, 1): 1,
    (0xfd380014, 3, 1): 1,
}
ADOPTED_ARCHIVE_SHA = "7ed800eb74f957dff3647f679a48dadbe70921d176c6887a1bbf4f639c714362"
FIRMWARE_NAME = "gradiated-tiny-output-projection-ddr4-v1-50mhz.bit.bin"

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def check(condition, message):
    if not condition:
        raise ValueError(message)

def recover(archive, receipt, destination, expected_pin):
    received = json.loads(receipt.read_text())
    check(archive.stat().st_size == received["bytes"] and sha(archive) == received["sha256"],
          "Recovered archive differs from the remote receipt")
    destination.mkdir()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        names = {item.name for item in members}
        check(len(names) == len(members) and all(
            item.isfile() and (destination / item.name).resolve().is_relative_to(destination.resolve())
            for item in members
        ), "Unexpected archive member")
        for member in members:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output, tar.extractfile(member) as source:
                shutil.copyfileobj(source, output)
    files = json.loads((destination / "recovery-manifest.json").read_text())["files"]
    check(len(files) == received["files"] and set(files) == names - {"recovery-manifest.json"},
          "Archive members do not match recovery manifest")
    for name, pin in files.items():
        path = destination / name
        check(sha(path) == pin["sha256"] and path.stat().st_size == pin["bytes"], f"Member drift: {name}")
    source = destination / "source-manifest.json"
    check(sha(source) == expected_pin, "Recovered build source manifest differs")
    for name, digest in json.loads(source.read_text())["files"].items():
        check(sha(destination / name) == digest, f"Source drift: {name}")
    return received

def ps_writes(tcl):
    rows = re.findall(r"^\s*mask_write +(0[xX][\da-fA-F]+) +(0[xX][\da-fA-F]+) +(0[xX][\da-fA-F]+)",
                      tcl, flags=re.MULTILINE)
    return [tuple(int(field, 16) for field in row) for row in rows]

def verify_psu(root, adopted):
    check(sha(adopted) == ADOPTED_ARCHIVE_SHA, "Unexpected adopted routed archive")
    candidate, = (root / "build/generate/project").rglob("psu_init.tcl")
    target = "build/generate/project/tiny_ps_axi_build.gen/sources_1/bd/tiny_ps_axi/ip/tiny_ps_axi_ps_0/psu_init.tcl"
    with tarfile.open(adopted) as tar:
        control = tar.extractfile(target).read().decode()
    previous = ps_writes(control)
    current = ps_writes(candidate.read_text())
    expected = Counter(EXPECTED_PSU_CHANGES)
    check(previous and Counter(current) - Counter(previous) == expected and
          [row for row in current if row not in expected] == previous,
          "Unexpected generated PS register write difference or reordering")
    return [{"address": hex(address), "mask": mask, "value": value}
            for address, mask, value in EXPECTED_PSU_CHANGES]

def verify_interfaces(build):
    contents = (build / "generate/ddr-interfaces.txt").read_text()
    hp, rtl = contents.split("INTERFACE ")[1:]
    for side in (hp, rtl):
        for property_name, value in (("ADDR_WIDTH", 49), ("ID_WIDTH", 6), ("DATA_WIDTH", 64),
                                     ("MAX_BURST_LENGTH", 1), ("FREQ_HZ", 49999500),
                                     ("PROTOCOL", "AXI4"), ("CLK_DOMAIN", "tiny_ps_axi_ps_0_pl_clk0")):
            check(re.search(rf"(?m)^CONFIG\.{property_name} +\S+ +\S+ +{value}$", side),
                  f"Incompatible or missing interface property: {property_name}")
        check("\nNET /neural_M_AXI\n" in side, "Expected native direct HP0 net")
    check("READ_ONLY" in rtl and rtl.count("\nADDRESS ") == 1 and "SEG_ps_HP0_DDR_LOW" in rtl,
          "Expected one read-only interface to HP0 low DDR")
    for property_name, value in (("OFFSET", 0), ("RANGE", 0x80000000), ("REMAPPED", 0)):
        match = re.search(rf"(?m)^{property_name} +\S+ +\S+ +(\S+)$", rtl)
        check(match and int(match[1], 0) == value, f"Unexpected aperture {property_name}")

def verify_routed_hp(path):
    rows = [line.split("\t") for line in path.read_text().splitlines()]
    def pins(fragment):
        return [row for row in rows if fragment in row[0]]
    def constant(row, value):
        primitive = "VCC" if value else "GND"
        name = row[1].rsplit("/", 1)[-1]
        return row[-1].split() == [primitive] or (not row[-1] and name == f"<const{value}>")

    for fragment, count in (("SAXIGP2ARID", 6), ("SAXIGP2AWVALID", 1), ("SAXIGP2ARUSER", 1),
                            ("SAXIGP2ARLEN", 8)):
        matching = pins(fragment)
        check(len(matching) == count and all(constant(row, 0) for row in matching),
              f"Expected {count} tied-low routed {fragment} pin(s): {matching}")
    for field, value_by_bit in (("ARPROT", (0, 1, 0)), ("ARSIZE", (1, 1, 0))):
        matching = pins(f"SAXIGP2{field}")
        check(len(matching) == len(value_by_bit), f"Unexpected HP0 {field} width")
        for bit, value in enumerate(value_by_bit):
            bit_pin = [row for row in matching if row[0].endswith((f"[{bit}]", f"{field}{bit}"))]
            check(len(bit_pin) == 1 and constant(bit_pin[0], value),
                  f"Unexpected routed HP0 {field}[{bit}] constant: {bit_pin}")
    read_data = pins("SAXIGP2RDATA")
    check(len(read_data) == 64 and all(row[1] for row in read_data),
          "Expected all 64 routed HP0 return data pins")
    for fragment in ("SAXIGP2ARVALID", "SAXIGP2ARREADY", "SAXIGP2RVALID", "SAXIGP2RREADY"):
        matching = pins(fragment)
        check(len(matching) == 1 and matching[0][1] and not any(
            constant(matching[0], value) for value in (0, 1)
        ),
              f"Expected an active routed HP0 signal: {fragment}")
    return {"arid": 0, "read_data_width": 64, "awvalid": 0, "aruser": 0, "arlen": 0, "arsize": 3, "arprot": 2}

def read_overlay(path):
    """Return fully named FDT nodes and properties for an independently checked overlay."""
    data = path.read_bytes()
    magic, size, start, strings, _, version, _, _, strings_size, block_size = struct.unpack_from(">10I", data)
    end = start + block_size
    strings_end = strings + strings_size
    check(magic == 0xD00DFEED and size == len(data) and version >= 17 and
          40 <= start < end <= strings <= strings_end <= size, f"Malformed FDT header: {path}")
    nodes = {}
    stack = []
    cursor = start
    while cursor < end:
        token, = struct.unpack_from(">I", data, cursor)
        cursor += 4
        if token == 1:
            terminator = data.index(0, cursor, end)
            stack.append(data[cursor:terminator].decode())
            nodes["/".join(stack)] = {}
            cursor = (terminator + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, offset = struct.unpack_from(">II", data, cursor)
            name_start = strings+offset
            name_end = data.index(0, name_start, strings_end)
            name = data[name_start:name_end].decode()
            cursor += 8
            check(cursor+size <= end, f"FDT property out of bounds: {name}")
            nodes["/".join(stack)][name] = data[cursor:cursor+size]
            cursor = (cursor+size+3) & ~3
        elif token == 9 and not stack:
            return nodes
        elif token != 4:
            raise ValueError(f"Unexpected FDT token: {token}")
    raise ValueError(f"FDT contains no terminator: {path}")

def cells(*values):
    return struct.pack(f">{len(values)}I", *values)

def require_props(actual, expected):
    for name, value in expected.items():
        check(actual.get(name) == value, f"Unexpected overlay property {name}: {actual.get(name)!r}")

def verify_overlays(root):
    program = root / "kv260-output-projection-ddr4-program.dtbo"
    interface = root / "kv260-ddr4-interface.dtbo"
    dma = root / "kv260-ddr4-dma.dtbo"
    program_nodes = read_overlay(program)
    require_props(program_nodes["/fragment@0/__overlay__"], {
        "firmware-name": FIRMWARE_NAME.encode()+b"\0", "resets": cells(0xFFFFFFFF, 119),
    })
    require_props(program_nodes["/__fixups__"], {
        "fpga_full": b"/fragment@0:target:0\0",
        "zynqmp_reset": b"/fragment@0/__overlay__:resets:0\0",
    })
    interface_nodes = read_overlay(interface)
    base = "/fragment@0/__overlay__"
    require_props(interface_nodes[base+"/tiny_transformer_afi"], {
        "compatible": b"xlnx,afi-fpga\0", "config-afi": cells(4, 1, 5, 1, 14, 0x800),
        "resets": cells(0xFFFFFFFF, 119),
    })
    require_props(interface_nodes[base+"/tiny-transformer@a0000000"], {
        "compatible": b"generic-uio\0", "reg": cells(0, 0xA0000000, 0, 0x60),
        "clocks": cells(0xFFFFFFFF, 71),
    })
    dma_nodes = read_overlay(dma)
    device = dma_nodes[base+"/ddr4-weights@a0000060"]
    check(set(device) == {"compatible", "reg"}, "Unexpected DMA-node address/translation properties")
    require_props(device, {
        "compatible": b"gradiated,kv260-ddr4-weights-v1\0",
        "reg": cells(0, 0xA0000060, 0, 0x30),
    })
    for nodes in (interface_nodes, dma_nodes):
        require_props(nodes["/__fixups__"], {"amba": b"/fragment@0:target:0\0"})
    return {path.name: sha(path) for path in (program, interface, dma)}

def verify_deployment_overlays(board_assets, recovered):
    direct = board_assets / "kv260-ddr4-dma-direct.dtbo"
    restore = board_assets / "kv260-ddr4-afi-restore.dtbo"
    dma_template = read_overlay(recovered / "kv260-ddr4-dma.dtbo")
    dma_template["/fragment@0/__overlay__/ddr4-weights@a0000060"]["gradiated,verified-direct-dma"] = b""
    check(read_overlay(direct) == dma_template, "Direct DMA overlay differs from admitted HP0 node")
    restore_nodes = read_overlay(restore)
    check(restore_nodes["/fragment@0/__overlay__/gradiated_hp0_afi_restore"] == {
        "compatible": b"xlnx,afi-fpga\0", "config-afi": cells(4, 0, 5, 0),
    }, "AFI restoration overlay differs from the admitted baseline width")
    require_props(restore_nodes["/__fixups__"], {"amba": b"/fragment@0:target:0\0"})
    return {path.name: sha(path) for path in (direct, restore)}

def verify_output(root):
    out = root / "offline-package"
    firmware = out / FIRMWARE_NAME
    raw = firmware.with_suffix("").read_bytes()
    converted = firmware.read_bytes()
    offset = len(raw) - len(converted)
    check(len(converted) == 7797692 and offset > 4 and
          int.from_bytes(raw[offset-4:offset], "big") == len(converted), "Unexpected .bit payload boundaries")
    check(b"".join(raw[i:i+4][::-1] for i in range(offset, len(raw), 4)) == converted,
          "Firmware differs from independently byte-swapped .bit payload")
    return {firmware.name: sha(firmware), **verify_overlays(root)}


def verify(root, adopted, receipt):
    check(receipt["passed"] and json.loads((root / "build-outcome.json").read_text())["passed"],
          "Remote build failed; recovered artifacts are available for diagnosis")
    build = root / "build"
    for phase in PHASES:
        stage = json.loads((build / phase / "phase.json").read_text())
        check(stage["phase"] == phase and stage["returncode"] == 0 and not stage["timed_out"] and
              stage["expected_output_exists"], f"Incomplete build phase: {phase}")
    reports = build / "reports"
    metrics = dict(line.split(maxsplit=1) for line in (reports / "metrics.txt").read_text().splitlines())
    check(metrics["clock"] == "clk_pl_0 period_ns 20.000" and all(
        metrics[key] == "1" for key in ("fully_placed", "fully_routed")
    ) and all(metrics[key] == "0" for key in ZERO_METRICS) and all(
        float(metrics[key]) >= 0 for key in ("setup_slack_ns", "hold_slack_ns")
    ), "20 ns route/timing admission failed")
    utilization = (reports / "utilization.rpt").read_text()
    resources = {}
    for name, label in (("lut", "CLB LUTs"), ("register", "CLB Registers"), ("dsp", "DSPs"),
                        ("bram_tile", "Block RAM Tile")):
        match = re.search(rf"(?m)^\|\s*{label}\s*\|\s*(\d+(?:\.\d+)?)\s*\|", utilization)
        check(match, f"No routed utilization row: {label}")
        resources[name] = float(match[1])
    verify_interfaces(build)
    psu = verify_psu(root, adopted)
    hp = verify_routed_hp(reports / "ddr-routed-hp0.tsv")
    prims = (reports / "ddr-primitives.tsv").read_text()
    projection_brams = [row for row in prims.splitlines() if "/output_projection/" in row and row.split("\t")[-1] in {"RAMB18E2", "RAMB36E2"}]
    check(bool(projection_brams), "Missing BRAM control storage in output projection hierarchy")
    return {
        "firmware_assets": verify_output(root), "timing": metrics, "resources": resources,
        "generated_psu_delta": psu, "routed_hp0": hp, "projection_brams": projection_brams,
        "board_programmed": False, "passed": True,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "receipt", "destination", "adopted_archive", "result"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--manifest-pin", required=True)
    parser.add_argument("--board-assets", type=Path)
    args = parser.parse_args()
    receipt = recover(args.archive, args.receipt, args.destination, args.manifest_pin)
    result = verify(args.destination, args.adopted_archive, receipt)
    if args.board_assets:
        result["firmware_assets"].update(verify_deployment_overlays(args.board_assets, args.destination))
    with args.result.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
