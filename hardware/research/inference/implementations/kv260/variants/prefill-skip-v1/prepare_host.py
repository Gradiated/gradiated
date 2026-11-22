"""Generate a common reader for autonomous-v1 and prefill-skip-v1."""
from hashlib import sha256
from pathlib import Path
import argparse
from materialise import replace

SOURCE_PINS = {
    "autonomous_mmio.c":"01206644c353c2468babfbac98835ecf32a518e64f858f03246b1c1d22fbb27c",
    "autonomous_runtime.py":"7879ccab3d3d5e4adffcc5c1443a37f2ac6f6d3584ed170b89eea95a26a4ed57",
}


def prepare(baseline, output):
    inputs = {}
    for name, pin in SOURCE_PINS.items():
        data = (baseline/name).read_bytes()
        if sha256(data).hexdigest()!=pin:
            raise ValueError(f"Baseline host differs: {name}")
        inputs[name]=data.decode()
    c = replace(inputs["autonomous_mmio.c"], "case 0x50: case 0x54: case 0x58:",
                "case 0x50: case 0x54: case 0x58: case 0x5c:")
    c = replace(c, "uint32_t max_output, uint64_t deadline)",
                "uint32_t max_output, uint64_t deadline, uint32_t abi)")
    c = replace(c, "read_word(base, 0x24) != UINT32_C(0x41553031)", "read_word(base, 0x24) != abi")
    py = replace(inputs["autonomous_runtime.py"], "ABI = 0x41553031", "ABI = 0x41553031\nSKIP_ABI = 0x41553032")
    py = replace(py, "def __init__(self, session, library):",
                 "def __init__(self, session, library, abi):\n"
                 "        if abi not in (ABI, SKIP_ABI):\n"
                 "            raise ValueError('Unknown expected ABI')\n"
                 "        self.abi = abi")
    py = replace(py, "ctypes.c_size_t, u32, u64],", "ctypes.c_size_t, u32, u64, u32],")
    py = replace(py, "if self.read(0x24) != ABI:", "if self.read(0x24) != self.abi:")
    py = replace(py, "len(prefix), max_output, deadline_ns)", "len(prefix), max_output, deadline_ns, self.abi)")
    py = replace(py, "def finish_candidate(port, output, times, reason, observed, status):",
                 "def finish_candidate(port, output, times, reason, observed, status, prefix_count):")
    py = replace(py, "    if not 1 <= count <= CONTEXT or port.read(0x20) != count or scores != VOCAB * count:",
                 "    skips = port.read(0x5c) if port.abi == SKIP_ABI else 0\n"
                 "    expected_skips = prefix_count - 1 if port.abi == SKIP_ABI else 0\n"
                 "    if (skips != expected_skips or not prefix_count <= count <= CONTEXT or\n"
                 "            port.read(0x20) != count or scores != VOCAB * (count - skips)):")
    py = replace(py, '"request_cycles": internal}', '"request_cycles": internal, "skipped_positions": skips}')
    py = replace(py, "return finish_candidate(port, output, times, reason, observed, status)",
                 "return finish_candidate(port, output, times, reason, observed, status, len(prefix))")
    output.mkdir(parents=True, exist_ok=False)
    (output/"autonomous_mmio.c").write_text(c)
    (output/"autonomous_runtime.py").write_text(py)


if __name__=="__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    prepare(a.baseline,a.output)
