"""Fetch and adapt the hash-pinned Apache-2.0 decision loader at build time."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

manifest = json.loads(Path(sys.argv[1]).read_text())
root = Path(sys.argv[2])
for name, digest in manifest['files'].items():
    url = f"https://huggingface.co/{manifest['repository']}/resolve/{manifest['revision']}/{name}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(1024 * 1024)
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f'Pinned source checksum mismatch: {name}')
    target = root / (name.removeprefix('source/src/') if name.startswith('source/src/') else 'licenses/' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

path = root / 'pplx_decider/model.py'
source = path.read_text()
original = 'self.backbone = Qwen3_5Model.from_pretrained(str(checkpoint), dtype=dtype, attn_implementation="sdpa")'
replacement = '''self.backbone = Qwen3_5Model.from_pretrained(
            str(checkpoint), dtype=dtype, attn_implementation="sdpa", device_map={"": 0},
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_skip_modules=[r"^(?!language_model\\.layers\\.\\d+\\.mlp\\.).*"]))'''
if source.count(original) != 1:
    raise RuntimeError('Pinned loader no longer matches the reviewed NF4 adaptation')
source = source.replace('from transformers import AutoProcessor', 'from transformers import AutoProcessor, BitsAndBytesConfig')
source = source.replace(original, replacement)
compile(source, str(path), 'exec')
path.write_text(source)
(root / 'licenses/MODIFICATIONS').write_text(
    'Gradiated: loader adapted to NF4 decoder MLPs; attention, vision and readout remain BF16.\n'
    f"Upstream checkpoint/source revision: {manifest['revision']}\n")
