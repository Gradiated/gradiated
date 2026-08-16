from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .schema import EngineSpec


def _canonical_id(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SourceProvenance:
    revision: str
    version: str
    tracked_diff_sha256: str
    installed_binary_sha256: str
    installed_binary_path: str
    dirty_paths: tuple[str, ...]
    server_command: tuple[str, ...]
    benchmark_command: tuple[str, ...]
    content_id: str

    @classmethod
    def create(
        cls,
        revision: str,
        version: str,
        tracked_diff_sha256: str,
        installed_binary_sha256: str,
        installed_binary_path: str,
        dirty_paths: tuple[str, ...],
        server_command: tuple[str, ...],
        benchmark_command: tuple[str, ...],
    ) -> SourceProvenance:
        identity = {
            "revision": revision,
            "version": version,
            "tracked_diff_sha256": tracked_diff_sha256,
            "installed_binary_sha256": installed_binary_sha256,
            "installed_binary_path": installed_binary_path,
            "dirty_paths": list(dirty_paths),
            "server_command": list(server_command),
            "benchmark_command": list(benchmark_command),
        }
        return cls(
            revision=revision,
            version=version,
            tracked_diff_sha256=tracked_diff_sha256,
            installed_binary_sha256=installed_binary_sha256,
            installed_binary_path=installed_binary_path,
            dirty_paths=dirty_paths,
            server_command=server_command,
            benchmark_command=benchmark_command,
            content_id=_canonical_id(identity),
        )

    def to_mapping(self) -> dict:
        return asdict(self)


def _run(command: tuple[str, ...], cwd: Path, text: bool = True):
    return subprocess.run(
        command, cwd=cwd, capture_output=True, text=text, check=True
    ).stdout


def capture_source(
    engine: EngineSpec,
    server_command: tuple[str, ...],
    benchmark_command: tuple[str, ...],
) -> SourceProvenance:
    revision = _run(("git", "rev-parse", "HEAD"), engine.checkout).strip()
    diff = _run(("git", "diff", "--binary", "HEAD", "--"), engine.checkout, False)
    status = _run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        engine.checkout,
    )
    version = (
        _run(
            (str(engine.python), "-c", "import vllm; print(vllm.__version__)"),
            engine.checkout,
        )
        .strip()
        .splitlines()[-1]
    )
    binary_path = (
        _run(
            (
                str(engine.python),
                "-c",
                "import importlib.util; print(importlib.util.find_spec('vllm._C').origin)",
            ),
            engine.checkout,
        )
        .strip()
        .splitlines()[-1]
    )
    dirty_paths = tuple(sorted(line[3:] for line in status.splitlines() if line))
    return SourceProvenance.create(
        revision=revision,
        version=version,
        tracked_diff_sha256=hashlib.sha256(diff).hexdigest(),
        installed_binary_sha256=sha256_file(Path(binary_path)),
        installed_binary_path=binary_path,
        dirty_paths=dirty_paths,
        server_command=server_command,
        benchmark_command=benchmark_command,
    )


def validate_source(source: SourceProvenance, engine: EngineSpec) -> tuple[str, ...]:
    reasons: list[str] = []
    if source.revision != engine.expected_revision:
        reasons.append("vLLM revision drift")
    if source.version != engine.expected_version:
        reasons.append("vLLM version drift")
    if source.tracked_diff_sha256 != engine.expected_tracked_diff_sha256:
        reasons.append("vLLM tracked diff drift")
    if source.installed_binary_sha256 != engine.expected_installed_binary_sha256:
        reasons.append("vLLM installed binary drift")
    return tuple(reasons)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
