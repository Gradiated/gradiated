from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import torch
import transformers


CHECKPOINT_DTYPE_BITS = {
    "bfloat16": 16,
    "float16": 16,
    "float32": 32,
    "float64": 64,
}
TOKENIZER_DEFINITION_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_precision_bits(path: Path) -> int:
    config_path = path / "config.json"
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"local model config is missing: {config_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid model config: {config_path}") from error
    if not isinstance(document, dict):
        raise ValueError(f"model config must be an object: {config_path}")
    dtype = str(document.get("dtype", document.get("torch_dtype", "")))
    try:
        return CHECKPOINT_DTYPE_BITS[dtype]
    except KeyError as error:
        raise ValueError(
            f"unsupported checkpoint dtype: {dtype or 'missing'}"
        ) from error


def tokenizer_identity(path: Path, tokenizer: object) -> dict[str, object]:
    files = [
        path / name for name in TOKENIZER_DEFINITION_FILES if (path / name).is_file()
    ]
    if not files:
        raise FileNotFoundError(f"local tokenizer definition is missing under {path}")
    return {
        "local_path": str(path.resolve()),
        "class": type(tokenizer).__name__,
        "vocab_size": int(getattr(tokenizer, "vocab_size")),
        "files": [
            {
                "name": file.name,
                "bytes": file.stat().st_size,
                "sha256": sha256_file(file),
            }
            for file in files
        ],
    }


def validate_model_directory(path: Path) -> list[Path]:
    if not path.exists():
        raise FileNotFoundError(
            f"local model directory does not exist: {path}; download weights before running validation"
        )
    if not path.is_dir():
        raise ValueError(f"model path must be a directory: {path}")
    config_path = path / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"local model config is missing: {config_path}")
    weight_files = sorted(path.glob("*.safetensors")) + sorted(
        path.glob("pytorch_model*.bin")
    )
    if not weight_files:
        raise FileNotFoundError(
            f"local model weights are missing under {path}; expected safetensors or pytorch_model*.bin"
        )
    return weight_files


def model_identity(path: Path, weight_files: list[Path]) -> dict[str, object]:
    config_path = path / "config.json"
    return {
        "local_path": str(path.resolve()),
        "local_files_only": True,
        "config_sha256": sha256_file(config_path),
        "weight_files": [
            {
                "name": weight.relative_to(path).as_posix(),
                "bytes": weight.stat().st_size,
                "sha256": sha256_file(weight),
            }
            for weight in weight_files
        ],
    }


def software_identity() -> dict[str, object]:
    return {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "device": "cpu",
    }
