"""Prepare the exact Experiment 14 isolated Vivado closure from the adopted build archive."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

BASE_ARCHIVE_SHA = "4339b7b6f7b5129c6137055a205feedee2c9b7f8806e8a3a2028acc1a9033064"
BASE_SHELL_SHA = '1e0c61f601724241c0eff1d95f6bc50b1e5df42cf2ee78edc9f1cf727f411001'
BASE_SHELL = 'hardware/research/inference/implementations/kv260/tools/kv260-shell.tcl'
RUNTIME = '/home/admin/projects/gradiated/.agents/runtime/fpga-inference'
VARIANT = 'output-projection-ddr4-v1'
CONTROL = 'attention-exp-pair-v2'
APERTURE = 0x80000000
PS_PORT = "S_AXI_HP0_FPD"

SIGNALS = (
    ('ARADDR', 49, 'output'), ('ARID', 6, 'output'), ('ARLEN', 8, 'output'),
    ('ARSIZE', 3, 'output'), ('ARBURST', 2, 'output'), ('ARLOCK', 1, 'output'),
    ('ARCACHE', 4, 'output'), ('ARPROT', 3, 'output'), ('ARQOS', 4, 'output'),
    ('ARVALID', 1, 'output'), ('ARREADY', 1, 'input'), ('RDATA', 64, 'input'),
    ('RID', 6, 'input'), ('RRESP', 2, 'input'), ('RLAST', 1, 'input'),
    ('RVALID', 1, 'input'), ('RREADY', 1, 'output'),
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one shell anchor: {old}")
    return text.replace(old, new)

def shell_text(base, rtl):
    base = once(base, 'set repo [file dirname [file dirname $workstream]]',
                'set repo /home/admin/projects/gradiated')
    base = once(base, 'ASSOCIATED_BUSIF S_AXI,', 'ASSOCIATED_BUSIF S_AXI:M_AXI,')
    ports = ['    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 M_AXI ARUSER" *) output wire m_axi_aruser']
    wiring = []
    for signal, width, direction in SIGNALS:
        name = f"m_axi_{signal.lower()}"
        attrs = f'X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 M_AXI {signal}"'
        if signal == 'ARADDR':
            attrs += ', X_INTERFACE_PARAMETER="XIL_INTERFACENAME M_AXI, PROTOCOL AXI4, DATA_WIDTH 64, ADDR_WIDTH 49, ID_WIDTH 6, READ_WRITE_MODE READ_ONLY, NUM_READ_OUTSTANDING 1, MAX_BURST_LENGTH 1"'
        vector = f" [{width - 1}:0]" if width > 1 else ""
        ports.append(f"    (* {attrs} *) {direction} wire{vector} {name}")
        wiring.append(f"        .{name}({name})")
    base = once(base, 'input wire s_axi_rready\n);',
                'input wire s_axi_rready,\n' + ',\n'.join(ports) + '\n);')
    base = once(base, '    axi_transformer actual (',
                "    assign m_axi_aruser = 1'b0;\n    axi_transformer actual (")
    base = once(base, '.s_axi_rready(s_axi_rready)\n    );',
                '.s_axi_rready(s_axi_rready),\n' + ',\n'.join(wiring) + '\n    );')
    base = once(base, '    feedforward transformer axi_transformer\n',
                '    feedforward transformer axi_transformer ' + ' '.join(rtl) + '\n')
    anchor = '    CONFIG.PSU__NUM_FABRIC_RESETS'
    prefix = "    CONFIG.PSU__USE__S_AXI_GP2 {1} \\\n    CONFIG.PSU__SAXIGP2__DATA_WIDTH {64} \\\n"
    base = once(base, anchor, prefix + anchor)
    anchor = 'connect_bd_net [get_bd_pins ps/pl_clk0]'
    base = once(base, anchor, '\n'.join([
        'set hp [get_bd_intf_pins ps/S_AXI_HP0_FPD]',
        'set m [get_bd_intf_pins neural/M_AXI]',
        'if {[llength $hp] != 1 || [llength $m] != 1} {error "Missing HP0 or neural master"}',
        'connect_bd_intf_net $m $hp',
        'connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/saxihp0_fpd_aclk]',
        '',
    ]) + anchor)
    anchor = '\nvalidate_bd_design\n'
    base = once(base, anchor, '''
set hp_targets [get_bd_addr_segs -quiet -of_objects $hp]
set hp_low [lsearch -all -inline -glob $hp_targets */HP0_DDR_LOW]
if {[llength $hp_low] != 1} {error "Missing exact HP0 DDR low segment: $hp_targets"}
assign_bd_address -target_address_space [get_bd_addr_spaces neural/M_AXI] \\
    -offset 0x00000000 -range 0x80000000 [lindex $hp_low 0]
# Preserve the low aperture exclusively. The FPGA master also checks the base
# and complete weight image in RTL before issuing any AXI transaction.
foreach target $hp_targets {
    if {$target ni $hp_low} {
        exclude_bd_addr_seg -target_address_space [get_bd_addr_spaces neural/M_AXI] $target
    }
}
validate_bd_design
if {[get_property CONFIG.DATA_WIDTH $hp] != 64 || [get_property CONFIG.DATA_WIDTH $m] != 64} {
    error "HP0 and neural interface are not both 64 bits"
}
''')
    return once(base, 'axi/M00_AXI neural/S_AXI}', 'axi/M00_AXI neural/S_AXI ps/S_AXI_HP0_FPD neural/M_AXI}')

def prepare(args):
    archive = args.baseline.read_bytes()
    if sha(archive) != BASE_ARCHIVE_SHA:
        raise ValueError("Adopted input archive differs from physical control build")
    if not re.fullmatch(r'output-projection-ddr4-(?:preflight|build)-[0-9]{8}T[0-9]{6}Z', args.attempt):
        raise ValueError("Unexpected attempt name")
    remote = str(PurePosixPath(RUNTIME) / args.attempt)
    with tarfile.open(args.baseline) as tar:
        files = {info.name: tar.extractfile(info).read() for info in tar.getmembers() if info.isfile()}
    manifest = json.loads(files.pop('source-manifest.json'))
    if {name:sha(data) for name,data in files.items()} != manifest['files']:
        raise ValueError("Adopted input manifest does not close")
    rtl = {}
    for path in sorted(args.rtl.glob('*.sv')):
        if not re.fullmatch(r'[a-z][a-z0-9_]*', path.stem):
            raise ValueError(f"Unexpected RTL filename: {path}")
        rtl[path.stem] = path.read_bytes()
    baseline_rtl = {PurePosixPath(name).stem for name in files if name.endswith('.sv')}
    if baseline_rtl - rtl.keys():
        raise ValueError(f"DDR RTL closure missing {sorted(baseline_rtl - rtl.keys())}")
    for name, data in rtl.items():
        files[f'implementation/rtl/{name}.sv'] = data
    shell_bytes = (args.repo / BASE_SHELL).read_bytes()
    if sha(shell_bytes) != BASE_SHELL_SHA:
        raise ValueError("KV260 pinned source shell differs")
    shell = shell_bytes.decode()
    if not args.preflight:
        tested_rtl = json.loads((args.rtl / 'source-manifest.json').read_text())
        if {name:sha(data) for name,data in rtl.items()} != tested_rtl:
            raise ValueError("DDR RTL hashes differ from generated source manifest")
    extra_names = sorted(rtl.keys() - baseline_rtl)
    files['implementation/tools/ddr-shell.tcl'] = shell_text(shell, extra_names).encode()
    tcl_name = 'implementation/tools/autonomous-build.tcl'
    tcl = files[tcl_name].decode()
    for name in sorted(baseline_rtl):
        tcl = re.sub(rf'(?m)^(    {name} )[0-9a-f]{{64}}',
                     rf'\g<1>{sha(rtl[name])}', tcl, count=1)
    if extra_names:
        entries = [f"    {name} {sha(rtl[name])} " + chr(92) + "\n" for name in extra_names]
        tcl = once(tcl, '    axi_transformer ', ''.join(entries) + '    axi_transformer ')
        tcl = once(tcl, 'foreach name {fixed_scalar mac32 qk_rope kv_cache frontend attention dense rmsnorm feedforward transformer axi_transformer} {',
                   'foreach name [dict keys $neural_pins] {')
    tcl = once(tcl, '    validate_bd_design\n    save_bd_design',
               '''    validate_bd_design
    set ddr [open [file join $output ddr-interfaces.txt] w]
    foreach name {ps/S_AXI_HP0_FPD neural/M_AXI} {
        set intf [get_bd_intf_pins $name]
        puts $ddr "\\nINTERFACE $name"
        puts $ddr [report_property -all -return_string $intf]
        puts $ddr "NET [get_bd_intf_nets -of_objects $intf]"
    }
    foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces neural/M_AXI]] {
        puts $ddr "\\nADDRESS $seg"
        puts $ddr [report_property -all -return_string $seg]
    }
    close $ddr
    save_bd_design''')
    tcl = once(tcl, '        close $stream\n    }\n    report_timing_summary', '''        close $stream
        set census [open [file join $output ddr-primitives.tsv] w]
        foreach cell [get_cells -hierarchical -quiet -filter {REF_NAME =~ RAM* || REF_NAME == DSP48E2 || REF_NAME == PS8}] {
            puts $census "[get_property NAME $cell]\\t[get_property REF_NAME $cell]"
        }
        close $census
        set hp [open [file join $output ddr-routed-hp0.tsv] w]
        set ps8 [get_cells -hierarchical -quiet -filter {REF_NAME == PS8}]
        foreach pin [get_pins -quiet -of_objects $ps8 -filter {NAME =~ *SAXIGP2*}] {
            set net [get_nets -quiet -of_objects $pin]
            if {[llength $net]} {
                set roots [get_nets -quiet -segments -of_objects $net]
                set drivers [get_pins -quiet -leaf -of_objects $roots -filter {DIRECTION == OUT}]
                set types {}
                if {[llength $drivers]} {
                    set types [get_property REF_NAME [get_cells -quiet -of_objects $drivers]]
                }
                puts $hp "$pin\\t$net\\t$drivers\\t$types"
            }
        }
        close $hp
    }
    report_timing_summary''')
    files[tcl_name] = tcl.encode()
    phase = files['run-phase.py'].decode()
    phase = re.sub(r"'/home/admin/projects/gradiated/[^']+/generate/project/tiny_ps_axi_build.xpr'",
                   repr(f'{remote}/shell/project/tiny_ps_axi_candidate.xpr'), phase)
    files['run-phase.py'] = phase.encode()
    all_phases = files['run-all.py'].decode()
    if args.preflight:
        all_phases = once(all_phases, "['generate','synth','opt','place','route','reports','bitstream']", "['generate']")
        all_phases = once(all_phases, " checked([sys.executable,str(root/'convert-bit.py')],'convert.log',75)\n", "")
    all_phases = once(all_phases, ' for phase in [',
                      """ checked(['/home/admin/amd/2025.2/Vivado/bin/vivado','-mode','batch','-notrace',
          '-source', str(root/'implementation/tools/ddr-shell.tcl'),'-tclargs',str(root/'shell'),'50'],
         'ddr-shell.log',180)
 for phase in [""")
    if not args.preflight:
        for source, kind in (('kv260-ddr4-interface.dts','interface'), ('kv260-ddr4-dma.dts','dma')):
            files[source] = Path(__file__).with_name(source).read_bytes()
            all_phases = all_phases.replace(' for phase in [', (
                " checked(['/home/admin/amd/2025.2/Vivado/bin/dtc','-@','-I','dts','-O','dtb',"
                f"'-o','kv260-ddr4-{kind}.dtbo','{source}'],'{kind}-compile.log')\n for phase in ["
            ), 1)
    files['run-all.py'] = all_phases.encode()
    for name in ('run-all.py', 'convert-bit.py', 'autonomous-program.dts'):
        files[name] = files[name].decode().replace(manifest['remote_root'], remote).replace(
            CONTROL, VARIANT).replace('-output-projection-ddr4-v1-program', '-output-projection-ddr4-program').encode()
    protocol = args.repo / 'hardware/research/inference/experiments/kv260-output-projection-ddr4-v1.md'
    manifest.update(remote_root=remote, protocol_sha256=sha(protocol.read_bytes()),
                    files={name:sha(data) for name,data in files.items()},
                    hp_port=PS_PORT, ddr_aperture_bytes=APERTURE)
    files['source-manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    for name, data in files.items():
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    print(json.dumps({'remote':remote, 'manifest_sha256':sha(files['source-manifest.json'])}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'baseline', 'rtl', 'out'):
        parser.add_argument(name, type=Path)
    parser.add_argument('attempt')
    parser.add_argument('--preflight', action='store_true', help='Generate the Vivado design without synthesis')
    prepare(parser.parse_args())
