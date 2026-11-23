import json
import shutil
import struct

from artifacts import file_hash, remaining, strict_json

FILE = "cartridge.safetensors"
FORMAT = "gradiated.cartridge/1"
PLACEMENT = "system_prompt_start"
DEFAULT_SEPARATOR = "\n\n"
MAX_HEADER_BYTES = 1024 * 1024
CHUNK_BYTES = 4 * 1024 * 1024
# A little-endian bf16 is infinite or NaN when its high byte has the low seven
# exponent bits set and its low byte has the eighth.
_EXPONENT_HIGH = bytes(int(value & 0x7F == 0x7F) for value in range(256))
_EXPONENT_LOW = bytes(int(value & 0x80 == 0x80) for value in range(256))


def finite_bf16(chunk):
    high = int.from_bytes(chunk[1::2].translate(_EXPONENT_HIGH))
    low = int.from_bytes(chunk[0::2].translate(_EXPONENT_LOW))
    return not high & low


def model_dimensions(model_config):
    model_config = model_config.get("text_config", model_config)
    hidden = model_config.get("hidden_size")
    vocab = model_config.get("vocab_size")
    context = model_config.get("max_position_embeddings")
    if any(type(value) is not int or value <= 0 for value in (hidden, vocab, context)):
        raise ValueError("Cartridges require pinned hidden, vocabulary and context sizes")
    return hidden, vocab, context


def validate_metadata(adapter, model_config):
    hidden, _vocab, context = model_dimensions(model_config)
    separator = adapter.get("separator")
    if (
        type(adapter.get("num_tokens")) is not int
        or not 0 < adapter["num_tokens"] < context
        or adapter.get("hidden_size") != hidden
        or adapter.get("placement") != PLACEMENT
        or not isinstance(separator, str)
        or len(separator) > 64
        or type(adapter.get("has_slot_token_ids")) is not bool
    ):
        raise ValueError("Incompatible cartridge")
    # DeepSeek V4 hashes token IDs (Engram), so serving needs the IDs the cartridge was trained behind.
    if not adapter["has_slot_token_ids"]:
        raise ValueError("Serving a cartridge requires slot_token_ids")


