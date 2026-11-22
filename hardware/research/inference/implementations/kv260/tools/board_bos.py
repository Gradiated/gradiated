"""Inspect a KV260 package; opt-in supervised UIO BOS comparison, no programming.

Default invocation reads files/sysfs only. Device-writing modes explicitly
reset/reload, then score BOS or token sequences without retries. The native
library supplies single-width AArch64 MMIO with DSB barriers using host.c.
Software deadlines cannot rescue an unresponsive PS/PL hardware transaction.
"""
import argparse
from contextlib import ExitStack
import ctypes
import fcntl
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import platform
import stat
import struct
import subprocess
import sys

MODEL_SHA = '0198baeaeb48052895b5eb4f9622d61fb144295584e6823f8e42420fc0d73cf5'
UIO_NAME = 'gradiated-tiny-transformer-v1'
FIRMWARE = 'gradiated-tiny-50mhz.bit.bin'
OF_PATH = '/axi/tiny-transformer@a0000000'
RESET_ID = 119  # Generated pl_resetn0 -> EMIO95; firmware GPIO5_EMIO_95.
GOLDENS_SHA = '36ae1ebe2fa0bedd74c2cf872742e996b776349ba579742b7931928c0ea0f3e6'
CALL_BUDGET_NS = 30000000000
CONDITIONED_PROFILE = 'conditioned-hex-balanced-v1'
CONDITIONED_MODEL_SHA = '698df2e177b8e478088fffe9b02af09cd10c9ac0afbe252f3b031f133262e055'
CONDITIONED_REFERENCE_SHA = 'c0d3b73943ab580199cc7a4ceb0807c9a215e250d58c169fab016b019598a4fc'


def package_profile(manifest):
    """Pinned model/input/reference identity; no user-controlled codec selector."""
    name = manifest.get('model_profile', 'bos-byte-v1')
    cases = {'BOS': 1, 'J01-first16': 16, 'authored128': 128, 'repeated-J01-256': 256}
    if name == 'bos-byte-v1':
        return {'name': name, 'model_sha256': MODEL_SHA, 'reference_sha256': GOLDENS_SHA,
                'encoding': 'bytes', 'default_max_new_tokens': 128, 'cases': cases}
    if name == CONDITIONED_PROFILE:
        cases.update({'encoded-fu2p2q': 13, 'encoded-hello': 11, 'encoded-max48': 97})
        return {'name': name, 'model_sha256': CONDITIONED_MODEL_SHA,
                'reference_sha256': CONDITIONED_REFERENCE_SHA,
                'encoding': 'hex', 'default_max_new_tokens': 255, 'cases': cases}
    raise ValueError('Unknown model package profile')


