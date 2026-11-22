"""Offline behavioural checks. No device interfaces or network are accessed."""
import argparse
import copy
from hashlib import sha256
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest

L = None


def setUpModule():
    global L
    if L is not None:
        return
    from prepare_lifecycle import derive
    repo = Path(__file__).resolve().parents[7]
    prior = (repo / ".agents/runtime/hardware/inference/outputs/"
             "autonomous-prefill-decode-20261115T210134Z-97efcb/observer_lifecycle.py")
    if not prior.is_file():
        raise unittest.SkipTest("Pass --generated or recover the pinned autonomous-v1 lifecycle")
    scope = {}
    exec(compile(derive(prior.read_bytes()), str(prior), "exec"), scope)
    L = SimpleNamespace(**scope)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.original = root/'original'
        self.firmware = root/'firmware'
        self.staged = root/'staged'
        for folder in (self.original, self.firmware, self.staged):
            folder.mkdir()
        self.pins = {}
        for name in (L.CONTROL_FILE,L.OBSERVER_FILE,L.CONTROL_DTBO,L.OBS_DTBO):
            data = name.encode()
            (self.staged/name).write_bytes(data)
            self.pins[name] = L.file_pin(data)
            if name.endswith('.bin'):
                (self.firmware/name).write_bytes(data)
        (self.firmware/L.STOCK_FILE).write_bytes(b'stock-firmware')
        (self.original/'kv260-program.dtbo').write_bytes(b'original-overlay')
        (self.original/'kv260-interface.dtbo').write_bytes(b'interface-overlay')
        self.baseline = dict(boot_id='one-boot',kernel='k',model='kv260',taint='0',
                             ethernet_carrier='0',manager='operating',ownership={'uio':[]},dfx={},
                             bindings={'afi-fpga':['afi'],'uio_pdrv_genirq':['uio']},
                             uio={'0':L.PROJECT_UIO},clocks='pl0_ref 0 0 0 50000000 0 0 0 Y',warnings='')
        self.baseline.update(L.state_spec(self.baseline,'stock',True))
        self.mode, self.interface, self.warnings = 'stock', True, ''
        self.calls = []
        self.inject_warning = False
        live = SimpleNamespace(ORIGINAL=self.original, MANAGER=root/'manager', OVERLAYS=root/'overlays',
                               digest=lambda p:sha256(p.read_bytes()).hexdigest())
        self.setup = SimpleNamespace(live=live,FIRMWARE=self.firmware/L.STOCK_FILE,
                                    FIRMWARE_SHA=sha256(b'stock-firmware').hexdigest(),
                                    OVERLAY_PINS={'program':(16,sha256(b'original-overlay').hexdigest()),
                                                  'interface':(17,sha256(b'interface-overlay').hexdigest())},
                                    check_clock=lambda s:None,WRITE_OVERLAY='never-executed')

    def capture(self, label):
        value = copy.deepcopy(self.baseline)
        value.update(L.state_spec(self.baseline,self.mode,self.interface))
        value['warnings'] = self.warnings
        return value

    def command(self, label, argv, seconds):
        self.calls.append((label,argv,seconds))
        if label=='remove-interface':
            if self.inject_warning:
                self.warnings+='[0] unexpected warning\n'
            self.interface=False
        elif label=='remove-program':
            self.mode=None
        elif label=='apply-'+L.INTERFACE:
            self.interface=True
        else:
            modes={L.STOCK_OVERLAY:'stock',L.CONTROL_OVERLAY:'control',L.OBSERVER_OVERLAY:'candidate'}
            self.mode=modes[label.removeprefix('apply-')]

    def transition(self, before, after):
        return L.switch(self,self.setup,self.baseline,self.staged,self.pins,before,after)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx=Fixture(Path(self.tmp.name))

    def test_reviewed_sequence_and_restoration(self):
        fx=self.fx
        for before,after in [('stock','control'),('control','candidate'),('candidate','control'),
                             ('control','candidate'),('candidate','stock')]:
            out=fx.transition(before,after)
            self.assertEqual(out['from'],before)
            self.assertEqual(out['to'],after)
            self.assertEqual(out['firmware'],L.image_spec(after)[0])
            self.assertEqual(fx.mode,after)
            self.assertTrue(fx.interface)
            self.assertEqual([x[2] for x in fx.calls[-4:]],[15,15,60,20])
            L.check_state(fx.capture('done'),fx.baseline,after)
        self.assertEqual(len(fx.calls),20)

    def test_invalid_or_same_mode_before_actions(self):
        for modes in [('stock','stock'),('stock','unknown'),('unknown','stock')]:
            with self.assertRaises(ValueError): self.fx.transition(*modes)
        self.assertFalse(self.fx.calls)

    def test_corrupted_arm_aborts_before_actions(self):
        (self.fx.firmware/L.CONTROL_FILE).write_bytes(b'changed')
        with self.assertRaises(ValueError): self.fx.transition('stock','candidate')
        self.assertFalse(self.fx.calls)

    def test_new_warning_is_fail_stop(self):
        self.fx.inject_warning=True
        with self.assertRaisesRegex(ValueError,'Unexpected kernel notices'):
            self.fx.transition('stock','control')
        self.assertEqual([x[0] for x in self.fx.calls],['remove-interface'])

    def test_wrong_boot_is_rejected(self):
        state=self.fx.capture('before')
        state['boot_id']='other'
        with self.assertRaises(ValueError): L.check_state(state,self.fx.baseline,'stock')

    def test_logger_identity(self):
        source=('firmware="'+L.STOCK_FILE+'"').encode()
        for mode in ('stock','control','candidate'):
            derived=L.derive_logger(source,mode,lambda b:b)
            self.assertIn(L.image_spec(mode)[0].encode(),derived)
        with self.assertRaises(ValueError): L.derive_logger(source,'unknown',lambda b:b)

    def test_bundles_use_correct_assets_and_preserve_original(self):
        stock=self.fx.root/'stock-bundle'
        stock.mkdir()
        data={'board_bos.py':("FIRMWARE = '"+L.STOCK_FILE+"'\n").encode(),
              L.STOCK_FILE:b'stock-firmware','kv260-program.dtbo':b'original-overlay',
              'weights.bin':b'frozen-weights'}
        manifest={'files':{name:L.file_pin(b) for name,b in data.items()}}
        for name,b in data.items(): (stock/name).write_bytes(b)
        blob=json.dumps(manifest).encode()
        (stock/'package.json').write_bytes(blob)
        def read_pin(path,pin):
            b=path.read_bytes()
            self.assertEqual(sha256(b).hexdigest(),pin)
            return b
        resident=SimpleNamespace(sealed_runner=lambda p:{'checked_bundle':lambda p:None},
                                 PACKAGE_SHA256=sha256(blob).hexdigest(),
                                 SEALED_RUNNER_SHA256=sha256(data['board_bos.py']).hexdigest(),read_pinned=read_pin)
        for mode in ('control','candidate'):
            destination=self.fx.root/('bundle-'+mode)
            pin=L.prepare_bundle(stock,self.fx.staged,destination,resident,self.fx.pins,mode=mode)
            self.assertEqual(pin,L.file_pin((destination/'package.json').read_bytes()))
            out=json.loads((destination/'package.json').read_text())
            firmware=L.image_spec(mode)[0]
            self.assertIn(firmware,out['files'])
            self.assertNotIn(L.STOCK_FILE,out['files'])
            self.assertIn(firmware.encode(),(destination/'board_bos.py').read_bytes())
            self.assertEqual((destination/'kv260-program.dtbo').read_bytes(),L.image_overlay(mode).encode())
            self.assertEqual((destination/'weights.bin').read_bytes(),b'frozen-weights')
        for name,b in data.items(): self.assertEqual((stock/name).read_bytes(),b)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--generated", type=Path)
    args, remaining = parser.parse_known_args()
    if args.generated:
        L = SimpleNamespace(**runpy.run_path(str(args.generated)))
    unittest.main(argv=[__file__, *remaining])
