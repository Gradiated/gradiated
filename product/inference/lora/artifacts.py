import hashlib
import json
import math
import re
import shutil
import struct
import tarfile
import time
import urllib.parse
import urllib.request


def strict_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("Non-finite JSON number")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite JSON number")
        return result

    result = json.loads(
        data,
        object_pairs_hook=unique,
        parse_constant=invalid_constant,
        parse_float=finite_float,
    )
    if not isinstance(result, dict):
        raise TypeError("Expected JSON object")
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Artifact redirects are forbidden")


def download(spec, destination, allowed_hosts):
    url = urllib.parse.urlsplit(spec["download"]["url"])
    if (
        url.scheme != "https"
        or url.hostname not in allowed_hosts
        or url.username
        or url.password
        or url.port not in (None, 443)
    ):
        raise ValueError("Untrusted artifact URL")
    digest = hashlib.sha256()
    size = 0
    deadline = time.monotonic() + 60
    opener = urllib.request.build_opener(NoRedirect())
    with (
        opener.open(spec["download"]["url"], timeout=30) as response,
        destination.open("wb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if (
                size > spec["version"]["adapter"]["size_bytes"]
                or time.monotonic() > deadline
            ):
                raise ValueError("Archive exceeds declared size")
            digest.update(chunk)
            output.write(chunk)
    if (
        size != spec["version"]["adapter"]["size_bytes"]
        or digest.hexdigest() != spec["version"]["adapter"]["sha256"]
    ):
        raise ValueError("Archive integrity mismatch")


def extract(archive, destination, max_bytes, reserve=None):
    allowed = {"adapter_config.json", "adapter_model.safetensors", "README.md"}
    seen = set()
    total = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for ordinal, member in enumerate(bundle):
            if ordinal >= 16:
                raise ValueError("Archive has too many members")
            name = member.name.removeprefix("./")
            if member.isdir() and name in (".", "adapter", "adapter/"):
                continue
            name = name.removeprefix("adapter/")
            if name not in allowed or name in seen or not member.isfile():
                raise ValueError("Invalid archive member")
            if member.mode & 0o111:
                raise ValueError("Executable adapter file")
            total += member.size
            if member.size <= 0 or total > max_bytes:
                raise ValueError("Unpacked adapter exceeds budget")
            if name != "adapter_model.safetensors" and member.size > 1024 * 1024:
                raise ValueError("Oversized adapter metadata")
            if reserve:
                reserve(total)
            seen.add(name)
            source = bundle.extractfile(member)
            with source, (destination / name).open("xb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
    if not {"adapter_config.json", "adapter_model.safetensors"} <= seen:
        raise ValueError("Missing adapter files")
    return total


def validate_tensors(directory, spec, model_config):
    model_config = model_config.get("text_config", model_config)
    layer_count = model_config["num_hidden_layers"]
    expert_count = model_config.get(
        "n_routed_experts", model_config.get("num_local_experts", 0)
    )
    rank = spec["version"]["adapter"]["rank"]
    config = strict_json((directory / "adapter_config.json").read_bytes())
    if (
        config.get("peft_type") != "LORA"
        or config.get("r") != rank
        or config.get("bias", "none") != "none"
        or type(config.get("lora_alpha")) not in (int, float)
        or config["lora_alpha"] <= 0
        or any(
            config.get(key)
            for key in ("use_dora", "modules_to_save", "rank_pattern", "alpha_pattern")
        )
        or not isinstance(config.get("target_modules"), list)
        or not config["target_modules"]
        or any(
            not isinstance(module, str) or not module
            for module in config["target_modules"]
        )
    ):
        raise ValueError("Unsupported PEFT configuration")
    path = directory / "adapter_model.safetensors"
    with path.open("rb") as weights:
        prefix = weights.read(8)
        if len(prefix) != 8:
            raise ValueError("Invalid safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if not 0 < size <= 100_000_000:
            raise ValueError("Oversized safetensors header")
        header = strict_json(weights.read(size))
    tensor_bytes = path.stat().st_size - 8 - size
    offsets = []
    pairs = {}
    coverage = set()
    expert_coverage = {}
    expert_layouts = set()
    for name, tensor in header.items():
        if name == "__metadata__":
            continue
        match = re.fullmatch(
            r"(?:[a-zA-Z0-9_]+\.)*layers\.(\d+)\.(.+)\.lora_([AB])\.weight", name
        )
        if (
            not match
            or not isinstance(tensor, dict)
            or tensor.get("dtype") not in ("BF16", "F16", "F32")
        ):
            raise ValueError("Unsupported adapter tensor")
        layer, module, side = int(match[1]), match[2].split(".")[-1], match[3]
        if layer >= layer_count or module not in {
            target.split(".")[-1] for target in config["target_modules"]
        }:
            raise ValueError("Unexpected module or layer")
        shape = tensor["shape"]
        if len(shape) not in (2, 3) or any(
            type(dimension) is not int or not 0 < dimension <= 1_000_000
            for dimension in shape
        ):
            raise ValueError("Unsupported tensor shape")
        expert = re.search(r"(?:^|\.)experts\.(\d+)\.", match[2])
        fused = len(shape) == 3
        if expert or fused:
            expert_layouts.add("3d" if fused else "2d")
            if not expert_count:
                raise ValueError("Unexpected expert target")
            if fused:
                if shape[0] != expert_count:
                    raise ValueError("Fused expert count mismatch")
                expert_coverage.setdefault((layer, module), set()).update(
                    range(expert_count)
                )
            else:
                if int(expert[1]) >= expert_count:
                    raise ValueError("Expert index mismatch")
                expert_coverage.setdefault((layer, module), set()).add(int(expert[1]))
        if shape[-2 if side == "A" else -1] != rank:
            raise ValueError("Adapter rank mismatch")
        start, end = tensor["data_offsets"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= tensor_bytes
        ):
            raise ValueError("Invalid tensor offsets")
        width = 4 if tensor["dtype"] == "F32" else 2
        if end - start != width * shape[-2] * shape[-1] * (shape[0] if fused else 1):
            raise ValueError("Tensor byte count mismatch")
        offsets.append((start, end))
        pair = name.replace(f"lora_{side}", "lora")
        pairs.setdefault(pair, set()).add(side)
        coverage.add((layer, module))
    if (
        {layer for layer, _module in coverage} != set(range(layer_count))
        or not pairs
        or any(sides != {"A", "B"} for sides in pairs.values())
    ):
        raise ValueError("Incomplete adapter coverage")
    if any(indices != set(range(expert_count)) for indices in expert_coverage.values()):
        raise ValueError("Incomplete expert coverage")
    if len(expert_layouts) > 1:
        raise ValueError("Mixed expert layouts within one adapter")
    cursor = 0
    for start, end in sorted(offsets):
        if start != cursor:
            raise ValueError("Overlapping or missing tensor data")
        cursor = end
    if cursor != tensor_bytes:
        raise ValueError("Trailing tensor data")
    return tensor_bytes


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def has_fused_experts(directory):
    with (directory / "adapter_model.safetensors").open("rb") as weights:
        prefix = weights.read(8)
        if len(prefix) != 8:
            raise ValueError("Invalid safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if not 0 < size <= 100_000_000:
            raise ValueError("Oversized safetensors header")
        header = strict_json(weights.read(size))
    return any(
        len(tensor["shape"]) == 3
        for name, tensor in header.items()
        if name != "__metadata__"
    )


def materialize(
    spec, root, max_bytes, allowed_hosts, model_config, fetch=download, reserve=None
):
    version = spec["version"]
    name = f"ft-{version['id']}-{version['adapter']['sha256']}"
    destination = root / name
    verification = destination / ".verified.json"
    if verification.is_file():
        try:
            if verification.stat().st_size > 4096:
                raise ValueError("Oversized cache manifest")
            hashes = strict_json(verification.read_bytes())
            allowed = {
                "archive.tar.gz",
                "adapter_config.json",
                "adapter_model.safetensors",
                "README.md",
            }
            if (
                not {
                    "archive.tar.gz",
                    "adapter_config.json",
                    "adapter_model.safetensors",
                }
                <= set(hashes)
                or not set(hashes) <= allowed
                or hashes.get("archive.tar.gz") != spec["version"]["adapter"]["sha256"]
            ):
                raise ValueError("Invalid cached manifest")
            if any(
                file_hash(destination / filename) != digest
                for filename, digest in hashes.items()
            ):
                raise ValueError("Cached file integrity mismatch")
            disk_bytes = sum(path.stat().st_size for path in destination.iterdir())
            if disk_bytes > max_bytes:
                raise ValueError("Cached adapter exceeds disk budget")
            tensor_bytes = validate_tensors(destination, spec, model_config)
            return (
                destination,
                sum(path.stat().st_size for path in destination.iterdir()),
                tensor_bytes,
            )
        except (ValueError, KeyError, OSError, TypeError, AttributeError):
            shutil.rmtree(destination, ignore_errors=True)
    shutil.rmtree(destination, ignore_errors=True)
    staging = root / (name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    try:
        archive = staging / "archive.tar.gz"
        archive_size = spec["version"]["adapter"]["size_bytes"]
        if reserve:
            reserve(archive_size + 4096)
        fetch(spec, archive, allowed_hosts)
        if (
            archive.stat().st_size != spec["version"]["adapter"]["size_bytes"]
            or file_hash(archive) != spec["version"]["adapter"]["sha256"]
        ):
            raise ValueError("Archive integrity mismatch")
        extract(
            archive,
            staging,
            max_bytes - archive_size - 4096,
            reserve=(lambda unpacked: reserve(archive_size + unpacked + 4096))
            if reserve
            else None,
        )
        tensor_bytes = validate_tensors(staging, spec, model_config)
        hashes = {path.name: file_hash(path) for path in staging.iterdir()}
        (staging / ".verified.json").write_text(json.dumps(hashes))
        disk_bytes = sum(path.stat().st_size for path in staging.iterdir())
        shutil.rmtree(destination, ignore_errors=True)
        staging.rename(destination)
        return destination, disk_bytes, tensor_bytes
    finally:
        shutil.rmtree(staging, ignore_errors=True)