def checked_bundle(folder, *, with_profile=False):
    folder = Path(folder)
    manifest = json.loads((folder / 'package.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('candidate_only') is not True:
        raise ValueError('Unexpected candidate manifest')
    profile = package_profile(manifest)
    required = {'model-words.bin', 'bos-logits.json', 'libboard_bos.so', 'board_bos.py'}
    if not required <= manifest['files'].keys():
        raise ValueError('Incomplete package')
    for name, record in manifest['files'].items():
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Manifest path escape')
        data = (folder / name).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Package integrity failure: ' + name)
    image = (folder / 'model-words.bin').read_bytes()
    if len(image) != 117124 or hashlib.sha256(image).hexdigest() != profile['model_sha256']:
        raise ValueError('Wrong selected model image')
    reference = json.loads((folder / 'bos-logits.json').read_text())
    values = reference['logits']
    if reference.get('tokens') != [256] or len(values) != 320 or any(
            type(v) is not int or not -(1 << 31) <= v < (1 << 31) for v in values):
        raise ValueError('Invalid original BOS reference')
    if profile['encoding'] == 'hex':
        if (reference.get('original_goldens_sha256') != profile['reference_sha256'] or
                reference.get('model_profile') != profile['name'] or 'token-logits.json' not in manifest['files']):
            raise ValueError('Conditioned model reference identity differs')
        refs = json.loads((folder / 'token-logits.json').read_text())
        if refs.get('model_profile') != profile['name']:
            raise ValueError('Conditioned token reference profile differs')
        reference_cases(folder)
    return (image, values, profile) if with_profile else (image, values)


def inspect_board(root=Path('/')):
    """No device open, mmap, subprocess or board-state write in this function."""
    root = Path(root)
    errors = []
    report = {'ready': False, 'errors': errors, 'uio': []}

    def read(path):
        try:
            return (root / path.lstrip('/')).read_text().strip()
        except OSError:
            return ''

    if read('/sys/class/fpga_manager/fpga0/state') != 'operating':
        errors.append('FPGA manager is not operating')
    try:
        flags = int(read('/sys/class/fpga_manager/fpga0/flags'), 16)
    except ValueError:
        errors.append('FPGA manager flags are missing or not hexadecimal')
    else:
        report['manager_flags'] = flags
        if flags != 0:
            errors.append('FPGA manager flags must be zero for firmware-file loading (found ' + hex(flags) + ')')
    firmware_path = root / 'sys/firmware/devicetree/base/fpga-region/firmware-name'
    try:
        firmware = firmware_path.read_bytes().rstrip(b'\0').decode()
    except OSError:
        firmware = ''
    if firmware != FIRMWARE:
        errors.append('Custom programming overlay is not present')
    try:
        reset_root = root / 'sys/firmware/devicetree/base/firmware/zynqmp-firmware/reset-controller'
        phandle, = struct.unpack('>I', (reset_root / 'phandle').read_bytes())
        cells, = struct.unpack('>I', (reset_root / '#reset-cells').read_bytes())
        if not phandle or cells != 1 or (reset_root / 'compatible').read_bytes() != b'xlnx,zynqmp-reset\0':
            raise ValueError('Unexpected reset controller')
        for node in ('fpga-region', 'axi/tiny_transformer_afi'):
            data = (root / 'sys/firmware/devicetree/base' / node / 'resets').read_bytes()
            if struct.unpack('>II', data) != (phandle, RESET_ID):
                raise ValueError('Reset line differs from generated pl_resetn0 / EMIO95: ' + node)
        report['reset'] = {'dt_reset_id': RESET_ID, 'generated_gpio': 'EMIO95',
                           'source': 'live DT metadata; not a physical pulse measurement'}
    except (OSError, ValueError, struct.error) as exc:
        errors.append('Reset gate: ' + str(exc))
    report['registered_drivers'] = {}
    for driver in ('xilinx_fclk', 'afi-fpga', 'uio_pdrv_genirq'):
        available = (root / 'sys/bus/platform/drivers' / driver).is_dir()
        report['registered_drivers'][driver] = available
        if not available:
            errors.append('Required registered driver missing: ' + driver)
    for driver, node_name in (('xilinx_fclk', 'tiny_transformer_clock'),
                              ('afi-fpga', 'tiny_transformer_afi')):
        expected = root / 'sys/firmware/devicetree/base/axi' / node_name
        matches = [entry for entry in (root / 'sys/bus/platform/drivers' / driver).glob('*')
                   if (entry / 'of_node').exists() and
                   (entry / 'of_node').resolve() == expected.resolve()]
        if len(matches) != 1:
            errors.append('Candidate device is not bound to ' + driver)
    try:
        rows = [line.split() for line in (root / 'sys/kernel/debug/clk/clk_summary').read_text().splitlines()]
        rows = [row for row in rows if row and row[0] == 'pl0_ref']
        if len(rows) != 1:
            raise ValueError('Expected one pl0_ref clock')
        row = rows[0]
        # Linux 6.8 summary: name, enable, prepare, protect, rate, accuracy,
        # phase, duty, hardware-enable. Refuse ambiguous/missing data.
        rate = int(row[4])
        if not (1 <= int(row[1]) and 1 <= int(row[2]) and
                40000000 <= rate <= 50000000 and row[8] == 'Y'):
            raise ValueError('PL0 is not enabled at a supported <=50 MHz rate')
        report['clock'] = {'rate_hz': rate, 'source': 'kernel clk_summary'}
    except (OSError, IndexError, ValueError) as exc:
        errors.append('Clock gate: ' + str(exc))
    candidates = []
    base = root / 'sys/class/uio'
    for node in sorted(base.glob('uio*')):
        if not node.name[3:].isdigit():
            continue
        name = read(str(node.relative_to(root) / 'name'))
        if name != UIO_NAME:
            continue
        try:
            address = int((node / 'maps/map0/addr').read_text(), 0)
            size = int((node / 'maps/map0/size').read_text(), 0)
            offset = int((node / 'maps/map0/offset').read_text(), 0)
            ofnode = (node / 'device/of_node').resolve(strict=True)
            expected = (root / ('sys/firmware/devicetree/base' + OF_PATH)).resolve(strict=True)
            reg = struct.unpack('>IIII', (ofnode / 'reg').read_bytes())
            driver = (node / 'device/driver').resolve(strict=True).name
            device = root / 'dev' / node.name
            mode = device.stat().st_mode
            if (address != 0xa0000000 or size != mmap.PAGESIZE or offset != 0 or
                    ofnode != expected or reg != (0, 0xa0000000, 0, 0x100) or
                    driver != 'uio_pdrv_genirq' or not stat.S_ISCHR(mode)):
                raise ValueError('Unexpected map/DT/driver/device identity')
            candidates.append(str(device))
            report['uio'].append({'device': str(device), 'base': address, 'map_bytes': size})
        except (OSError, ValueError, struct.error) as exc:
            errors.append(node.name + ': ' + str(exc))
    if len(candidates) != 1:
        errors.append('Expected exactly one dedicated transformer UIO device')
    report['ready'] = not errors
    return report


def run_bos(folder):
    folder = Path(folder).resolve()
    image, reference = checked_bundle(folder)
    if platform.machine() != 'aarch64' or sys.byteorder != 'little':
        raise ValueError('Only little-endian Linux AArch64 is supported')
    report = inspect_board()
    if not report['ready']:
        raise ValueError(json.dumps(report))
    manifest = json.loads((folder / 'package.json').read_text())
    firmware = (Path('/lib/firmware') / FIRMWARE).read_bytes()
    wanted = manifest['files'][FIRMWARE]
    if len(firmware) != wanted['bytes'] or hashlib.sha256(firmware).hexdigest() != wanted['sha256']:
        raise ValueError('Installed candidate firmware file differs from the package')
    lib = ctypes.CDLL(str(folder / 'libboard_bos.so'))
    function = lib.board_bos
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                         ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    function.restype = ctypes.c_int
    payload = ctypes.create_string_buffer(image)
    logits = (ctypes.c_int32 * 320)()
    counters = (ctypes.c_uint32 * 5)()
    fd = os.open(report['uio'][0]['device'], os.O_RDWR | os.O_CLOEXEC)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with mmap.mmap(fd, mmap.PAGESIZE, flags=mmap.MAP_SHARED,
                       prot=mmap.PROT_READ | mmap.PROT_WRITE) as memory:
            anchor = ctypes.c_uint32.from_buffer(memory)
            try:
                rc = function(ctypes.addressof(anchor), payload, len(image), 1,
                              30000000000, logits, counters)
            finally:
                del anchor
    finally:
        os.close(fd)
    values = list(logits)
    mismatches = [i for i, (a, b) in enumerate(zip(values, reference)) if a != b]
    accepted = rc == 0 and list(counters) == [0, 29281, 320, 1, 0] and not mismatches
    return {'accepted': accepted, 'api_result': rc, 'counters': list(counters),
            'logits': values if rc == 0 else None, 'mismatch_indices': mismatches if rc == 0 else None,
            'reference': 'Original Mac fixed-point BOS; exact 320 signed32 scores',
            'clock': report['clock'], 'sampling_performed': False}


class NativeSession:
    """One explicit reset/full load, ordered token calls, explicit context clear.

    Closing releases only userspace resources, never resets or reprograms PL.
    Every native call gets its own 30-second deadline; main owns the independent
    absolute child watchdog, including time spent waiting for external input.
    """
    def __init__(self, folder):
        folder = Path(folder).resolve()
        image, _ = checked_bundle(folder)
        if platform.machine() != 'aarch64' or sys.byteorder != 'little':
            raise ValueError('Only little-endian Linux AArch64 is supported')
        self.report = inspect_board()
        if not self.report['ready']:
            raise ValueError(json.dumps(self.report))
        manifest = json.loads((folder / 'package.json').read_text())
        firmware = (Path('/lib/firmware') / FIRMWARE).read_bytes()
        wanted = manifest['files'][FIRMWARE]
        if len(firmware) != wanted['bytes'] or hashlib.sha256(firmware).hexdigest() != wanted['sha256']:
            raise ValueError('Installed candidate firmware file differs from the package')
        self.lib = ctypes.CDLL(str(folder / 'libboard_bos.so'))
        signatures = {
            'board_session_bytes': (ctypes.c_size_t, []),
            'board_session_begin': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_size_t,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                ctypes.c_uint64, ctypes.c_void_p]),
            'board_session_step': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_size_t,
                ctypes.c_uint16, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]),
            'board_session_clear': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_size_t,
                ctypes.c_uint64, ctypes.c_void_p]),
        }
        for name, (restype, argtypes) in signatures.items():
            try:
                function = getattr(self.lib, name)
            except AttributeError as exc:
                raise ValueError('Native session ABI missing: ' + name) from exc
            function.restype, function.argtypes = restype, argtypes
        self.storage_bytes = self.lib.board_session_bytes()
        if not 0 < self.storage_bytes <= 4096:
            raise ValueError('Unexpected native session size')
        self.storage = (ctypes.c_uint64 * ((self.storage_bytes + 7) // 8))()
        self.payload = ctypes.create_string_buffer(image)
        self.context_count = 0
        self.failed = False
        self.resources = ExitStack()
        try:
            fd = os.open(self.report['uio'][0]['device'], os.O_RDWR | os.O_CLOEXEC)
            self.resources.callback(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            memory = self.resources.enter_context(mmap.mmap(fd, mmap.PAGESIZE,
                flags=mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE))
            self.anchor = ctypes.c_uint32.from_buffer(memory)
            self.resources.callback(setattr, self, 'anchor', None)
            counters = (ctypes.c_uint32 * 5)()
            rc = self.lib.board_session_begin(self.storage, self.storage_bytes,
                ctypes.addressof(self.anchor), self.payload, len(image), 1,
                CALL_BUDGET_NS, counters)
            self.check(rc, counters, 0, 0, 'begin/reset/full-load')
        except BaseException:
            self.resources.close()
            raise

    def check(self, rc, counters, count, logits, operation):
        if rc != 0 or list(counters) != [0, 29281, logits, count, 0]:
            self.failed = True
            raise RuntimeError(json.dumps({'operation': operation, 'api_result': rc,
                                           'counters': list(counters)}))
        self.context_count = count

    def step(self, token):
        if self.failed:
            raise RuntimeError('Session has failed; no retry or recovery is permitted')
        if type(token) is not int or not 0 <= token < 320:
            raise ValueError('Token must be an integer in 0..319')
        if self.context_count >= 256:
            raise ValueError('Context is full; explicit clear is required')
        if self.context_count == 0 and token != 256:
            raise ValueError('BOS 256 is required after begin or explicit clear')
        values = (ctypes.c_int32 * 320)()
        counters = (ctypes.c_uint32 * 5)()
        rc = self.lib.board_session_step(self.storage, self.storage_bytes, token,
                                         CALL_BUDGET_NS, values, counters)
        self.check(rc, counters, self.context_count + 1, 320, 'step')
        return {'api_result': rc, 'counters': list(counters),
                'context_count': self.context_count, 'logits': list(values)}

    def clear(self):
        if self.failed:
            raise RuntimeError('Session has failed; no retry or recovery is permitted')
        counters = (ctypes.c_uint32 * 5)()
        rc = self.lib.board_session_clear(self.storage, self.storage_bytes,
                                          CALL_BUDGET_NS, counters)
        self.check(rc, counters, 0, 0, 'explicit-context-clear')
        return {'context_count': 0, 'counters': list(counters)}

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.resources.close()


def reference_cases(folder):
    reference = json.loads((Path(folder) / 'token-logits.json').read_text())
    profile = package_profile(reference)
    if reference.get('schema') != 1 or reference.get('original_goldens_sha256') != profile['reference_sha256']:
        raise ValueError('Wrong original token reference')
    cases = reference['cases']
    expected = profile['cases']
    if [case['name'] for case in cases] != list(expected):
        raise ValueError('Unexpected reference cases/order')
    for case in cases:
        tokens, scores = case['tokens'], case['logits']
        if (len(tokens) != expected[case['name']] or tokens[0] != 256 or
                any(type(t) is not int or not 0 <= t < 320 for t in tokens) or
                len(scores) != len(tokens) or any(len(row) != 320 or any(
                    type(v) is not int or not -(1 << 31) <= v < (1 << 31) for v in row) for row in scores)):
            raise ValueError('Invalid token/reference geometry')
    return cases


def run_validation(folder, name):
    cases = reference_cases(folder)
    selected = cases if name == 'all' else [case for case in cases if case['name'] == name]
    if not selected:
        raise ValueError('Unknown validation case')
    results = []
    with NativeSession(folder) as session:
        for index, case in enumerate(selected):
            if index:
                session.clear()
            digest = hashlib.sha256()
            for position, (token, expected) in enumerate(zip(case['tokens'], case['logits'])):
                frame = session.step(token)
                actual = frame['logits']
                if actual != expected:
                    raise RuntimeError(json.dumps({'case': case['name'], 'position': position,
                        'token': token, 'actual': actual, 'expected': expected,
                        'completed_cases': results, 'frame': frame}))
                digest.update(struct.pack('<320i', *actual))
            results.append({'case': case['name'], 'tokens_checked': len(case['tokens']),
                'logit_values_checked': 320 * len(case['tokens']),
                'context_count': session.context_count, 'logits_sha256': digest.hexdigest()})
    return {'accepted': True, 'cases': results, 'explicit_context_clears': len(selected) - 1,
            'sampling_performed': False, 'reference': 'Original frozen Mac signed32 scores'}


def run_stream(folder, incoming=None, outgoing=None):
    """JSON lines only. The external Mac owns all sampling, EOS and byte decoding."""
    incoming = sys.stdin if incoming is None else incoming
    outgoing = sys.stdout if outgoing is None else outgoing

    def emit(value):
        print(json.dumps(value, sort_keys=True), file=outgoing, flush=True)

    with NativeSession(folder) as session:
        emit({'event': 'ready', 'protocol': 'fpga-logits-v1', 'context_count': 0,
              'model_words_loaded': 29281, 'call_budget_seconds': 30,
              'sampling_performed': False})
        for expected_id in range(1024):
            line = incoming.readline(4097)
            if not line or len(line) > 4096 or not line.endswith('\n'):
                raise ValueError('Missing, oversized or unterminated stream request')
            request = json.loads(line)
            if (type(request) is not dict or type(request.get('id')) is not int or
                    request['id'] != expected_id):
                raise ValueError('Stream request ID must increase from zero without repeats')
            op = request.get('op')
            fields = {'id', 'op', 'token'} if op == 'step' else {'id', 'op'}
            if set(request) != fields:
                raise ValueError('Unexpected stream request fields')
            response = {'id': expected_id, 'op': op, 'accepted': True}
            if op == 'step':
                frame = session.step(request['token'])
                response.update(frame, input_token=request['token'], logit_exponent=-16,
                    logits_sha256=hashlib.sha256(struct.pack('<320i', *frame['logits'])).hexdigest())
            elif op == 'clear':
                response.update(session.clear())
            elif op == 'close':
                response.update(closed=True, context_count=session.context_count)
                emit(response)
                return 0
            else:
                raise ValueError('Unknown stream operation')
            emit(response)
    raise ValueError('Stream request limit reached without explicit close')


def uniform_draws(folder, seed):
    data = json.loads((Path(folder) / 'sampling-draws.json').read_text())
    if data.get('schema') != 1 or str(seed) not in data['draws']:
        raise ValueError('Seed missing from pinned Mac uniform draws')
    draws = data['draws'][str(seed)]
    if len(draws) != 32 or any(type(v) not in (int, float) or not math.isfinite(v) or
                              not 0 <= v < 1 for v in draws):
        raise ValueError('Expected exactly 32 finite uniforms in [0,1)')
    return draws


def sample_logits(values, position, uniform):
    """Provisional stdlib FP64. Mac must audit every actual choice with NumPy.

    exp/reduction can round differently; no bitwise probability-equivalence
    claim, resampling or replacement of a failed audit is permitted.
    """
    if len(values) != 320 or any(type(v) is not int or not -(1 << 31) <= v < (1 << 31) for v in values):
        raise ValueError('Expected all 320 signed32 FPGA scores')
    if position >= 32:
        return max(range(320), key=values.__getitem__)
    if type(uniform) not in (int, float) or not math.isfinite(uniform) or not 0 <= uniform < 1:
        raise ValueError('Invalid uniform draw')
    logits = [v / 65536 / .8 for v in values]
    peak = max(logits)
    weights = [math.exp(v - peak) for v in logits]
    total = sum(weights)
    cumulative = 0.0
    for token, weight in enumerate(weights):
        cumulative += weight / total
        if uniform < cumulative:  # searchsorted(side='right')
            return token
    return 319


def run_generation(folder, seed):
    draws = uniform_draws(folder, seed)
    frames, tokens = [], []
    eos = False
    token = 256
    with NativeSession(folder) as session:
        for position in range(255):
            frame = session.step(token)
            draw = draws[position] if position < 32 else None
            chosen = sample_logits(frame['logits'], position, draw)
            frame.update(position=position, input_token=token, uniform_draw=draw, chosen_token=chosen,
                logits_sha256=hashlib.sha256(struct.pack('<320i', *frame['logits'])).hexdigest())
            frames.append(frame)
            if chosen == 257:
                eos = True
                break
            tokens.append(chosen)
            token = chosen
    try:
        text = bytes(tokens).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        text = None
    return {'hardware_accepted': True, 'sampling_verified': False,
            'requires_mac_numpy_audit': True, 'seed': seed, 'tokens': tokens,
            'eos': eos, 'text': text, 'valid_utf8_bytes': text is not None,
            'uniform_draws': draws, 'frames': frames,
            'recipe': {'name': 'prefix32', 'temperature': .8, 'sample_bytes': 32},
            'model_input_tokens': [256], 'output_constraints': False,
            'sampling_location': 'Arm stdlib FP64; original pinned Mac NumPy uniforms',
            'limits': 'Provisional until every decision passes original Mac NumPy audit; no retry/fallback'}


def completion_prefix(text, max_new_tokens, *, encoding='bytes'):
    """Validate byte geometry before any child or hardware session is started."""
    if type(text) is not str:
        raise ValueError('Text must be a Unicode string')
    if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 255:
        raise ValueError('max-new-tokens must be in 1..255')
    if encoding not in ('bytes', 'hex'):
        raise ValueError('Unknown input encoding')
    encoded = text.encode('utf-8')
    limit = 48 if encoding == 'hex' else 255
    if len(encoded) > limit:
        raise ValueError('Text exceeds ' + str(limit) + ' UTF-8 bytes; nothing was truncated')
    if encoding == 'hex':
        return encoded, [256, *[t for b in encoded for t in (272 + (b >> 4), 288 + (b & 15))]]
    return encoded, [256, *encoded]


def run_completion(folder, text, max_new_tokens=128, *, encoding='bytes'):
    """Condition on every actual UTF-8 byte, then greedily continue in PL.

    Legacy byte prefixes feed back the final byte at an output cap. The pending
    conditioned-model hex path matches the Mac decoder: the last output byte
    within the request/context budget is retained without another scoring call.
    The verified model package binds the input format; there is no CLI selector.
    EOS and non-byte tokens stop before feedback. No vocabulary mask or repair.
    """
    encoded, prefix = completion_prefix(text, max_new_tokens, encoding=encoding)
    frames, generated, decisions = [], [], []
    eos = False
    stop_reason = 'max_new_tokens'
    output_budget = max_new_tokens
    if encoding == 'hex' and 256 - len(prefix) <= max_new_tokens:
        output_budget = 256 - len(prefix)
        stop_reason = 'context_limit'
    with NativeSession(folder) as session:
        def score(token, phase):
            frame = session.step(token)
            frame.update(frame_index=len(frames), phase=phase, input_token=token,
                         logits_sha256=hashlib.sha256(struct.pack('<320i', *frame['logits'])).hexdigest())
            frames.append(frame)
            return frame

        for token in prefix:
            last = score(token, 'prefix')
        for index in range(output_budget):
            if session.context_count >= 256:
                stop_reason = 'context_limit'
                break
            chosen = max(range(320), key=last['logits'].__getitem__)
            decisions.append({'frame_index': last['frame_index'], 'token': chosen})
            if chosen == 257:
                eos = True
                stop_reason = 'eos'
                break
            generated.append(chosen)
            if chosen > 255:
                stop_reason = 'non_byte_token'
                break
            if encoding == 'hex' and index + 1 == output_budget:
                break
            last = score(chosen, 'generation')
        count = session.context_count
    byte_prefix = []
    for token in generated:
        if token > 255:
            break
        byte_prefix.append(token)
    raw = bytes(byte_prefix)
    continuation = None
    if len(byte_prefix) == len(generated):
        try:
            continuation = raw.decode('utf-8')
        except UnicodeDecodeError:
            pass
    return {'hardware_accepted': True, 'mode': 'text-completion',
            'decoding': 'greedy first-index argmax over all 320 integer scores',
            'logit_exponent': -16,
            'input_encoding': encoding, 'answer_marker': False,
            'prefix_text': text, 'prefix_utf8_hex': encoded.hex(), 'prefix_tokens': prefix,
            'input_tokens': [f['input_token'] for f in frames], 'generated_tokens': generated,
            'continuation_text': continuation, 'valid_utf8_bytes': continuation is not None,
            'continuation_bytes_hex': raw.hex() if len(byte_prefix) == len(generated) else None,
            'byte_prefix_hex': raw.hex(), 'eos': eos, 'stop_reason': stop_reason,
            'max_new_tokens': max_new_tokens, 'context_limit': 256, 'context_count': count,
            'frames': frames, 'decisions': decisions, 'conversation_history': False,
            'sampling_performed': False, 'neural_calculation_location': 'FPGA programmable logic'}


def completion_request(folder, text, max_new_tokens=128, *, encoding='bytes'):
    """Parent transports exact text in JSON stdin; a fresh child owns all MMIO."""
    completion_prefix(text, max_new_tokens, encoding=encoding)
    completed = subprocess.run([sys.executable, '-I', '-B', __file__, '--bundle',
        str(Path(folder).resolve()), '--complete=', '--max-new-tokens', str(max_new_tokens),
        '--child'], input=json.dumps({'text': text}), capture_output=True, text=True, timeout=180)
    if completed.returncode:
        raise RuntimeError('Completion child failed: ' + completed.stdout + completed.stderr)
    try:
        result = json.loads(completed.stdout)
        if type(result) is not dict or result.get('hardware_accepted') is not True:
            raise ValueError('Missing accepted hardware completion')
        if encoding == 'hex' and result.get('input_encoding') != 'hex':
            raise ValueError('Completion child used the wrong input encoding')
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Invalid completion child result: ' + completed.stdout) from exc
    return result


def run_interactive(folder, max_new_tokens=128, incoming=None, outgoing=None, *, encoding='bytes'):
    """Human line input waits in the parent; each request gets a fresh child."""
    completion_prefix('', max_new_tokens, encoding=encoding)
    incoming = sys.stdin if incoming is None else incoming
    outgoing = sys.stdout if outgoing is None else outgoing
    limit = 48 if encoding == 'hex' else 255
    max_line = 257 if encoding == 'bytes' else 50
    print('Type text; Ctrl-D exits. Each line starts fresh, with no history.\n'
          'This model learned 48 jokes; arbitrary prefixes may produce gibberish.',
          file=outgoing, flush=True)
    while True:
        print('Text> ', end='', file=outgoing, flush=True)
        try:
            line = incoming.readline(max_line)
            if not line:
                print(file=outgoing, flush=True)
                return 0
            if len(line) == max_line and not line.endswith('\n'):
                while line and not line.endswith('\n'):
                    line = incoming.readline(4096)
                print('Error: text exceeds ' + str(limit) + ' UTF-8 bytes.', file=outgoing, flush=True)
                continue
            text = line[:-1] if line.endswith('\n') else line
            if line.endswith('\r\n'):
                text = text[:-1]
            try:
                result = completion_request(folder, text, max_new_tokens, encoding=encoding)
            except ValueError as exc:  # Rejected user input, before child/MMIO.
                print('Error: ' + str(exc), file=outgoing, flush=True)
                continue
            if result['valid_utf8_bytes']:
                shown = ''.join(c if c.isprintable() or c in '\n\t' else ascii(c)[1:-1]
                                for c in result['continuation_text'])
                print(shown if shown else '(no continuation)', file=outgoing, flush=True)
            else:
                reason = ('non-byte token selected' if result['stop_reason'] == 'non_byte_token'
                          else 'generated bytes are not valid UTF-8')
                print('Stopped: ' + reason + '. Token IDs: ' + str(result['generated_tokens']) +
                      '; byte prefix (hex): ' + result['byte_prefix_hex'], file=outgoing, flush=True)
            if result['stop_reason'] in ('context_limit', 'max_new_tokens'):
                print('Stopped: ' + result['stop_reason'].replace('_', ' ') + '.', file=outgoing, flush=True)
        except (OSError, RuntimeError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            print('Request failed; stopping: ' + str(exc), file=outgoing, flush=True)
            return 1
        except KeyboardInterrupt:
            print(file=outgoing, flush=True)
            return 130


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run-bos', action='store_true', help='WRITES model registers; opt-in only')
    modes.add_argument('--validate', choices=('BOS', 'J01-first16', 'authored128', 'repeated-J01-256',
                                           'encoded-fu2p2q', 'encoded-hello', 'encoded-max48', 'all'),
                       help='WRITES model registers; exact teacher-forced comparison')
    modes.add_argument('--stream', action='store_true',
                       help='WRITES model registers; JSON token requests, raw scores, external sampling')
    modes.add_argument('--generate', type=int, metavar='SEED',
                       help='WRITES model registers; sealed Mac draws, provisional Arm sampler')
    modes.add_argument('--complete', metavar='TEXT',
                       help='Continue actual UTF-8 text greedily on the FPGA; emits machine JSON')
    modes.add_argument('--interactive', action='store_true',
                       help='Continue each entered line as a fresh text request')
    parser.add_argument('--max-new-tokens', type=int,
                        help='Text continuation length, 1..255; default 128 for legacy, 255 for conditioned model')
    parser.add_argument('--watchdog-seconds', type=int, default=180,
                        help='Existing session timeout, 1..600 seconds; text requests use fixed 180 seconds')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        _, _, profile = checked_bundle(args.bundle, with_profile=True)
        max_new_tokens = (profile['default_max_new_tokens'] if args.max_new_tokens is None else args.max_new_tokens)
        if args.generate is not None and profile['encoding'] == 'hex':
            raise ValueError('Conditioned model uses greedy decoding; seeded generation is unavailable')
        extended = args.validate is not None or args.stream or args.generate is not None
        if not 1 <= args.watchdog_seconds <= 600:
            raise ValueError('Watchdog must be 1..600 seconds')
        if (args.complete is not None or args.interactive) and args.watchdog_seconds != 180:
            raise ValueError('Text requests use a fixed 180-second child watchdog')
        if args.interactive:
            if args.child:
                raise ValueError('Interactive input must stay in the parent process')
            return run_interactive(args.bundle, max_new_tokens, encoding=profile['encoding'])
        elif args.complete is not None:
            if args.child:
                packet = sys.stdin.read(8193)
                if len(packet) > 8192:
                    raise ValueError('Oversized completion request envelope')
                request = json.loads(packet)
                if type(request) is not dict or set(request) != {'text'}:
                    raise ValueError('Unexpected completion request envelope')
                result = run_completion(args.bundle, request['text'], max_new_tokens, encoding=profile['encoding'])
            else:
                result = completion_request(args.bundle, args.complete, max_new_tokens, encoding=profile['encoding'])
        elif args.child:
            if args.validate is not None:
                result = run_validation(args.bundle, args.validate)
            elif args.stream:
                return run_stream(args.bundle)
            elif args.generate is not None:
                result = run_generation(args.bundle, args.generate)
            elif args.run_bos:
                result = run_bos(args.bundle)
            else:
                raise ValueError('Child execution requires an explicit device-writing mode')
        elif extended:
            mode = (['--validate', args.validate] if args.validate is not None else
                    ['--stream'] if args.stream else ['--generate', str(args.generate)])
            if args.stream:
                # Inherit stdin/stdout for one live broker, while wait's timeout
                # bounds the entire child lifetime, including idle input time.
                return subprocess.run([sys.executable, '-I', '-B', __file__, '--bundle',
                    str(args.bundle.resolve()), *mode, '--child'], timeout=args.watchdog_seconds).returncode
            completed = subprocess.run([sys.executable, '-I', '-B', __file__, '--bundle',
                str(args.bundle.resolve()), *mode, '--child'], capture_output=True,
                text=True, timeout=args.watchdog_seconds)
            if completed.returncode:
                raise RuntimeError('Session child failed: ' + completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
        elif args.run_bos:
            # No signal handler can guarantee interruption of a hung device bus.
            # This supervises ordinary userspace failures, not hardware recovery.
            completed = subprocess.run([sys.executable, '-I', '-B', __file__, '--bundle',
                                        str(args.bundle.resolve()), '--run-bos', '--child'],
                                       capture_output=True, text=True, timeout=40)
            if completed.returncode:
                raise RuntimeError('BOS child failed: ' + completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
        else:
            result = inspect_board()
        result['model_profile'] = profile['name']
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('accepted', result.get('hardware_accepted', result.get('ready'))) else 1
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'accepted': False, 'error': str(exc)}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
