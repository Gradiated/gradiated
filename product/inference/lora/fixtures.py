import hashlib
import io
import json
import struct
import tarfile
import uuid


def archive(rank=2, hostile=None):
    config = json.dumps(
        {
            "peft_type": "LORA",
            "lora_alpha": 4,
            "r": rank,
            "target_modules": ["q_proj"],
            "bias": "none",
        }
    ).encode()
    header = {}
    data = bytearray()
    for layer in range(2):
        for side, shape in (("A", [rank, 4]), ("B", [4, rank])):
            size = 2 * shape[0] * shape[1]
            header[
                f"base_model.model.layers.{layer}.self_attn.q_proj.lora_{side}.weight"
            ] = {
                "dtype": "BF16",
                "shape": shape,
                "data_offsets": [len(data), len(data) + size],
            }
            data.extend(bytes(size))
    metadata = json.dumps(header).encode()
    weights = struct.pack("<Q", len(metadata)) + metadata + data
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for name, body in (
            ("adapter_config.json", config),
            ("adapter_model.safetensors", weights),
        ):
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.size = len(body)
            bundle.addfile(member, io.BytesIO(body))
        if hostile:
            bundle.addfile(hostile, io.BytesIO(b"x"))
    return output.getvalue()


def grant(payload):
    version_id = str(uuid.uuid4())
    return {
        "workspace_id": "01980000-0000-7000-8000-000000000001",
        "version": {
            "id": version_id,
            "name": f"version-{version_id}",
            "base_model_id": "base",
            "adapter": {
                "format": "peft_lora",
                "artifact_uri": "s3://bucket/adapter",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "base_model_revision": "base-revision",
                "rank": 2,
                "size_bytes": len(payload),
            },
        },
        "download": {
            "url": "https://bucket.s3.amazonaws.com/adapter",
            "expires_at": "2030-01-01T00:00:00Z",
        },
    }


def settings():
    return {
        "runtime_model_name": "base",
        "base_model_revision": "base-revision",
        "gpu_slots": 1,
        "model_config": {"num_hidden_layers": 2},
        "base_model_id": "base",
        "tensor_parallel_size": 2,
        "max_rank": 8,
        "cpu_adapter_slots": 1,
        "disk_cache_bytes": 1024 * 1024,
    }


def cartridge_file(tokens=3, hidden=4, slots=True, metadata=None, values=None):
    header = {
        "__metadata__": metadata
        if metadata is not None
        else {"format": "gradiated.cartridge/1", "placement": "system_prompt_start"}
    }
    embeddings = (
        values
        if values is not None
        else struct.pack(f"<{tokens * hidden}H", *([0x3F80] * (tokens * hidden)))
    )
    header["embeddings"] = {
        "dtype": "BF16",
        "shape": [tokens, hidden],
        "data_offsets": [0, len(embeddings)],
    }
    data = bytearray(embeddings)
    if slots:
        ids = struct.pack(f"<{tokens}q", *range(10, 10 + tokens))
        header["slot_token_ids"] = {
            "dtype": "I64",
            "shape": [tokens],
            "data_offsets": [len(data), len(data) + len(ids)],
        }
        data.extend(ids)
    encoded = json.dumps(header).encode()
    return struct.pack("<Q", len(encoded)) + encoded + bytes(data)


def cartridge_grant(payload, tokens=3, hidden=4, slots=True, separator="\n\n"):
    spec = grant(payload)
    spec["version"]["adapter"] = {
        "format": "cartridge",
        "artifact_uri": "s3://bucket/cartridge.safetensors",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "base_model_revision": "base-revision",
        "size_bytes": len(payload),
        "num_tokens": tokens,
        "hidden_size": hidden,
        "placement": "system_prompt_start",
        "separator": separator,
        "has_slot_token_ids": slots,
    }
    return spec


def cartridge_model_config():
    return {
        "num_hidden_layers": 2,
        "hidden_size": 4,
        "vocab_size": 32,
        "max_position_embeddings": 64,
    }


GRAD_SOURCE = {
    "kind": "grad",
    "artifact_id": "art_0123456789abcdef01234567",
    "artifact_source": "run",
    "bundle": "grad.artifact/1",
}


def grad_bundle(files, adapter_format="peft_lora", manifest=None, extra=None):
    """A grad.artifact/1 bundle as grad-trainer writes it: sorted, mtime 0, root members."""
    manifest = {
        "schema": "grad.artifact/1",
        "kind": "final",
        "format": adapter_format,
        "format_version": 1,
        "files": {
            name: hashlib.sha256(body).hexdigest() for name, body in files.items()
        },
        **(manifest or {}),
    }
    members = {"manifest.json": json.dumps(manifest).encode(), **files, **(extra or {})}
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for name in sorted(members):
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.size = len(members[name])
            bundle.addfile(member, io.BytesIO(members[name]))
    return output.getvalue()


def adapter_files(rank=2):
    with tarfile.open(fileobj=io.BytesIO(archive(rank)), mode="r:gz") as bundle:
        return {member.name: bundle.extractfile(member).read() for member in bundle}
