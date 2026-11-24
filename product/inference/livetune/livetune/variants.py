from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import linecache
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


def code_id(code: str) -> int:
    """A variant's id: 48 bits of its code's sha256, so an id names the same code on every host.

    It fits the numeric update endpoint, like a policy version.
    """
    return int(hashlib.sha256(code.encode()).hexdigest()[:12], 16) or 1


def _root(variants_dir: str | Path | None) -> Path:
    return Path(variants_dir or os.environ.get("LIVETUNE_VARIANTS_DIR", ""))


def _entries(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "manifest.json"
    return json.loads(manifest_path.read_text()).get("variants", []) if manifest_path.is_file() else []


def _file(root: Path, entry: dict[str, Any]) -> Path:
    return root / f"{entry['name']}-{entry['sha256'][:12]}.py"


def catalog(variants_dir: str | None = None) -> dict[str, str]:
    """Variant id to sha256 for every selectable variant, each verified against its file."""
    root = _root(variants_dir)
    return {str(entry["id"]): resolve(entry["id"], variants_dir).sha256 for entry in _entries(root)}


def resolve(variant_id: int, variants_dir: str | Path | None = None) -> VariantSource:
    if isinstance(variant_id, bool) or not isinstance(variant_id, int) or variant_id < 1:
        raise VariantError(f"variant id must be a positive integer, got {variant_id!r}")
    root = _root(variants_dir)
    if not (root / "manifest.json").is_file():
        raise VariantError(f"no variant manifest at {root / 'manifest.json'}")
    entry = next((e for e in _entries(root) if e["id"] == variant_id), None)
    if entry is None:
        raise VariantError(f"variant {variant_id} is not in the manifest")
    if not _NAME.match(entry["name"]):
        raise VariantError(f"invalid variant name {entry['name']!r}")
    code = _file(root, entry).read_text()
    digest = hashlib.sha256(code.encode()).hexdigest()
    # The id is the code's hash, so a file that changed no longer matches either.
    if digest != entry["sha256"] or code_id(code) != variant_id:
        raise VariantError(f"variant {entry['name']} does not match its pinned sha256")
    return VariantSource(entry["name"], code, digest)


def register(variants_dir: str | Path, name: str, code: str) -> int:
    """Add a variant to a directory's manifest and return its id. The same code always gets the same
    id, and registering it again changes nothing; a name may carry several revisions."""
    if not _NAME.match(name):
        raise VariantError(f"invalid variant name {name!r}")
    root = Path(variants_dir)
    root.mkdir(parents=True, exist_ok=True)
    new_id, sha256 = code_id(code), hashlib.sha256(code.encode()).hexdigest()
    # The controller and an operator's job may register into one directory at once.
    with open(root / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = _entries(root)
        entry = {"id": new_id, "name": name, "sha256": sha256}
        existing = next((e for e in entries if e["id"] == new_id), None)
        if existing is not None:
            entry = existing
        path = _file(root, entry)
        if not path.is_file() or path.read_text() != code:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(code)
            temporary.replace(path)
        if existing is None:
            manifest_path = root / "manifest.json"
            temporary = manifest_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"variants": sorted(entries + [entry], key=lambda e: e["id"])}, indent=1))
            temporary.replace(manifest_path)
    return new_id


def embedded(source: VariantSource) -> dict[str, str]:
    """A variant as a policy carries it: its code travels with the policy to every replica."""
    return {"name": source.name, "sha256": source.sha256, "code": source.code}


def check_embedded(variant_id: str, entry: dict[str, Any]) -> None:
    code = entry.get("code")
    if not isinstance(code, str) or not _NAME.match(str(entry.get("name", ""))):
        raise VariantError(f"variant {variant_id} needs a name and its code")
    if hashlib.sha256(code.encode()).hexdigest() != entry.get("sha256") or str(code_id(code)) != str(variant_id):
        raise VariantError(f"variant {variant_id} ({entry.get('name')}) does not match its id and sha256")


@dataclass
class InstalledVariant:
    source: VariantSource
    patcher: Patcher = field(default_factory=Patcher)
    module: types.ModuleType | None = None


def install(source: VariantSource, model: Any, ctx: dict[str, Any]) -> InstalledVariant:
    installed = InstalledVariant(source)
    module = types.ModuleType(f"livetune_variant_{source.sha256[:12]}")
    module.__file__ = f"<variant {source.name} {source.sha256[:12]}>"
    # Kernel compilers read a function's source (triton.jit uses inspect.getsource): serve the
    # verified code from linecache under the module's name, not from a file that could change.
    linecache.cache[module.__file__] = (len(source.code), None, source.code.splitlines(True), module.__file__)
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