def read_header(path):
    with path.open("rb") as source:
        prefix = source.read(8)
        if len(prefix) != 8:
            raise ValueError("Invalid safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if not 0 < size <= MAX_HEADER_BYTES:
            raise ValueError("Invalid safetensors header")
        data = source.read(size)
    if len(data) != size:
        raise ValueError("Invalid safetensors header")
    return strict_json(data), 8 + size


def _tensor(header, name, dtype, shape):
    entry = header.get(name)
    if (
        not isinstance(entry, dict)
        or set(entry) != {"dtype", "shape", "data_offsets"}
        or entry["dtype"] != dtype
        or entry["shape"] != shape
        or not isinstance(entry["data_offsets"], list)
        or len(entry["data_offsets"]) != 2
        or any(type(offset) is not int or offset < 0 for offset in entry["data_offsets"])
    ):
        raise ValueError(f"Invalid cartridge tensor: {name}")
    start, end = entry["data_offsets"]
    width = 2 if dtype == "BF16" else 8
    count = 1
    for dimension in shape:
        count *= dimension
    if end - start != width * count:
        raise ValueError(f"Cartridge tensor size mismatch: {name}")
    return start, end


def validate_file(path, adapter, model_config, deadline=None):
    """Check a downloaded cartridge against its task version and the pinned model."""
    hidden, vocab, _context = model_dimensions(model_config)
    tokens = adapter["num_tokens"]
    header, data_start = read_header(path)
    metadata = header.pop("__metadata__", None)
    if (
        not isinstance(metadata, dict)
        or any(not isinstance(value, str) for value in metadata.values())
        or metadata.get("format") != FORMAT
        or metadata.get("placement", PLACEMENT) != PLACEMENT
        or metadata.get("separator", DEFAULT_SEPARATOR) != adapter["separator"]
    ):
        raise ValueError("Invalid cartridge metadata")
    expected = {"embeddings"} | ({"slot_token_ids"} if adapter["has_slot_token_ids"] else set())
    if set(header) != expected:
        raise ValueError("Unexpected cartridge tensors")
    spans = [_tensor(header, "embeddings", "BF16", [tokens, hidden])]
    if adapter["has_slot_token_ids"]:
        spans.append(_tensor(header, "slot_token_ids", "I64", [tokens]))
    cursor = 0
    for start, end in sorted(spans):
        if start != cursor:
            raise ValueError("Overlapping or missing cartridge data")
        cursor = end
    if data_start + cursor != path.stat().st_size:
        raise ValueError("Trailing cartridge data")

    with path.open("rb") as source:
        start, end = spans[0]
        source.seek(data_start + start)
        left = end - start
        while left:
            remaining(deadline)
            chunk = source.read(min(CHUNK_BYTES, left))
            if not chunk:
                raise ValueError("Truncated cartridge")
            left -= len(chunk)
            if len(chunk) % 2 or not finite_bf16(chunk):
                raise ValueError("Cartridge embeddings must be finite")
        if adapter["has_slot_token_ids"]:
            start, end = spans[1]
            source.seek(data_start + start)
            ids = struct.unpack(f"<{tokens}q", source.read(end - start))
            if any(not 0 <= token < vocab for token in ids):
                raise ValueError("Cartridge slot token outside the vocabulary")


def materialize(spec, root, max_bytes, allowed_hosts, model_config, fetch, reserve=None, deadline=None):
    """Download and verify one cartridge file; returns (directory, disk bytes)."""
    remaining(deadline)
    version = spec["version"]
    adapter = version["adapter"]
    validate_metadata(adapter, model_config)
    name = f"{version['id']}-{adapter['sha256']}"
    destination = root / name
    verification = destination / ".verified.json"
    if verification.is_file():
        try:
            if verification.stat().st_size > 4096:
                raise ValueError("Oversized cache manifest")
            hashes = strict_json(verification.read_bytes())
            if hashes != {FILE: adapter["sha256"]} or file_hash(destination / FILE, deadline) != adapter["sha256"]:
                raise ValueError("Cached cartridge integrity mismatch")
            if {path.name for path in destination.iterdir()} != {FILE, ".verified.json"}:
                raise ValueError("Unexpected cached cartridge files")
            validate_file(destination / FILE, adapter, model_config, deadline)
            return destination, sum(path.stat().st_size for path in destination.iterdir())
        except TimeoutError:
            raise
        except (ValueError, KeyError, OSError, TypeError, AttributeError, struct.error):
            shutil.rmtree(destination, ignore_errors=True)
    shutil.rmtree(destination, ignore_errors=True)
    staging = root / (name + ".partial")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    try:
        if adapter["size_bytes"] + 4096 > max_bytes:
            raise ValueError("Cartridge exceeds disk budget")
        if reserve:
            reserve(adapter["size_bytes"] + 4096)
        path = staging / FILE
        fetch(spec, path, allowed_hosts)
        if path.stat().st_size != adapter["size_bytes"] or file_hash(path, deadline) != adapter["sha256"]:
            raise ValueError("Cartridge integrity mismatch")
        try:
            validate_file(path, adapter, model_config, deadline)
        except struct.error:
            raise ValueError("Invalid cartridge") from None
        (staging / ".verified.json").write_text(json.dumps({FILE: adapter["sha256"]}))
        disk_bytes = sum(item.stat().st_size for item in staging.iterdir())
        remaining(deadline)
        staging.rename(destination)
        return destination, disk_bytes
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def resolved_files(directory, adapter):
    return {
        "kind": "cartridge",
        "path": str(directory / FILE),
        "sha256": adapter["sha256"],
        "num_tokens": adapter["num_tokens"],
    }
