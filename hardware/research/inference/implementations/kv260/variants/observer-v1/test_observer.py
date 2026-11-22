"""Bounded numerical, AXI edge and cycle-equivalence checks for observer-v1."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
from materialise import materialise
from validate_snapshot import validate_snapshot

HERE = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()

def checked_run(command, cwd, env, log, limit=150):
    with log.open('x') as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(limit)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code:
        raise RuntimeError(f'Failed ({code}), see {log}')

def main(args):
    baseline, output = args.baseline.resolve(), args.output.resolve()
    tool = args.verilator.resolve()
    pin = json.loads((baseline/'toolchain.json').read_text())
    files = {str(f.relative_to(tool)):sha(f.read_bytes()) for f in sorted(tool.rglob('*')) if f.is_file()}
    if len(files) != pin['tree_files'] or sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode()) != pin['tree_sha256']:
        raise ValueError('Simulator tree differs from the pinned toolchain')
    package = args.bundle.resolve()
    raw = (package/'package.json').read_bytes()
    if sha(raw) != 'b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167':
        raise ValueError('Frozen board package differs')
    manifest = json.loads(raw)
    for name in ('model-words.bin','bos-logits.json'):
        if sha((package/name).read_bytes()) != manifest['files'][name]['sha256']:
            raise ValueError(f'Fixture differs: {name}')
    output.mkdir(parents=True, exist_ok=False)
    names = materialise(baseline, output/'rtl')
    source_pins = json.loads((HERE/'manifest.json').read_text())
    if sha((baseline/'axi_transformer_core_tb.sv').read_bytes()) != source_pins['baseline_testbench_sha256']:
        raise ValueError('Frozen equivalence testbench differs')
    values = {'model':struct.unpack('<29281I',(package/'model-words.bin').read_bytes()),
              'scores':json.loads((package/'bos-logits.json').read_text())['logits']}
    for name, items in values.items():
        (output/(name+'.hex')).write_text(''.join(f'{value&0xffffffff:08x}\n' for value in items))
    env = dict(os.environ, VERILATOR_ROOT=str(tool/'share/verilator'))
    if sys.platform == 'darwin':
        env.update(PATH='/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                   SDKROOT='/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
    def check(name, sources, fixture=True):
        folder = output/name
        folder.mkdir()
        checked_run([str(tool/'bin/verilator'),'--binary','--timing','--assert','-Wall','-Wno-fatal',
                     '--top-module',name,'-j','2','--Mdir',str(folder/'obj'),'-o','simulation',
                     *map(str,sources)], output, env, folder/'compile.log')
        command = [str(folder/'obj/simulation'),'+CSV='+str(folder/'events.csv'),'+VCD='+str(folder/'unused.vcd')]
        if fixture:
            command += ['+MODEL='+str(output/'model.hex'),'+SCORES='+str(output/'scores.hex'),
                        '+RETURNS='+str(folder/'returns.csv')]
        checked_run(command, output, env, folder/'simulation.log')
        print((folder/'simulation.log').read_text().splitlines()[0], flush=True)
    check('observer_edge_tb',[output/'rtl/axi_transformer.sv',HERE/'tests/observer_edge_tb.sv'],False)
    check('observer_core_tb',[*[output/'rtl'/(name+'.sv') for name in names],HERE/'tests/observer_core_tb.sv'])
    snapshots = [list(map(int, line.split()[2:])) for line in (output/'observer_core_tb/simulation.log').read_text().splitlines() if line.startswith('OBSERVER ')]
    if len(snapshots) != 2:
        raise ValueError('Missing observer snapshots')
    for counts in snapshots:
        words = [0x4b563031, 0, 0] + counts
        validate_snapshot(words, 1)
        for index in (0, 1, 2, 3, 22, 23, 24, 28, 32):
            corrupt = words[:]
            corrupt[index] += 1
            try:
                validate_snapshot(corrupt, 1)
            except ValueError:
                pass
            else:
                raise ValueError(f'Corrupt snapshot accepted at {index}')
    for name, source in [('equivalence_base',baseline),('equivalence_variant',output/'rtl')]:
        text = (baseline/'axi_transformer_core_tb.sv').read_text().replace(
            'module axi_transformer_core_tb;',f'module {name};').replace('$dumpfile(wavefile);$dumpvars(0,dut);','')
        tb = output/(name+'.sv')
        tb.write_text(text)
        check(name,[*[source/(n+'.sv') for n in names],tb])
    result = {'passed':True,'evidence_type':'RTL simulation','scope':'two BOS requests, synthetic AXI edge cases',
              'cycle_equivalence':{}}
    for name in ('events.csv','returns.csv'):
        original = (output/'equivalence_base'/name).read_bytes()
        if original != (output/'equivalence_variant'/name).read_bytes():
            raise ValueError(f'Baseline trace differs: {name}')
        result['cycle_equivalence'][name] = {'bytes':len(original),'sha256':sha(original)}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,default=HERE.parents[1]/'rtl')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--verilator',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
