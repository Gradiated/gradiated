"""Bind cached evaluations to the installed runtime and imported implementations."""

import hashlib
import json
import sys
from importlib import metadata
from pathlib import Path

PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "tokenizers",
    "accelerate",
    "safetensors",
    "jinja2",
)


def runtime_fingerprint():
    packages = {}
    for name in PACKAGES:
        try:
            version = metadata.version(name)
            direct = json.loads(
                metadata.distribution(name).read_text("direct_url.json") or "{}"
            )
            packages[name] = {
                "version": version,
                "vcs": direct.get("vcs_info"),
                "archive": direct.get("archive_info"),
            }
        except metadata.PackageNotFoundError:
            packages[name] = {"version": None}
    implementations = {}
    for name, module in sorted(sys.modules.copy().items()):
        if not any(
            name == package or name.startswith(package + ".") for package in PACKAGES
        ):
            continue
        file = getattr(module, "__file__", None)
        if file and Path(file).is_file():
            implementations[name] = hashlib.sha256(Path(file).read_bytes()).hexdigest()
    torch = sys.modules.get("torch")
    cuda = None
    if torch is not None and torch.cuda.is_available():
        cuda = {
            "torch_cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "tf32_matmul": torch.backends.cuda.matmul.allow_tf32,
            "tf32_cudnn": torch.backends.cudnn.allow_tf32,
        }
    return {
        "packages": packages,
        "imported_implementations_sha256": implementations,
        "cuda": cuda,
    }
