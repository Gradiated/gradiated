"""Bind cached evaluations to the installed runtime and imported implementations."""

import hashlib
import json
import sys
from importlib import metadata, util
from pathlib import Path

PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "tokenizers",
    "accelerate",
    "safetensors",
    "jinja2",
    "triton",
    "numpy",
    "tiktoken",
)


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def runtime_fingerprint():
    packages = {}
    package_files = {}
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
        try:
            specification = util.find_spec(name)
        except (ImportError, ValueError):
            specification = None
        roots = (
            list(specification.submodule_search_locations or [])
            if specification
            else []
        )
        for directory in roots:
            root = Path(directory)
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix in (
                    ".py",
                    ".so",
                    ".pyd",
                    ".dll",
                    ".dylib",
                    ".json",
                    ".jinja",
                    ".model",
                ):
                    package_files[name + "/" + str(path.relative_to(root))] = (
                        file_sha256(path)
                    )
    implementations = {}
    for name, module in sorted(sys.modules.copy().items()):
        if not any(
            name == package or name.startswith(package + ".") for package in PACKAGES
        ):
            continue
        file = getattr(module, "__file__", None)
        if file and Path(file).is_file():
            implementations[name] = file_sha256(file)
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
        "python": sys.version,
        "installed_versions": {
            distribution.metadata["Name"]: distribution.version
            for distribution in metadata.distributions()
            if distribution.metadata.get("Name")
        },
        "packages": packages,
        "imported_implementations_sha256": implementations,
        "installed_package_files_sha256": package_files,
        "cuda": cuda,
    }
