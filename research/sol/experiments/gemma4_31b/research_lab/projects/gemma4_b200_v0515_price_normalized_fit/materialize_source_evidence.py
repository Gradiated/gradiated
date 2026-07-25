#!/usr/bin/env python3
import hashlib
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
BASE = f"https://raw.githubusercontent.com/sgl-project/sglang/{COMMIT}"
SOURCES = {
    "python/sglang/srt/layers/attention/triton_ops/decode_attention.py": "4ecf5d81f06fcc8aa36479541ff3857a1416e2d8def2c5fa818808148febaa75",
    "python/sglang/srt/layers/attention/triton_ops/extend_attention.py": "2f4a934625b38d2e797a92c5966270c4d36ebfce9dc0093fb83bf18b140e9f28",
    "python/sglang/srt/layers/gemma4_fused_ops.py": "f9d8c7c3ea71afc1341c2de02807b8fda94e418248bd9ee404b15b3337463ad3",
    "python/sglang/srt/layers/quantization/fp8.py": "15eca3ffb6fc5c9767c1ff0d704d47647dd42383afd84a1f78b65c11fa58e1ec",
    "python/sglang/srt/layers/quantization/fp8_utils.py": "bd5b7ddfe86ce5837d2e39a5d62d5aeac348eb4e18a5dd7d5c2518379daf58fc",
    "python/sglang/srt/model_executor/model_runner.py": "91fcb5873f26679498eec052c68e1d91102af79cdf7d0486dd5aa9f68e839171",
    "python/sglang/srt/utils/common.py": "53226d80b87bc737f1b41aadca8ce9d0e171a37fbc2569dc4b281b00fbe190ac",
    "sgl-kernel/CMakeLists.txt": "5d91e2ab9af1ae51d313b61b740203a03c9986cfa997b3e54fbd668cd0bc9067",
    "sgl-kernel/csrc/gemm/fp8_gemm_kernel.cu": "be6f95bb0ef108ebf08b8b84336b6840726beb7fa5bbb90aa6eb4038ce778767",
    "sgl-kernel/pyproject.toml": "9ebebc2b77811e0b90037198c1f41536c037f85337ccc96434642a51d4eec162",
    "sgl-kernel/python/sgl_kernel/load_utils.py": "e7db471562b3fa3748af4793fc1647f23d9dd2142249d6cccd6bbe671a38c5c2",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    evidence = ROOT / "evidence" / "official-v0.5.15"
    for relative, expected in SOURCES.items():
        target = evidence / relative
        if target.is_file() and digest(target.read_bytes()) == expected:
            continue
        with urllib.request.urlopen(f"{BASE}/{relative}", timeout=30) as response:
            data = response.read()
        actual = digest(data)
        if actual != expected:
            raise RuntimeError(f"source_hash_mismatch:{relative}:{actual}")
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        part.write_bytes(data)
        part.replace(target)


if __name__ == "__main__":
    main()
