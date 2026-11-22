"""Offline package/preflight rejection tests. Never opens a hardware device."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import board_bos
import board_prepare


class BitConversion(unittest.TestCase):
    def test_exact_payload_conversion_and_corruption_rejection(self):
        bit = b'\0\x09' + b'header123' + b'\0\1'
        for tag in b'abcd':
            bit += bytes([tag]) + b'\0\x02' + b'x\0'
        raw = bytes(range(32))
        bit += b'e' + struct.pack('>I', len(raw)) + raw
        converted = b''.join(raw[i:i+4][::-1] for i in range(0, len(raw), 4))
        board_prepare.verify_bit_conversion(bit, converted)
        for bad_bit, bad_binary in ((bit[:-1], converted), (bit+b'x', converted),
                                    (bit, raw), (bit, converted[:-1]),
                                    (bit, converted+b'x')):
            with self.assertRaises(ValueError):
                board_prepare.verify_bit_conversion(bad_bit, bad_binary)


class ResetGeometry(unittest.TestCase):
    def test_generated_connection_selects_firmware_id_and_rejects_wrong_overlay(self):
        hdl = 'if (C_NUM_FABRIC_RESETS == 1) begin assign pl_resetn0 = emio_gpio_o_temp[95]; end'
        definitions = '#define PM_RESET_GPIO5_EMIO_92 (PM_RESET_BASE + 116U)\n' \
                      '#define PM_RESET_GPIO5_EMIO_95 (PM_RESET_BASE + 119U)\n'
        names = ('kv260-program.dts', 'kv260-interface.dts')
        overlays = {name: (board_prepare.TOOLS / name).read_text() for name in names}
        result = board_prepare.reset_geometry(hdl, definitions, 1, overlays)
        self.assertEqual((result['emio_gpio'], result['dt_reset_id']), (95, 119))
        for name in names:
            changed = dict(overlays)
            changed[name] = changed[name].replace('zynqmp_reset 119', 'zynqmp_reset 116')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                board_prepare.reset_geometry(hdl, definitions, 1, changed)
        for changed_hdl, changed_defs, count in (
                (hdl.replace('[95]', '[92]'), definitions, 1),
                (hdl, definitions.replace('119U', '116U'), 1),
                (hdl, definitions, 2), (hdl + 'assign pl_resetn0 = emio_gpio_o_temp[92];', definitions, 1)):
            with self.assertRaises(ValueError):
                board_prepare.reset_geometry(changed_hdl, changed_defs, count, overlays)


class BoardPackage(unittest.TestCase):
    def bundle(self, root):
        data = b'\0' * 117124
        files = {'model-words.bin': data, 'libboard_bos.so': b'offline fixture only',
                 'board_bos.py': b'offline fixture only',
                 'bos-logits.json': json.dumps({'tokens': [256], 'logits': [0] * 320}).encode()}
        manifest = {'schema': 1, 'candidate_only': True, 'files': {}}
        for name, value in files.items():
            (root / name).write_bytes(value)
            manifest['files'][name] = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
        (root / 'package.json').write_text(json.dumps(manifest))
        return hashlib.sha256(data).hexdigest()

    def test_verified_package_and_modified_weight_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            digest = self.bundle(root)
            with patch.object(board_bos, 'MODEL_SHA', digest):
                image, scores = board_bos.checked_bundle(root)
                self.assertEqual((len(image), len(scores)), (117124, 320))
                (root / 'model-words.bin').write_bytes(image[:-1] + b'\1')
                with self.assertRaisesRegex(ValueError, 'integrity'):
                    board_bos.checked_bundle(root)

    def test_reference_range_and_geometry_rejection(self):
        for values in ([0] * 319, [0] * 319 + [1 << 31], [0] * 319 + [True]):
            with self.subTest(values=values[-1]):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp).resolve()
                    digest = self.bundle(root)
                    path = root / 'bos-logits.json'
                    path.write_text(json.dumps({'tokens': [256], 'logits': values}))
                    manifest = json.loads((root / 'package.json').read_text())
                    manifest['files'][path.name] = {'bytes': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    (root / 'package.json').write_text(json.dumps(manifest))
                    with patch.object(board_bos, 'MODEL_SHA', digest):
                        with self.assertRaisesRegex(ValueError, 'reference'):
                            board_bos.checked_bundle(root)

    def test_untrusted_model_digest_rejected_even_with_renewed_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.bundle(root)
            with self.assertRaisesRegex(ValueError, 'selected model'):
                board_bos.checked_bundle(root)

    def conditioned_bundle(self, root):
        digest = self.bundle(root)
        profile = board_bos.package_profile({'model_profile': board_bos.CONDITIONED_PROFILE})
        reference = {'model_profile': profile['name'], 'original_goldens_sha256': profile['reference_sha256']}
        (root / 'bos-logits.json').write_text(json.dumps(dict(reference, tokens=[256], logits=[0] * 320)))
        (root / 'token-logits.json').write_text(json.dumps(dict(reference, schema=1, cases=[
            {'name': name, 'tokens': [256] + [0] * (count - 1), 'logits': [[0] * 320] * count}
            for name, count in profile['cases'].items()])))
        manifest = json.loads((root / 'package.json').read_text())
        manifest['model_profile'] = profile['name']
        for name in ('bos-logits.json', 'token-logits.json'):
            data = (root / name).read_bytes()
            manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        (root / 'package.json').write_text(json.dumps(manifest))
        return digest

    def test_conditioned_profile_binds_its_own_weight_and_reference_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            digest = self.conditioned_bundle(root)
            with self.assertRaisesRegex(ValueError, 'selected model'):
                board_bos.checked_bundle(root)
            with patch.object(board_bos, 'CONDITIONED_MODEL_SHA', digest):
                image, scores, profile = board_bos.checked_bundle(root, with_profile=True)
            self.assertEqual((len(image), len(scores)), (117124, 320))
            self.assertEqual(profile['encoding'], 'hex')
            self.assertEqual(profile['default_max_new_tokens'], 255)
            self.assertEqual(sum(profile['cases'].values()), 522)

    def test_conditioned_reference_cannot_be_replaced_by_legacy_with_renewed_file_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            digest = self.conditioned_bundle(root)
            path = root / 'bos-logits.json'
            ref = json.loads(path.read_text())
            ref['original_goldens_sha256'] = board_bos.GOLDENS_SHA
            path.write_text(json.dumps(ref))
            manifest = json.loads((root / 'package.json').read_text())
            manifest['files'][path.name] = {'bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            (root / 'package.json').write_text(json.dumps(manifest))
            with patch.object(board_bos, 'CONDITIONED_MODEL_SHA', digest):
                with self.assertRaisesRegex(ValueError, 'reference identity'):
                    board_bos.checked_bundle(root)

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'profile'):
            board_bos.package_profile({'model_profile': 'unreviewed'})


class ConditionedPreparation(unittest.TestCase):
    def test_unsealed_receipts_reject_before_any_package_directory_is_created(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as temp:
            path = Path(temp) / 'results.json'
            path.write_text('{}')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(board_prepare.tempfile, 'mkdtemp') as create:
                with self.assertRaisesRegex(ValueError, 'receipt location/hash'):
                    board_prepare.conditioned_build(path, digest, path, digest, path, digest)
                create.assert_not_called()


class BoardPreflight(unittest.TestCase):
    def fixture(self, root, clock):
        def put(name, text):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(text, bytes):
                path.write_bytes(text)
            else:
                path.write_text(text)
        put('sys/class/fpga_manager/fpga0/state', 'operating\n')
        put('sys/class/fpga_manager/fpga0/flags', '0\n')
        put('sys/firmware/devicetree/base/fpga-region/firmware-name', board_bos.FIRMWARE + '\0')
        put('sys/kernel/debug/clk/clk_summary', clock)
        prefix = 'sys/firmware/devicetree/base/'
        controller = prefix + 'firmware/zynqmp-firmware/reset-controller/'
        put(controller + 'phandle', struct.pack('>I', 17))
        put(controller + '#reset-cells', struct.pack('>I', 1))
        put(controller + 'compatible', b'xlnx,zynqmp-reset\0')
        for node in ('fpga-region', 'axi/tiny_transformer_afi'):
            put(prefix + node + '/resets', struct.pack('>II', 17, 119))
        # Existing actual monitor identities must never be adopted for the model.
        for i in range(4):
            put('sys/class/uio/uio%d/name' % i, 'axi-pmon\n')

    def test_default_inspection_never_opens_or_maps_device(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.fixture(root, 'pl0_ref 1 1 0 49999999 0 0 50000 Y deviceless no_connection_id\n')
            with (patch.object(board_bos.os, 'open', side_effect=AssertionError('device open')),
                  patch.object(board_bos.mmap, 'mmap', side_effect=AssertionError('device mmap'))):
                result = board_bos.inspect_board(root)
            self.assertFalse(result['ready'])
            self.assertEqual(result['uio'], [])
            self.assertEqual(result['clock']['rate_hz'], 49999999)
            self.assertIn('Expected exactly one dedicated transformer UIO device', result['errors'])

    def test_wrong_disabled_missing_or_ambiguous_clock_rejected(self):
        for clock in ('pl0_ref 0 0 0 99999999 0 0 50000 Y deviceless no_connection_id\n',
                      'pl0_ref 1 1 0 50000001 0 0 50000 Y\n',
                      'pl0_ref 1 1 0 49999999 0 0 50000 N\n', '',
                      'pl0_ref 1 1 0 49999999 0 0 50000 Y\n' * 2):
            with self.subTest(clock=clock):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp).resolve()
                    self.fixture(root, clock)
                    result = board_bos.inspect_board(root)
                    self.assertTrue(any('Clock gate:' in value for value in result['errors']))

    def test_either_live_overlay_using_old_reset_is_rejected(self):
        for node in ('fpga-region', 'axi/tiny_transformer_afi'):
            with self.subTest(node=node):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp).resolve()
                    self.fixture(root, 'pl0_ref 1 1 0 49999999 0 0 50000 Y\n')
                    path = root / 'sys/firmware/devicetree/base' / node / 'resets'
                    path.write_bytes(struct.pack('>II', 17, 116))
                    result = board_bos.inspect_board(root)
                    self.assertTrue(any('Reset gate: Reset line differs' in value for value in result['errors']))

    def test_arbitrary_named_regular_file_is_not_a_uio_device(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.fixture(root, 'pl0_ref 1 1 0 49999999 0 0 50000 Y\n')
            node = root / 'sys/class/uio/uio9'
            (node / 'maps/map0').mkdir(parents=True)
            (node / 'name').write_text(board_bos.UIO_NAME)
            for name, value in (('addr', '0xa0000000'), ('size', hex(board_bos.mmap.PAGESIZE)), ('offset', '0')):
                (node / 'maps/map0' / name).write_text(value)
            dt = root / ('sys/firmware/devicetree/base' + board_bos.OF_PATH)
            dt.mkdir(parents=True)
            (dt / 'reg').write_bytes(struct.pack('>IIII', 0, 0xa0000000, 0, 0x100))
            (node / 'device').mkdir()
            (node / 'device/of_node').symlink_to(dt)
            driver = root / 'sys/bus/platform/drivers/uio_pdrv_genirq'
            driver.mkdir(parents=True)
            (node / 'device/driver').symlink_to(driver)
            (root / 'dev').mkdir()
            (root / 'dev/uio9').touch()
            result = board_bos.inspect_board(root)
            self.assertFalse(result['ready'])
            self.assertEqual(result['uio'], [])
            self.assertTrue(any('Unexpected map/DT/driver/device identity' in value for value in result['errors']))

    def ready_fixture(self, root):
        self.fixture(root, 'pl0_ref 1 1 0 49999999 0 0 50000 Y candidate unnamed\n')
        for driver, name in (('xilinx_fclk', 'tiny_transformer_clock'),
                             ('afi-fpga', 'tiny_transformer_afi'),
                             ('uio_pdrv_genirq', 'tiny-transformer@a0000000')):
            dt = root / 'sys/firmware/devicetree/base/axi' / name
            dt.mkdir(parents=True, exist_ok=True)
            device = root / 'sys/devices/platform' / name
            device.mkdir(parents=True)
            (device / 'of_node').symlink_to(dt)
            drv = root / 'sys/bus/platform/drivers' / driver
            drv.mkdir(parents=True)
            (drv / name).symlink_to(device)
            (device / 'driver').symlink_to(drv)
        node = root / 'sys/class/uio/uio4'
        (node / 'maps/map0').mkdir(parents=True)
        (node / 'name').write_text(board_bos.UIO_NAME)
        for name, value in (('addr', '0xa0000000'), ('size', hex(board_bos.mmap.PAGESIZE)), ('offset', '0')):
            (node / 'maps/map0' / name).write_text(value)
        (node / 'device').symlink_to(device)
        (dt / 'reg').write_bytes(struct.pack('>IIII', 0, 0xa0000000, 0, 0x100))
        (root / 'dev').mkdir()
        (root / 'dev/uio4').touch()
        return dt

    def test_known_hex_zero_manager_flags_accept(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.ready_fixture(root)
            path = root / 'sys/class/fpga_manager/fpga0/flags'
            for text in ('0\n', '00\n', '0x0\n', '0X00\n'):
                with self.subTest(flags=text):
                    path.write_text(text)
                    with patch.object(board_bos.stat, 'S_ISCHR', return_value=True):
                        result = board_bos.inspect_board(root)
                    self.assertTrue(result['ready'], result['errors'])
                    self.assertEqual(result['manager_flags'], 0)
                    self.assertEqual(path.read_text(), text)

    def test_nonzero_manager_flags_reject_and_are_parsed_as_hex(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.ready_fixture(root)
            path = root / 'sys/class/fpga_manager/fpga0/flags'
            for text, value in (('1', 1), ('10', 16), ('20\n', 32), ('0x20', 32), ('FF', 255)):
                with self.subTest(flags=text):
                    path.write_text(text)
                    with patch.object(board_bos.stat, 'S_ISCHR', return_value=True):
                        result = board_bos.inspect_board(root)
                    self.assertFalse(result['ready'])
                    self.assertEqual(result['manager_flags'], value)
                    self.assertEqual(result['errors'], [
                        'FPGA manager flags must be zero for firmware-file loading (found ' + hex(value) + ')'])
                    self.assertEqual(path.read_text(), text)

    def test_malformed_manager_flags_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.ready_fixture(root)
            path = root / 'sys/class/fpga_manager/fpga0/flags'
            for text in (b'', b'garbage', b'0x', b'20\n0', b'1g', b'\xff'):
                with self.subTest(flags=text):
                    path.write_bytes(text)
                    with patch.object(board_bos.stat, 'S_ISCHR', return_value=True):
                        result = board_bos.inspect_board(root)
                    self.assertFalse(result['ready'])
                    self.assertEqual(result['errors'], ['FPGA manager flags are missing or not hexadecimal'])
                    self.assertEqual(path.read_bytes(), text)

    def test_missing_manager_flags_reject_without_creating_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            self.ready_fixture(root)
            path = root / 'sys/class/fpga_manager/fpga0/flags'
            path.unlink()
            with patch.object(board_bos.stat, 'S_ISCHR', return_value=True):
                result = board_bos.inspect_board(root)
            self.assertFalse(result['ready'])
            self.assertEqual(result['errors'], ['FPGA manager flags are missing or not hexadecimal'])
            self.assertFalse(path.exists())

    def test_simulated_postload_identity_accepts_and_changed_reg_rejects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            dt = self.ready_fixture(root)
            # Only character-device type is simulated. No UIO open or mmap.
            with patch.object(board_bos.stat, 'S_ISCHR', return_value=True):
                self.assertTrue(board_bos.inspect_board(root)['ready'])
                (dt / 'reg').write_bytes(struct.pack('>IIII', 0, 0xa0001000, 0, 0x100))
                self.assertFalse(board_bos.inspect_board(root)['ready'])


if __name__ == '__main__':
    unittest.main()
