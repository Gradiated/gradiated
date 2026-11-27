import concurrent.futures
import hashlib
import http.client
import json
import logging
import math
import re
import shutil
import struct
import tarfile
import time
import urllib.error
import urllib.parse
from socket import gaierror
from ssl import SSLEOFError


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


def remaining(deadline):
    if deadline is None:
        return 60
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Cold adapter deadline exceeded")
    return seconds


def download(spec, destination, allowed_hosts, deadline=None):
    url = urllib.parse.urlsplit(spec["download"]["url"])
    if (
        url.scheme != "https"
        or url.hostname not in allowed_hosts
        or url.username
        or url.password
        or url.port not in (None, 443)
    ):
        raise ValueError("Untrusted artifact URL")
    if deadline is None:
        deadline = time.monotonic() + 60
    expected = spec["version"]["adapter"]["size_bytes"]
    with destination.open("wb") as output:
        output.truncate(expected)
    if expected < 8 * 1024 * 1024:
        _download_part(url, destination, 0, expected - 1, expected, deadline)
    else:
        part_bytes = (expected + 7) // 8
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(
                pool.map(
                    lambda bounds: _download_part(
                        url, destination, *bounds, expected, deadline
                    ),
                    [
                        (start, min(start + part_bytes, expected) - 1)
                        for start in range(0, expected, part_bytes)
                    ],
                )
            )
    if file_hash(destination, deadline) != spec["version"]["adapter"]["sha256"]:
        raise ValueError("Archive integrity mismatch")


def _download_part(url, destination, start, end, total, deadline):
    whole = start == 0 and end == total - 1
    with destination.open("r+b") as output:
        output.seek(start)
        for attempt in range(12):
            attempt_deadline = min(deadline, time.monotonic() + 5)
            offset = output.tell()
            connection = http.client.HTTPSConnection(
                url.hostname, timeout=remaining(attempt_deadline)
            )
            try:
                connection.connect()
                socket = connection.sock
                socket.settimeout(remaining(attempt_deadline))
                path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
                headers = (
                    {"Range": f"bytes={offset}-{end}"} if offset or not whole else {}
                )
                connection.request("GET", path, headers=headers)
                socket.settimeout(remaining(attempt_deadline))
                with connection.getresponse() as response:
                    if response.status == 206:
                        if (
                            not headers
                            or response.getheader("Content-Range")
                            != f"bytes {offset}-{end}/{total}"
                        ):
                            raise ValueError("Invalid artifact range response")
                    elif response.status == 200:
                        if not whole:
                            raise ValueError("Artifact server ignored byte range")
                        output.seek(0)
                        offset = 0
                    else:
                        raise urllib.error.HTTPError(
                            f"https://{url.hostname}",
                            response.status,
                            "Artifact request failed",
                            {},
                            None,
                        )
                    while not response.isclosed():
                        socket.settimeout(remaining(attempt_deadline))
                        chunk = response.read1(1024 * 1024)
                        remaining(attempt_deadline)
                        if not chunk:
                            break
                        after = output.tell() + len(chunk)
                        if after > end + 1:
                            raise ValueError("Archive exceeds declared size")
                        output.write(chunk)
                if output.tell() != end + 1:
                    raise ConnectionError(
                        "Artifact response ended before its declared size"
                    )
                return
            except (TimeoutError, gaierror, ConnectionError, SSLEOFError) as error:
                if attempt == 11 or time.monotonic() >= deadline:
                    raise
                reason = "connection"
                if isinstance(error, TimeoutError):
                    reason = "timeout"
                elif isinstance(error, gaierror):
                    reason = "dns"
                logging.getLogger(__name__).warning(
                    json.dumps({"event": "lora_download_retry", "reason": reason})
                )
                if reason != "timeout":
                    time.sleep(min(1, remaining(deadline)))
            finally:
                connection.close()


ADAPTER_FILES = ("adapter_config.json", "adapter_model.safetensors")
LARGE_FILES = {"adapter_model.safetensors", "cartridge.safetensors"}
GRAD_BUNDLE = "grad.artifact/1"
GRAD_RESERVED = ("manifest.json", "eval_report.json")


