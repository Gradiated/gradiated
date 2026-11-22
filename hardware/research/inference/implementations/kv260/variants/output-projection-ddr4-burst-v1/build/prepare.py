"""Derive an isolated Exp15 Vivado closure from the exact Exp14 build input."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile

BASE_SHA = '3d65e514925d81dedb5f1248495310a43efa7aa73f7666fb90c1c9cac9068a26'
BASE_FIRMWARE = 'gradiated-tiny-output-projection-ddr4-v1-50mhz'
FIRMWARE = 'gradiated-tiny-output-projection-ddr4-burst-v1-50mhz'
BASE_PROGRAM = 'kv260-output-projection-ddr4-program.dtbo'
PROGRAM = 'kv260-output-projection-ddr4-burst-program.dtbo'
PROTOCOL = 'hardware/research/inference/experiments/kv260-output-projection-ddr4-burst-v1.md'

def digest(data):
    return sha256(data).hexdigest()

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one anchor: {old}')
    return text.replace(old, new)

def prepare(args):
    if not re.fullmatch(r'output-projection-ddr4-burst-(?:preflight|build)-[0-9]{8}T[0-9]{6}Z', args.attempt):
        raise ValueError('Unexpected attempt ID')
    base = args.control.read_bytes()
    if digest(base) != BASE_SHA:
        raise ValueError('Exp14 exact input archive hash differs')
    with tarfile.open(fileobj=BytesIO(base)) as tar:
        files = {item.name:tar.extractfile(item).read() for item in tar.getmembers() if item.isfile()}
    manifest = json.loads(files.pop('source-manifest.json'))
    if {name:digest(content) for name,content in files.items()} != manifest['files']:
        raise ValueError('Exp14 source manifest differs')
    old_remote = manifest['remote_root']
    new_remote = f'{old_remote.rsplit("/",1)[0]}/{args.attempt}'
    rtl = {path.stem:path.read_bytes() for path in args.rtl.glob('*.sv')}
    if not args.preflight:
        pins = json.loads((args.rtl/'source-manifest.json').read_text())
        if {name:digest(content) for name,content in rtl.items()} != pins:
            raise ValueError('Exp15 RTL differs from the materialised manifest')
    prefixes = 'implementation/rtl/'
    inherited_rtl = {Path(name).stem for name in files if name.startswith(prefixes) and name.endswith('.sv')}
    if inherited_rtl != rtl.keys():
        raise ValueError(f'Unexpected RTL compile closure: {sorted(inherited_rtl ^ rtl.keys())}')
    for name, contents in rtl.items():
        files[f'{prefixes}{name}.sv'] = contents
    shell = 'implementation/tools/ddr-shell.tcl'
    files[shell] = once(files[shell].decode(), 'MAX_BURST_LENGTH 1"', 'MAX_BURST_LENGTH 8"').encode()
    tcl_name = 'implementation/tools/autonomous-build.tcl'
    tcl = files[tcl_name].decode()
    for name, content in rtl.items():
        old_pin = manifest['files'][f'{prefixes}{name}.sv']
        tcl = once(tcl, f'    {name} {old_pin}', f'    {name} {digest(content)}')
    tcl = once(tcl, 'set roots [get_nets -quiet -segments -of_objects $net]',
               'set roots [get_nets -quiet -segments -of_objects $pin]')
    # Keep the read/write clock evidence in the final checkpoint's native pin trace.
    tcl = once(tcl, '                puts $hp "$pin\\t$net\\t$drivers\\t$types"',
               '                set clocks [get_clocks -quiet -of_objects $pin]\n'
               '                puts $hp "$pin\\t$net\\t$drivers\\t$types\\t$clocks"')
    files[tcl_name] = tcl.encode()
    for name in ('run-all.py','run-phase.py','convert-bit.py','autonomous-program.dts'):
        files[name] = files[name].decode().replace(old_remote,new_remote).replace(
            BASE_FIRMWARE,FIRMWARE).replace(BASE_PROGRAM,PROGRAM).encode()
    runner = files['run-all.py'].decode()
    dma_compile = " checked(['/home/admin/amd/2025.2/Vivado/bin/dtc','-@','-I','dts','-O','dtb','-o','kv260-ddr4-dma.dtbo','kv260-ddr4-dma.dts'],'dma-compile.log')"
    if args.preflight:
        runner = once(runner, "['generate','synth','opt','place','route','reports','bitstream']", "['generate']")
        runner = once(runner, " checked([sys.executable,str(root/'convert-bit.py')],'convert.log',75)\n", "")
    else:
        del files['kv260-ddr4-dma.dts']
        for source in (args.dma, args.restore):
            files[source.name] = source.read_bytes()
        dtc = " checked(['/home/admin/amd/2025.2/Vivado/bin/dtc','-@','-I','dts','-O','dtb',"
        def compile_overlay(src, role):
            return dtc+f"'-o','{src.stem}.dtbo','{src.name}'],'{role}-compile.log')"
        runner = once(runner, dma_compile,
                      '\n'.join((compile_overlay(args.dma,'direct-dma'),compile_overlay(args.restore,'afi-restore'))))
    files['run-all.py'] = runner.encode()
    manifest.update(remote_root=new_remote,
                    files={name:digest(content) for name,content in files.items()},
                    hp0_max_burst_beats=8)
    if not args.preflight:
        manifest['protocol_sha256']=digest((args.repo/PROTOCOL).read_bytes())
    files['source-manifest.json']=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    args.destination.mkdir(parents=True)
    for name, contents in files.items():
        path=args.destination/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(contents)
    print(json.dumps({'remote':new_remote,'manifest_sha256':digest(files['source-manifest.json'])}))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('repo','control','rtl','destination'):
        p.add_argument(arg,type=Path)
    p.add_argument('attempt')
    p.add_argument('--preflight',action='store_true')
    p.add_argument('--dma',type=Path)
    p.add_argument('--restore',type=Path)
    args=p.parse_args()
    if not args.preflight and not (args.dma and args.restore):
        p.error('--dma and --restore are required for the final build')
    prepare(args)
