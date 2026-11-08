from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_MISSING = object()
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
STOCK = 0


class VariantError(ValueError):
    pass


class Patcher:
    def __init__(self) -> None:
        self._records: list[tuple[Any, str, Any]] = []

    def __call__(self, target: Any, name: str, value: Any) -> Any:
        if isinstance(target, str):
            target = importlib.import_module(target)
        previous = vars(target).get(name, _MISSING) if hasattr(target, "__dict__") else _MISSING
        self._records.append((target, name, previous))
        setattr(target, name, value)
        return value

    def __len__(self) -> int:
        return len(self._records)

    def undo(self) -> int:
        count = len(self._records)
        while self._records:
            target, name, previous = self._records.pop()
            if previous is _MISSING:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
            else:
                setattr(target, name, previous)
        return count


@dataclass
class VariantSource:
    name: str
    code: str
    sha256: str


def catalog(variants_dir: str | None = None) -> dict[str, str]:
    """Variant id to sha256 for every selectable variant, each verified against its file."""
    manifest_path = Path(variants_dir or os.environ.get("LIVETUNE_VARIANTS_DIR", "")) / "manifest.json"
    if not manifest_path.is_file():
        return {}
    ids = [entry["id"] for entry in json.loads(manifest_path.read_text()).get("variants", [])]
    return {str(variant_id): resolve(variant_id, variants_dir).sha256 for variant_id in ids}


def resolve(variant_id: int, variants_dir: str | None = None) -> VariantSource:
    if isinstance(variant_id, bool) or not isinstance(variant_id, int) or variant_id < 1:
        raise VariantError(f"variant id must be a positive integer, got {variant_id!r}")
    root = Path(variants_dir or os.environ.get("LIVETUNE_VARIANTS_DIR", ""))
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise VariantError(f"no variant manifest at {manifest_path}")
    entries = {entry["id"]: entry for entry in json.loads(manifest_path.read_text()).get("variants", [])}
    entry = entries.get(variant_id)
    if entry is None:
        raise VariantError(f"variant {variant_id} is not in the manifest")
    if not _NAME.match(entry["name"]):
        raise VariantError(f"invalid variant name {entry['name']!r}")
    code = (root / f"{entry['name']}.py").read_text()
    digest = hashlib.sha256(code.encode()).hexdigest()
    if digest != entry["sha256"]:
        raise VariantError(f"variant {entry['name']} does not match its pinned sha256")
    return VariantSource(entry["name"], code, digest)


def register(variants_dir: str | Path, name: str, code: str) -> int:
    if not _NAME.match(name):
        raise VariantError(f"invalid variant name {name!r}")
    root = Path(variants_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    entries = json.loads(manifest_path.read_text()).get("variants", []) if manifest_path.is_file() else []
    existing = next((e for e in entries if e["name"] == name), None)
    variant_id = existing["id"] if existing else max([e["id"] for e in entries], default=0) + 1
    entries = [e for e in entries if e["name"] != name] + [{"id": variant_id, "name": name, "sha256": hashlib.sha256(code.encode()).hexdigest()}]
    (root / f"{name}.py").write_text(code)
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"variants": sorted(entries, key=lambda e: e["id"])}, indent=1))
    temporary.replace(manifest_path)
    return variant_id


@dataclass
class InstalledVariant:
    source: VariantSource
    patcher: Patcher = field(default_factory=Patcher)
    module: types.ModuleType | None = None


def install(source: VariantSource, model: Any, ctx: dict[str, Any]) -> InstalledVariant:
    installed = InstalledVariant(source)
    module = types.ModuleType(f"livetune_variant_{source.sha256[:12]}")
    module.__file__ = f"<variant {source.name}>"
    try:
        exec(compile(source.code, module.__file__, "exec"), module.__dict__)
        entry: Callable[..., Any] | None = getattr(module, "install", None)
        if entry is None:
            raise VariantError(f"variant {source.name} defines no install(model, patch, ctx)")
        sys.modules[module.__name__] = module
        entry(model, installed.patcher, ctx)
    except Exception:
        installed.patcher.undo()
        sys.modules.pop(module.__name__, None)
        raise
    installed.module = module
    return installed


def uninstall(installed: InstalledVariant) -> int:
    restored = installed.patcher.undo()
    if installed.module is not None:
        sys.modules.pop(installed.module.__name__, None)
    return restored
