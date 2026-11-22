"""Prepare a sealed offline KV260 first-BOS package. Never accesses a board.

Uses only installed AMD tools; no package/model downloads or installations.
Every subprocess has a 60-second process-group watchdog. No FPGA programming,
network operation, driver load, clock change or physical MMIO occurs here.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import tarfile
import tempfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "product").is_dir() and (p / ".git").exists())
TOOLS = Path(__file__).resolve().parent
RUNTIME = ROOT / '.agents/runtime/hardware/inference'
AMD = Path('/home/admin/amd/2025.2')
PINS = {
    'vivado-prep/board-build-_4wbn4bx/offline-candidate.bit': '4f69ec2d1c41eca9dc33b42fa058c3440a2852fdcd42298e6f2c9893e4909cdd',
    'vivado-prep/pack-vp89u9_3/model-words.bin': '0198baeaeb48052895b5eb4f9622d61fb144295584e6823f8e42420fc0d73cf5',
    'vivado-prep/board-build-fzsm963h/results.json': '4ccb6b79023d6b5458035c1e20687c4e881d5483f0ae126f362fba2471f1fcfe',
    'vivado-prep/model-compare-2az1bnjc/results.json': 'a692b41a116ed4b7c3a62a8686652f16690f5bfaa90089fb2491fea5a7e87c98',
    'board-readiness/full-build-m6b0vzkp/generate/project/tiny_ps_axi_build.srcs/sources_1/bd/tiny_ps_axi/ip/tiny_ps_axi_ps_0/tiny_ps_axi_ps_0.xci': '661779569422cef31cf18660fce41586c81b1e6fae5454f3e9609725a4a44993',
    'board-readiness/full-build-m6b0vzkp/generate/project/tiny_ps_axi_build.gen/sources_1/bd/tiny_ps_axi/ip/tiny_ps_axi_ps_0/hdl/zynq_ultra_ps_e_v3_5_8.v': 'ca3d2841323e2236bea92841a147a76def63cf8ac291d704a95c353ed1936e7c',
    'rmsnorm-validation/whole-model-reference-20261104T101114Z/goldens.json': '36ae1ebe2fa0bedd74c2cf872742e996b776349ba579742b7931928c0ea0f3e6',
    'board-inspection/mac-ubuntu-24.04/original-json/transfer-manifest.json': '1d6011ab7f58f56dafca1e320796b5eb5e28ebd56db3c09787a8bb0020080151',
    'board-inspection/mac-ubuntu-24.04/live-support/transfer-manifest.json': 'f2aa50e19870a7ab987b14149e7075260c91e94cc6ad0ff3e3f82dcc91101ffe',
    'board-inspection/mac-ubuntu-24.04/clock-afi-driver-check-20261109T132436Z.json': '085558f8d5bf038a72f83591b975dcf2896a2b7f487aa288c8023babde239869',
    'board-generation/mac-sampling-20261109/board-sampling-draws.json': '7dd023b96ebe016ccbc626df89356a0e44fc8e2a928b6108820d78f393734b1a',
    'board-generation/mac-sampling-20261109/sampling-draws.json': 'e735b68f8a083d5a6a983d3bd9bf8247ffe7448c8fa10bb8c18ff8af1867ca2a',
}
RESET_DEFS = AMD / 'data/embeddedsw/lib/sw_apps/zynqmp_pmufw/src/pm_defs.h'
RESET_DEFS_SHA = '41dfe972c677db45a8cbd8086f2e9950ccc956c100709cdb88aa50ea6981904d'


def record(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def verify_bit_conversion(bit, binary):
    """Bootgen must only remove the .bit header and swap each 32-bit word."""
    if len(bit) < 4:
        raise ValueError('Truncated bit header')
    pos = 2 + struct.unpack_from('>H', bit)[0]
    if bit[pos:pos + 2] != b'\0\1':
        raise ValueError('Unexpected bit header marker')
    pos += 2
    for expected in b'abcde':
        if bit[pos:pos + 1] != bytes([expected]):
            raise ValueError('Unexpected bit header field')
        pos += 1
        width = 4 if expected == ord('e') else 2
        if pos + width > len(bit):
            raise ValueError('Truncated bit header length')
        length = int.from_bytes(bit[pos:pos + width], 'big')
        pos += width
        if pos + length > len(bit):
            raise ValueError('Truncated bit payload')
        if expected == ord('e'):
            if length == 0 or length % 4 or pos + length != len(bit):
                raise ValueError('Unexpected bit payload length/trailing bytes')
            raw = bit[pos:]
            for offset in range(4):
                if binary[offset::4] != raw[3-offset::4]:
                    raise ValueError('Bootgen binary differs from the word-swapped bit payload')
        pos += length


def reset_geometry(hdl, definitions, fabric_resets, overlays):
    """Join actual generated wiring to firmware IDs; reject generic reset guesses."""
    def uncomment(text):
        return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    pins = {int(value) for value in re.findall(
        r'assign\s+pl_resetn0\s*=\s*emio_gpio_o_temp\[(\d+)\]\s*;', uncomment(hdl))}
    if fabric_resets != 1 or len(pins) != 1:
        raise ValueError('Unsupported/ambiguous generated reset geometry')
    pin, = pins
    ids = re.findall(r'#define\s+PM_RESET_GPIO5_EMIO_' + str(pin) +
                     r'\s+\(PM_RESET_BASE\s*\+\s*(\d+)U?\)', uncomment(definitions))
    if len(ids) != 1:
        raise ValueError('Missing/ambiguous firmware reset mapping')
    reset_id = int(ids[0])
    if (pin, reset_id) != (95, 119):
        raise ValueError('Generated reset is not the supported EMIO95 / reset119')
    for name, source in overlays.items():
        actual = re.findall(r'resets\s*=\s*<\s*&zynqmp_reset\s+(\d+)\s*>\s*;', uncomment(source))
        if actual != [str(reset_id)]:
            raise ValueError('Overlay reset does not match generated wiring: ' + name)
    return {'fabric_resets': 1, 'port': 'pl_resetn0', 'emio_gpio': pin,
            'dt_reset_id': reset_id, 'firmware_constant': 'PM_RESET_GPIO5_EMIO_95',
            'evidence': 'Pinned generated HDL plus published installed firmware definitions; no physical pulse claim'}


def verify_inputs():
    for relative, wanted in PINS.items():
        if record(RUNTIME / relative)['sha256'] != wanted:
            raise ValueError('Trusted input changed: ' + relative)
    sample_root = RUNTIME / 'board-generation/mac-sampling-20261109'
    original = json.loads((sample_root / 'sampling-draws.json').read_text())
    draws = json.loads((sample_root / 'board-sampling-draws.json').read_text())
    if (draws != {'schema': 1, 'draws': {str(row['seed']): row['draws'] for row in original['seeds']}} or
            original['model_forward_calls'] != 0 or original['training_calls'] != 0 or
            original['selected_weights_changed'] is not False or
            set(draws['draws']) != {'47', '20001', '20002', '20003', '20087', '20128'} or
            any(len(row) != 32 or any(type(v) is not float or not 0 <= v < 1 for v in row)
                for row in draws['draws'].values())):
        raise ValueError('Pinned NumPy draw export/provenance mismatch')
    xci = next(path for path in PINS if path.endswith('.xci'))
    params = json.loads((RUNTIME / xci).read_text())['ip_inst']['parameters']['model_parameters']
    if [params[name][0]['value'] for name in ('C_MAXIGP0_DATA_WIDTH', 'C_MAXIGP1_DATA_WIDTH')] != ['32', '128']:
        raise ValueError('AFI overlay no longer matches the built PS interface widths')
    if record(RESET_DEFS)['sha256'] != RESET_DEFS_SHA:
        raise ValueError('Firmware reset definitions changed')
    hdl = next(path for path in PINS if path.endswith('/hdl/zynq_ultra_ps_e_v3_5_8.v'))
    reset = reset_geometry((RUNTIME / hdl).read_text(), RESET_DEFS.read_text(),
                           int(params['C_NUM_FABRIC_RESETS'][0]['value']),
                           {name: (TOOLS / name).read_text() for name in
                            ('kv260-program.dts', 'kv260-interface.dts')})
    base = RUNTIME / 'board-inspection/mac-ubuntu-24.04'
    for folder in ('original-json', 'live-support'):
        for item in json.loads((base / folder / 'transfer-manifest.json').read_text())['files']:
            if Path(item['name']).name != item['name']:
                raise ValueError('Manifest path escape')
            if record(base / folder / item['name']) != {k: item[k] for k in ('bytes', 'sha256')}:
                raise ValueError('Board capture changed: ' + item['name'])
    driver = json.loads((base / 'clock-afi-driver-check-20261109T132436Z.json').read_text())
    if driver['kernel_config'] != ['CONFIG_XILINX_FCLK=y', 'CONFIG_XILINX_AFI_FPGA=y'] or not all(
            driver['exact_driver_paths'][name] for name in ('xilinx_fclk', 'afi-fpga')):
        raise ValueError('Required clock/AFI drivers were not registered')
    return reset


def command(folder, name, args):
    log = folder / (name + '.log')
    with log.open('wb') as stream:
        process = subprocess.Popen([str(a) for a in args], cwd=folder,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=60)
        except BaseException as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise RuntimeError('60-second watchdog: ' + name) from exc
            raise
    if code:
        raise RuntimeError(name + ' failed; see ' + str(log))
    return log


def build():
    reset = verify_inputs()
    destination = RUNTIME / 'board-packages'
    destination.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='bos-', dir=destination))
    clang = AMD / 'tps/lnx64/clangd-8.0.0/bin/clang'
    linker = AMD / 'tps/llvm/7.0/lnx64/bin/ld.lld'
    objdump = AMD / 'tps/lnx64/clangd-8.0.0/bin/llvm-objdump'
    readelf = AMD / 'tps/lnx64/clangd-8.0.0/bin/llvm-readelf'
    dtc = AMD / 'Vivado/bin/dtc'
    overlay = AMD / 'gnu/riscv/linux_toolchain/lin64/x86_64-amdedfsdk-linux/usr/bin/fdtoverlay'
    fdtget = overlay.with_name('fdtget')
    bootgen = AMD / 'Vivado/bin/bootgen'
    executables = [clang, linker, objdump, readelf, dtc, overlay, fdtget, bootgen]
    # Only ISO function declarations; execution uses the board's normal libc.
    shim = folder / 'include'
    shim.mkdir()
    (shim / 'string.h').write_text('#include <stddef.h>\nvoid *memset(void *, int, size_t);\nvoid *memcpy(void *, const void *, size_t);\n')
    for source in ('host.c', 'board_bos.c'):
        command(folder, 'compile-' + source, [clang, '--target=aarch64-linux-gnu',
                '-std=c11', '-ffreestanding', '-nostdlibinc', '-fPIC', '-O2',
                '-Wall', '-Wextra', '-Werror', '-pedantic', '-I', shim, '-I', TOOLS,
                '-c', TOOLS / source, '-o', source + '.o'])
    command(folder, 'link', [linker, '-shared', '-z', 'noexecstack', '-z', 'relro',
                            '-z', 'now', 'host.c.o', 'board_bos.c.o', '-o', 'libboard_bos.so'])
    command(folder, 'arm-disassembly', [objdump, '-d', 'libboard_bos.so'])
    symbols = command(folder, 'arm-symbols', [readelf, '--dyn-symbols', 'libboard_bos.so']).read_text()
    undefined = {line.split()[-1] for line in symbols.splitlines()
                 if ' UND ' in line and len(line.split()) >= 8}
    if 'clock_gettime' not in undefined or not undefined <= {'clock_gettime', 'memcpy', 'memset'}:
        raise ValueError('Unexpected unresolved native ABI: ' + repr(undefined))
    # Compile warnings are fatal. Device-tree warnings remain in their logs;
    # overlays are also resolved against the actual captured live board tree.
    for stem in ('clock', 'program', 'interface'):
        source = TOOLS / ('kv260-' + stem + '.dts')
        shutil.copyfile(source, folder / source.name)
        command(folder, 'dtc-' + stem, [dtc, '-@', '-I', 'dts', '-O', 'dtb',
                                     '-o', 'kv260-' + stem + '.dtbo', source])
    live = RUNTIME / 'board-inspection/mac-ubuntu-24.04/live-support/live-device-tree.dtb'
    command(folder, 'overlay-resolve', [overlay, '-i', live, '-o', 'merged.dtb',
                                      'kv260-clock.dtbo', 'kv260-program.dtbo', 'kv260-interface.dtbo'])
    command(folder, 'merged-tree', [dtc, '-I', 'dtb', '-O', 'dts', 'merged.dtb'])
    checks = [('clock-rate', 'u', '/axi/tiny_transformer_clock', 'assigned-clock-rates', '50000000'),
              ('clock-input', 'x', '/axi/tiny_transformer_clock', 'clocks', '4 47'),
              ('firmware-name', 's', '/fpga-region', 'firmware-name', 'gradiated-tiny-50mhz.bit.bin'),
              ('afi-width', 'x', '/axi/tiny_transformer_afi', 'config-afi', 'e 800'),
              ('program-reset', 'x', '/fpga-region', 'resets', '11 77'),
              ('interface-reset', 'x', '/axi/tiny_transformer_afi', 'resets', '11 77'),
              ('interface-reg', 'x', '/axi/tiny-transformer@a0000000', 'reg', '0 a0000000 0 100'),
              ('interface-driver', 's', '/axi/tiny-transformer@a0000000', 'compatible', 'generic-uio')]
    for label, kind, node, prop, wanted in checks:
        actual = command(folder, 'merged-' + label, [fdtget, '-t', kind, 'merged.dtb', node, prop]).read_text().strip()
        if actual != wanted:
            raise ValueError('Resolved live-tree check failed: ' + label)
    original_bit = RUNTIME / 'vivado-prep/board-build-_4wbn4bx/offline-candidate.bit'
    shutil.copyfile(original_bit, folder / 'gradiated-tiny-50mhz.bit')
    (folder / 'payload.bif').write_text('all: { [destination_device=pl] gradiated-tiny-50mhz.bit }\n')
    command(folder, 'bootgen', [bootgen, '-arch', 'zynqmp', '-image', 'payload.bif',
                              '-process_bitstream', 'bin'])
    if not (folder / 'gradiated-tiny-50mhz.bit.bin').is_file():
        raise ValueError('Bootgen did not produce the expected firmware file')
    verify_bit_conversion(original_bit.read_bytes(), (folder / 'gradiated-tiny-50mhz.bit.bin').read_bytes())
    shutil.copyfile(RUNTIME / 'vivado-prep/pack-vp89u9_3/model-words.bin', folder / 'model-words.bin')
    goldens = json.loads((RUNTIME / 'rmsnorm-validation/whole-model-reference-20261104T101114Z/goldens.json').read_text())
    case, = [case for case in goldens['cases'] if case['name'] == 'BOS']
    if case['tokens'] != [256] or case['states']['logits']['shape'] != [1, 1, 320]:
        raise ValueError('Unexpected original BOS reference shape')
    (folder / 'bos-logits.json').write_text(json.dumps({'tokens': [256],
        'logits': case['states']['logits']['values'][0][0], 'original_goldens_sha256':
        PINS['rmsnorm-validation/whole-model-reference-20261104T101114Z/goldens.json']}, indent=2) + '\n')
    reference = {'schema': 1, 'original_goldens_sha256':
        PINS['rmsnorm-validation/whole-model-reference-20261104T101114Z/goldens.json'],
        'cases': [{'name': c['name'], 'tokens': c['tokens'],
                   'logits': c['states']['logits']['values'][0]} for c in goldens['cases']]}
    (folder / 'token-logits.json').write_text(json.dumps(reference, separators=(',', ':')) + '\n')
    shutil.copyfile(RUNTIME / 'board-generation/mac-sampling-20261109/board-sampling-draws.json',
                    folder / 'sampling-draws.json')
    shutil.copyfile(TOOLS / 'board_bos.py', folder / 'board_bos.py')
    payloads = ['board_bos.py', 'libboard_bos.so', 'model-words.bin', 'bos-logits.json',
                'gradiated-tiny-50mhz.bit.bin', 'kv260-clock.dtbo', 'kv260-program.dtbo', 'kv260-interface.dtbo',
                'token-logits.json', 'sampling-draws.json']
    manifest = {'schema': 1, 'candidate_only': True, 'board_execution_performed': False,
                'reset_geometry': reset, 'firmware_reset_definitions': {str(RESET_DEFS): record(RESET_DEFS)},
                'supersedes_manifest_sha256': '6d153993204d960ff857ad9d8b46ebe691061ebc095862101e44fa87edb1a14a',
                'inputs': PINS, 'sources': {name: record(TOOLS / name) for name in
                ('host.c', 'host.h', 'board_bos.c', 'board_bos.py', 'board_prepare.py',
                 'kv260-clock.dts', 'kv260-program.dts', 'kv260-interface.dts')},
                'tools': {str(path): record(path) for path in executables},
                'files': {name: record(folder / name) for name in payloads},
                'unverified_board_requirements': ['New native session lifecycle and multi-token scores on physical board',
                    'Every Arm-sampled decision requires the original pinned Mac NumPy audit'],
                'limits': 'Preparation performs no board actions. Batch Arm sampling remains provisional until every choice passes original Mac NumPy audit; streaming keeps sampling on Mac. No physical timing/energy evidence'}
    (folder / 'package.json').write_text(json.dumps(manifest, indent=2) + '\n')
    archive = folder.with_suffix('.tar.gz')
    with archive.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|') as tar:
                for name in sorted([*payloads, 'package.json']):
                    path = folder / name
                    info = tarfile.TarInfo(name)
                    info.size = path.stat().st_size
                    info.mode = 0o644
                    with path.open('rb') as stream:
                        tar.addfile(info, stream)
    return {'folder': str(folder), 'manifest': record(folder / 'package.json'),
            'archive': {'path': str(archive), **record(archive)},
            'candidate_only': True, 'board_execution_performed': False}


def conditioned_build(model_report,model_sha256,host_report,host_sha256,packed_report,packed_sha256):
    """Seal separately validated weights around the unchanged accepted circuit.

    No compiler or vendor executable is invoked. Reuse the verified native
    library and physical payloads; require fresh model/native/packing receipts.
    """
    import rtl
    import board_bos
    receipts={}
    for name,path,digest in (('model',model_report,model_sha256),('host',host_report,host_sha256),
                             ('packed',packed_report,packed_sha256)):
        path=Path(path).resolve()
        if not path.is_relative_to(RUNTIME.resolve()) or not digest or record(path)['sha256']!=digest:
            raise ValueError('Conditioned receipt location/hash differs: '+name)
        receipts[name]=(path,json.loads(path.read_text()))
    model=receipts['model'][1];block=model.get('blocks',{}).get('model-compare',{})
    if (model.get('state')!='complete' or model.get('mode')!='model-compare' or model.get('accepted') is not True or
            block.get('state')!='complete' or block.get('checks',{}).get('cases')!=7 or
            block['checks'].get('input_positions')!=522 or block['checks'].get('all_exact') is not True or
            block['reference'].get('transfer_sha256')!=rtl.CONDITIONED_TRANSFER_SHA256):
        raise ValueError('Conditioned package requires the complete accepted seven-case comparison')
    reference=Path(block['reference']['directory']).resolve()
    model_inputs=(reference/'fixed/arithmetic.json',block['reference']['model_pins']['conditioned_arithmetic'],
                  reference/'fixed/fixed-tensors.safetensors')
    cases,provenance=rtl.mac_conditioned_reference(reference,rtl.CONDITIONED_TRANSFER_SHA256,model_inputs)
    old_model=json.loads((RUNTIME/'vivado-prep/model-compare-2az1bnjc/results.json').read_text())['blocks']['model-compare']
    if block['source_sha256']!=old_model['source_sha256']:
        raise ValueError('Conditioned RTL differs from original accepted circuit sources')
    for name,digest in block['source_sha256'].items():
        if record(rtl.RTL/name)['sha256']!=digest:raise ValueError('Conditioned RTL source changed: '+name)
    for name,case in cases.items():
        result=block['cases'][name]
        if result.get('state')!='complete' or result['checks'].get('all_available_checks_exact') is not True or \
                result['checks']['independent_arithmetic'].get('all_exact') is not True:
            raise ValueError('Conditioned case acceptance differs: '+name)
        for filename,pin in result['artifacts'].items():
            if Path(filename).name!=filename or record(receipts['model'][0].parent/name/'transformer'/filename)!=pin:
                raise ValueError('Conditioned simulation artifact changed: '+name+'/'+filename)
    if any(sum(c['name']==name for c in model['commands'])!=7 for name in ('compile','elaborate','simulation')):
        raise ValueError('Conditioned simulation command coverage differs')
    host=receipts['host'][1];native=host.get('blocks',{}).get('host',{})
    if (host.get('state')!='complete' or host.get('mode')!='host' or native.get('state')!='complete' or
            native.get('checks')!={'mock_suites':6,'all_exact':True,'context_frames':256,'logit_values':81920,
                'compiler_warnings_fatal':True,'address_sanitizer':True,'undefined_behavior_sanitizer':True}):
        raise ValueError('Conditioned native transport validation differs')
    for report in (model,host):
        if any(c.get('exit_code')!=0 or c.get('timeout_seconds')!=180 or
                c.get('child_reaped') is not True or c.get('process_group_absent') is not True for c in report['commands']):
            raise ValueError('Conditioned validation watchdog/cleanup differs')
    for name,digest in native['source_sha256'].items():
        if record(Path(__file__).resolve().parents[1]/name)['sha256']!=digest:
            raise ValueError('Native transport source changed: '+name)
    packed=receipts['packed'][1];transport=packed.get('blocks',{}).get('model_package',{}).get('package',{})
    image=receipts['packed'][0].parent/'model-words.bin'
    if (packed.get('state')!='complete' or packed.get('mode')!='pack' or
            transport.get('fixed_manifest_sha256')!=model_inputs[1] or
            transport.get('fixed_tensor_image_sha256')!=provenance['model_pins']['payload'] or
            transport.get('packed_image',{}).get('words')!=29281 or record(image)!={
                'bytes':117124,'sha256':board_bos.CONDITIONED_MODEL_SHA}):
        raise ValueError('Conditioned packed weights identity differs')
    reset=verify_inputs()
    base=RUNTIME/'board-packages/text-bgjxdjep';base_manifest=base/'package.json'
    base_sha='bf40e0c470fd3af974f021c1e6f57583c7c8098b9cd35889513fe1a136984d9f'
    if record(base_manifest)['sha256']!=base_sha:raise ValueError('Original sealed package manifest differs')
    original=json.loads(base_manifest.read_text())
    for name,pin in original['files'].items():
        if Path(name).name!=name or record(base/name)!=pin:raise ValueError('Original sealed payload differs: '+name)
    for name in ('host.c','host.h','board_bos.c'):
        if record(TOOLS/name)!=original['sources'][name]:raise ValueError('Native source differs from accepted ARM library')
    folder=Path(tempfile.mkdtemp(prefix='conditioned-',dir=RUNTIME/'board-packages'))
    common=('libboard_bos.so',board_bos.FIRMWARE,'kv260-clock.dtbo','kv260-program.dtbo','kv260-interface.dtbo')
    for name in common:shutil.copyfile(base/name,folder/name)
    shutil.copyfile(TOOLS/'board_bos.py',folder/'board_bos.py')
    shutil.copyfile(image,folder/'model-words.bin')
    refs=dict(schema=1,model_profile=board_bos.CONDITIONED_PROFILE,
              original_goldens_sha256=rtl.CONDITIONED_TRANSFER_SHA256)
    (folder/'bos-logits.json').write_text(json.dumps(dict(refs,tokens=[256],logits=cases['BOS']['arrays'][0]['logits']))+'\n')
    (folder/'token-logits.json').write_text(json.dumps(dict(refs,cases=[
        dict(name=name,tokens=case['tokens'],logits=[a['logits'] for a in case['arrays']])
        for name,case in cases.items()]),separators=(',',':'))+'\n')
    receipt_pins={name:dict(path=str(path),**record(path)) for name,(path,_) in receipts.items()}
    acceptance=dict(schema=1,server_validation_complete=True,board_execution_performed=False,
        model_profile=board_bos.CONDITIONED_PROFILE,original_package_sha256=base_sha,
        source_transfer_sha256=rtl.CONDITIONED_TRANSFER_SHA256,rtl=block['checks'],native=native['checks'],
        numerical_gate=provenance['numerical_gate'],receipts=receipt_pins,
        reused_payloads={name:original['files'][name] for name in common},
        input_protocol=dict(encoding='hex',answer_marker=False,max_utf8_bytes=48,default_max_new_tokens=255,
                            decoding='first-index argmax over all 320 integer scores',fresh_session_per_request=True),
        limits='Finite teacher-forced RTL and host mock evidence; new weights require a later physical board test. Known empty/Unicode failures and repeats remain.')
    (folder/'acceptance.json').write_text(json.dumps(acceptance,indent=2)+'\n')
    payloads=[*common,'board_bos.py','model-words.bin','bos-logits.json','token-logits.json','acceptance.json']
    manifest=dict(schema=1,candidate_only=True,board_execution_performed=False,
        model_profile=board_bos.CONDITIONED_PROFILE,reset_geometry=reset,
        supersedes_manifest_sha256=base_sha,inputs=receipt_pins,
        sources={name:record(TOOLS/name) for name in ('host.c','host.h','board_bos.c','board_bos.py','board_prepare.py')},
        files={name:record(folder/name) for name in payloads},
        unverified_board_requirements=['New balanced weights, seven reference cases and conditioned generation on the physical KV260'],
        limits='Offline package only; original bitstream/native library/overlays retained. No physical board action or new timing/energy measurement.')
    (folder/'package.json').write_text(json.dumps(manifest,indent=2)+'\n')
    board_bos.checked_bundle(folder,with_profile=True)
    archive=folder.with_suffix('.tar.gz')
    with archive.open('xb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as tar:
                for name in sorted([*payloads,'package.json']):
                    info=tarfile.TarInfo(name);info.size=(folder/name).stat().st_size;info.mode=0o644
                    with (folder/name).open('rb') as stream:tar.addfile(info,stream)
    return dict(folder=str(folder),manifest=record(folder/'package.json'),archive=dict(path=str(archive),**record(archive)),
                model_image=record(folder/'model-words.bin'),reused_payloads=acceptance['reused_payloads'],
                server_validation_complete=True,board_execution_performed=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--conditioned',action='store_true',help='Reuse the original circuit after fresh seven-case numerical validation')
    for name in ('model','host','packed'):
        parser.add_argument('--'+name+'-report',type=Path)
        parser.add_argument('--'+name+'-report-sha256')
    args=parser.parse_args()
    inputs=(args.model_report,args.model_report_sha256,args.host_report,args.host_report_sha256,args.packed_report,args.packed_report_sha256)
    if args.conditioned and not all(inputs):parser.error('Conditioned preparation requires all three sealed validation reports')
    if not args.conditioned and any(inputs):parser.error('Validation report arguments require --conditioned')
    print(json.dumps(conditioned_build(*inputs) if args.conditioned else build(),indent=2))