def is_grad_bundle(adapter):
    source = adapter.get("source")
    return (
        isinstance(source, dict)
        and source.get("kind") == "grad"
        and source.get("bundle") == GRAD_BUNDLE
    )


def verify_grad_manifest(directory, payload, adapter_format, deadline=None):
    """Checks an extracted grad.artifact/1 bundle, then removes its envelope files."""
    manifest = strict_json((directory / "manifest.json").read_bytes())
    files = manifest.get("files")
    if (
        manifest.get("schema") != GRAD_BUNDLE
        or manifest.get("kind") != "final"
        or manifest.get("format") != adapter_format
        or manifest.get("format_version") != 1
        or not isinstance(files, dict)
        or set(files) != set(payload)
    ):
        raise ValueError("Invalid artifact bundle manifest")
    for name, digest in files.items():
        if file_hash(directory / name, deadline) != digest:
            raise ValueError("Artifact bundle file integrity mismatch")
    report = directory / "eval_report.json"
    if report.exists() != ("eval_report_sha256" in manifest) or (
        report.exists() and file_hash(report, deadline) != manifest["eval_report_sha256"]
    ):
        raise ValueError("Invalid artifact bundle evaluation report")
    for name in GRAD_RESERVED:
        (directory / name).unlink(missing_ok=True)


def extract(
    archive,
    destination,
    max_bytes,
    reserve=None,
    deadline=None,
    *,
    payload=ADAPTER_FILES,
    grad=False,
    adapter_format="peft_lora",
):
    allowed = set(payload) | (set(GRAD_RESERVED) if grad else {"README.md"})
    seen = set()
    total = 0
    with tarfile.open(archive, "r:gz") as bundle:
        for ordinal, member in enumerate(bundle):
            remaining(deadline)
            if ordinal >= 16:
                raise ValueError("Archive has too many members")
            name = member.name.removeprefix("./")
            if not grad:
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
            if name not in LARGE_FILES and member.size > 1024 * 1024:
                raise ValueError("Oversized adapter metadata")
            if reserve:
                reserve(total)
            seen.add(name)
            source = bundle.extractfile(member)
            with source, (destination / name).open("xb") as output:
                while True:
                    remaining(deadline)
                    chunk = source.read(1024 * 1024)
                    remaining(deadline)
                    if not chunk:
                        break
                    output.write(chunk)
                    remaining(deadline)
    if not set(payload) <= seen or (grad and "manifest.json" not in seen):
        raise ValueError("Missing adapter files")
    if grad:
        verify_grad_manifest(destination, payload, adapter_format, deadline)
    return total


