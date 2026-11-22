import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import weights


class WeightsTest(unittest.TestCase):
    def test_load_validates_image_before_upload(self):
        data = bytes([0x69]) * weights.MATRIX_BYTES
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.bin"
            path.write_bytes(data + b"\0")
            with self.assertRaisesRegex(ValueError, "matrix bytes"):
                weights.read_matrix(path)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                weights.read_matrix(path)
            with patch.object(weights, "MATRIX_SHA256", hashlib.sha256(data).hexdigest()):
                self.assertEqual(weights.read_matrix(path), data)

    @patch.object(weights.fcntl, "ioctl")
    def test_counter_order(self, ioctl):
        expected = list(range(11, 20))
        ioctl.return_value = weights.STATE.pack(
            0x120000, 2048, 0x120000, 0x11, *expected, 0x44445231
        )
        state = weights.read_state(3)
        ioctl.assert_called_once_with(3, 0x80385700, bytes(56))
        self.assertEqual(state["dma_base"], "0x00120000")
        self.assertEqual(state["dma_bytes"], 2048)
        self.assertEqual(state["mode"], "ddr")
        self.assertFalse(state["safe_release"])
        self.assertTrue(state["counter_saturated"])
        self.assertEqual([state[key] for key in weights.COUNTERS], expected + [0x44445231])

    @patch.object(weights.fcntl, "ioctl")
    @patch.object(weights.os, "close")
    @patch.object(weights.os, "open", return_value=3)
    def test_close_does_not_clear(self, open_device, close_device, ioctl):
        with weights.Fixture() as fixture:
            fixture.select("ddr")
        ioctl.assert_called_once_with(3, 0x5702)
        close_device.assert_called_once_with(3)


if __name__ == "__main__":
    unittest.main()
