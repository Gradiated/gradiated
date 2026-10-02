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