def validate_tensors(
    directory, spec, model_config, deadline=None, *, allowed_target_modules=None
):
    remaining(deadline)
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
        remaining(deadline)
    tensor_bytes = path.stat().st_size - 8 - size
    offsets = []
    pairs = {}
    coverage = set()
    expert_coverage = {}
    expert_layouts = set()
    head_sides = set()
    for name, tensor in header.items():
        remaining(deadline)
        if name == "__metadata__":
            continue
        match = re.fullmatch(
            r"(?:[a-zA-Z0-9_]+\.)*layers\.(\d+)\.(.+)\.lora_([AB])\.weight", name
        )
        head = re.fullmatch(
            r"(?:base_model\.model\.)?lm_head\.lora_([AB])\.weight", name
        )
        if (
            not (match or head)
            or not isinstance(tensor, dict)
            or tensor.get("dtype") not in ("BF16", "F16", "F32")
        ):
            raise ValueError("Unsupported adapter tensor")
        if head:
            layer, module, side = None, "lm_head", head[1]
            if (
                "lm_head" not in config["target_modules"]
                or not isinstance(allowed_target_modules, (list, tuple, set, frozenset))
                or "lm_head" not in allowed_target_modules
            ):
                raise ValueError("Head target is not declared and host-allowed")
            if config.get("fan_in_fan_out") or config.get("use_rslora"):
                raise ValueError("Unsupported head LoRA parameterization")
        else:
            layer, module, side = int(match[1]), match[2].split(".")[-1], match[3]
        if (
            not head and (layer >= layer_count or module == "lm_head")
        ) or module not in {target.split(".")[-1] for target in config["target_modules"]}:
            raise ValueError("Unexpected module or layer")
        shape = tensor["shape"]
        if len(shape) not in (2, 3) or any(
            type(dimension) is not int or not 0 < dimension <= 1_000_000
            for dimension in shape
        ):
            raise ValueError("Unsupported tensor shape")
        if head:
            hidden = model_config.get("hidden_size")
            vocab = model_config.get("vocab_size")
            if any(type(value) is not int or value <= 0 for value in (hidden, vocab)):
                raise ValueError("Head requires pinned hidden and vocabulary dimensions")
            if shape != ([rank, hidden] if side == "A" else [vocab, rank]):
                raise ValueError("Head tensor shape mismatch")
            if side in head_sides:
                raise ValueError("Duplicate head tensor")
            head_sides.add(side)
        expert = None if head else re.search(r"(?:^|\.)experts\.(\d+)\.", match[2])
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
    if not pairs or any(sides != {"A", "B"} for sides in pairs.values()):
        raise ValueError("Incomplete adapter coverage")
    if {target.split(".")[-1] for target in config["target_modules"]} - {
        module for _layer, module in coverage
    }:
        raise ValueError("Adapter target modules have no tensors")
    if any(indices != set(range(expert_count)) for indices in expert_coverage.values()):
        raise ValueError("Incomplete expert coverage")
    if len(expert_layouts) > 1:
        raise ValueError("Mixed expert layouts within one adapter")
    cursor = 0
    for start, end in sorted(offsets):
        remaining(deadline)
        if start != cursor:
            raise ValueError("Overlapping or missing tensor data")
        cursor = end
    if cursor != tensor_bytes:
        raise ValueError("Trailing tensor data")
    return tensor_bytes


def file_hash(path, deadline=None):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            remaining(deadline)
            chunk = source.read(1024 * 1024)
            remaining(deadline)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


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


def cache_key(version):
    return f"{version['id']}-{version['adapter']['sha256']}"


def materialize(
    spec,
    root,
    max_bytes,
    allowed_hosts,
    model_config,
    fetch=download,
    reserve=None,
    deadline=None,
    allowed_target_modules=None,
):
    remaining(deadline)
    version = spec["version"]
    name = cache_key(version)
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
                file_hash(destination / filename, deadline) != digest
                for filename, digest in hashes.items()
            ):
                raise ValueError("Cached file integrity mismatch")
            disk_bytes = sum(path.stat().st_size for path in destination.iterdir())
            if disk_bytes > max_bytes:
                raise ValueError("Cached adapter exceeds disk budget")
            tensor_bytes = validate_tensors(
                destination,
                spec,
                model_config,
                deadline,
                allowed_target_modules=allowed_target_modules,
            )
            return (
                destination,
                sum(path.stat().st_size for path in destination.iterdir()),
                tensor_bytes,
            )
        except TimeoutError:
            raise
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
            or file_hash(archive, deadline) != spec["version"]["adapter"]["sha256"]
        ):
            raise ValueError("Archive integrity mismatch")
        extract(
            archive,
            staging,
            max_bytes - archive_size - 4096,
            reserve=(lambda unpacked: reserve(archive_size + unpacked + 4096))
            if reserve
            else None,
            deadline=deadline,
            grad=is_grad_bundle(spec["version"]["adapter"]),
        )
        tensor_bytes = validate_tensors(
            staging,
            spec,
            model_config,
            deadline,
            allowed_target_modules=allowed_target_modules,
        )
        hashes = {path.name: file_hash(path, deadline) for path in staging.iterdir()}
        (staging / ".verified.json").write_text(json.dumps(hashes))
        disk_bytes = sum(path.stat().st_size for path in staging.iterdir())
        shutil.rmtree(destination, ignore_errors=True)
        remaining(deadline)
        staging.rename(destination)
        return destination, disk_bytes, tensor_bytes
    finally:
        shutil.rmtree(staging, ignore_errors=True)
