"""Verify the actual local snapshot before attributing results to a Hub revision."""

import hashlib
import json
from pathlib import Path

MODEL = "thinkingmachines/Inkling-2-Mini"
REVISION = "6e7c8248f75265bdd4fbab5273304243b5d8c2cb"


def verify_snapshot(run_dir, check=lambda: None):
    check()
    root = Path(run_dir)
    manifest = json.loads((root / "model-manifest.json").read_text())
    if manifest.get("id") != MODEL or manifest.get("sha") != REVISION:
        raise ValueError("model manifest does not describe the pinned Inkling release")
    files = []
    metadata = {}
    listed = {row["rfilename"] for row in manifest["siblings"]}
    actual = set()
    for path in (root / "model").rglob("*"):
        check()
        if path.is_file() and not path.relative_to(root / "model").is_relative_to(
            ".cache/huggingface"
        ):
            actual.add(str(path.relative_to(root / "model")))
    if actual != listed:
        raise ValueError(
            f"model files differ from pinned manifest: extra={sorted(actual - listed)}, "
            f"missing={sorted(listed - actual)}"
        )
    for row in manifest["siblings"]:
        check()
        relative = Path(row["rfilename"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid manifest path")
        path = root / "model" / relative
        stat = path.stat()
        if stat.st_size != row["size"]:
            raise ValueError(f"model file size mismatch: {relative}")
        algorithm = "sha256" if row.get("lfs") else "git-sha1"
        digest = row["lfs"]["sha256"] if row.get("lfs") else row["blobId"]
        files.append(
            {
                "path": str(relative),
                "size": row["size"],
                "algorithm": algorithm,
                "digest": digest,
            }
        )
        metadata[str(relative)] = [
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
            stat.st_mode & 0o777,
        ]
    if not files or not any(x["path"].endswith(".safetensors") for x in files):
        raise ValueError("manifest contains no model weights")
    payload = {
        "model": MODEL,
        "revision": REVISION,
        "files": sorted(files, key=lambda x: x["path"]),
    }
    manifest_digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    marker_path = root / "model-integrity.json"
    marker = json.loads(marker_path.read_text()) if marker_path.exists() else {}
    if (
        all(not (entry[-1] & 0o222) for entry in metadata.values())
        and marker.get("manifest_sha256") == manifest_digest
        and marker.get("metadata") == metadata
    ):
        return manifest_digest
    for item in files:
        digest = hashlib.sha256() if item["algorithm"] == "sha256" else hashlib.sha1()
        if item["algorithm"] == "git-sha1":
            digest.update(b"blob " + str(item["size"]).encode() + b"\0")
        with (root / "model" / item["path"]).open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                check()
                digest.update(chunk)
        if digest.hexdigest() != item["digest"]:
            raise ValueError(f"model file digest mismatch: {item['path']}")
    temporary = marker_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"manifest_sha256": manifest_digest, "metadata": metadata}, indent=2)
    )
    temporary.replace(marker_path)
    return manifest_digest
