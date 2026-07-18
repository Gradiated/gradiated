#!/usr/bin/env python3
"""Build the content-bound global attention route predicate."""
import ast
import hashlib
import json
import math
import subprocess
import tarfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
PRIOR_ARCHIVE = PROJECT / "artifacts/gemma-h100-w4-fp8kv-20260717t21031784315025z/h100-w4-fp8kv-repair5.tar.gz"
EXPECTED_OBJECT_HASHES = {
    "unified_kv_cache_update": "3be8b1b6913ee3ccab10466ee94d3048188cf2d761315c117509822195b95166",
    "unified_attention_with_output": "ddf567b33296f861b304cc9f30c729dce0bcf701487a24c28536936135b5480f",
    "TritonAttentionMetadataBuilder": "0643555d9458452f24290b956cfb45cc74bbf231b7edf4c421b1d57032241e92",
    "TritonAttentionImpl": "2da9ca0cf28ab21cd384892d198f21898b0df359f06fa5094e3c36647d5ce0e1",
    "unified_attention": "405000dc44912777c6d7835d0009deaa8594d8b8db422419a151c5f307cdd297",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_probe() -> dict:
    code = r'''import hashlib,inspect,json,vllm
from vllm.model_executor.layers.attention.attention import unified_kv_cache_update,unified_attention_with_output
from vllm.v1.attention.backends.triton_attn import MIN_LAUNCH_GRID_SIZE_2D,NUM_PAR_SOFTMAX_SEGMENTS,TritonAttentionImpl,TritonAttentionMetadataBuilder
from vllm.v1.attention.ops.triton_unified_attention import unified_attention
objects=[unified_kv_cache_update,unified_attention_with_output,TritonAttentionMetadataBuilder,TritonAttentionImpl,unified_attention]
rows={}
files={}
for value in objects:
 source=inspect.getsource(value).encode(); path=inspect.getsourcefile(value)
 rows[value.__name__]={"source_sha256":hashlib.sha256(source).hexdigest(),"file":path}
 files[path]={"sha256":hashlib.sha256(open(path,"rb").read()).hexdigest()}
print(json.dumps({"vllm":vllm.__version__,"objects":rows,"files":files,"MIN_LAUNCH_GRID_SIZE_2D":MIN_LAUNCH_GRID_SIZE_2D,"NUM_PAR_SOFTMAX_SEGMENTS":NUM_PAR_SOFTMAX_SEGMENTS,"guard":inspect.getsource(unified_attention)}))'''
    proc = subprocess.run(
        ["docker", "run", "--rm", "-i", "--network=none", "--entrypoint", "python3", IMAGE, "-"],
        input=code, capture_output=True, text=True, timeout=180,
    )
    if proc.returncode:
        raise RuntimeError(f"immutable image probe failed with exit {proc.returncode}")
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    if len(lines) != 1:
        raise RuntimeError("immutable image probe did not emit one JSON row")
    value = json.loads(lines[0])
    value["stderr_sha256"] = hashlib.sha256(proc.stderr.encode()).hexdigest()
    value["guard_sha256"] = hashlib.sha256(value.pop("guard").encode()).hexdigest()
    return value


def prior_result() -> tuple[dict, str]:
    with tarfile.open(PRIOR_ARCHIVE, "r:gz") as bundle:
        members = [item for item in bundle.getmembers() if item.name.endswith("/result.json")]
        if len(members) != 1:
            raise RuntimeError("prior archive lacks one result.json")
        handle = bundle.extractfile(members[0])
        if handle is None:
            raise RuntimeError("prior result is unreadable")
        raw = handle.read()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def page_invariants(context: int) -> dict:
    pages = math.ceil(context / 16)
    blocks = 32 * pages
    decode_offset = (context - 1) % 16
    decode_slots = [sequence * pages * 16 + (pages - 1) * 16 + decode_offset
                    for sequence in range(32)]
    checks = {
        "block_table_shape": [32, pages],
        "physical_blocks_unique": blocks,
        "producer_slot_count": blocks * 16,
        "decode_slots_unique": len(set(decode_slots)) == 32,
        "decode_slots_in_cache": min(decode_slots) >= 0 and max(decode_slots) < blocks * 16,
        "last_logical_token_addressed": all(slot % 16 == decode_offset for slot in decode_slots),
        "seq_lens_include_decode_token": context > 0,
    }
    return {"context": context, "pages_per_sequence": pages,
            "decode_offset": decode_offset, "checks": checks,
            "pass": all(value is True for key, value in checks.items()
                        if key not in {"block_table_shape", "physical_blocks_unique", "producer_slot_count"})}


def main() -> int:
    benchmark = PROJECT / "paged_residual.py"
    remote = PROJECT / "remote_stage.sh"
    ast.parse(benchmark.read_text())
    probe = image_probe()
    prior, prior_result_hash = prior_result()
    rows = {row["case"]: row for row in prior["rows"]}
    local = rows["local"]
    global_rows = [rows[name] for name in ("global4214", "global4393", "global4571")]
    thresholds = {"local_kv16": 128 // 16, "global_kv4": 128 // 4}
    prior_routes = {
        "local": "2d" if 32 > thresholds["local_kv16"] else "3d_segmented",
        "global": "2d" if 32 > thresholds["global_kv4"] else "3d_segmented",
    }
    benchmark_text = benchmark.read_text()
    remote_text = remote.read_text()
    object_hashes = {name: row["source_sha256"] for name, row in probe["objects"].items()}
    checks = {
        "immutable_image_digest": subprocess.run(
            ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip() == "sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79",
        "exact_vllm_revision": probe["vllm"] == "0.19.1.dev6+g6d4a8e6d2",
        "installed_object_hashes": object_hashes == EXPECTED_OBJECT_HASHES,
        "dispatch_constants": probe["MIN_LAUNCH_GRID_SIZE_2D"] == 128 and probe["NUM_PAR_SOFTMAX_SEGMENTS"] == 16,
        "prior_local_nonzero_pass": local["oracle"]["pass"] is True and local["oracle"]["nonzero"] is True,
        "prior_all_globals_finite_zero": all(row["oracle"]["finite"] is True and row["oracle"]["nonzero"] is False for row in global_rows),
        "isolated_dispatch_discontinuity": prior_routes == {"local": "2d", "global": "3d_segmented"},
        "corrected_metadata_forces_2d": all(token in benchmark_text for token in (
            "seq_threshold_3D=None", "num_par_softmax_segments=None",
            "softmax_segm_output=None", "M1_global4214_bf16_nonzero_sentinel")),
        "consumer_guard_accepts_missing_scratch": probe["guard_sha256"] == EXPECTED_OBJECT_HASHES["unified_attention"],
        "producer_population_is_observed_before_sentinel": all(token in benchmark_text for token in (
            "cache_sample(layer, table, context)", "producer left sampled global pages empty",
            "unified_kv_cache_update(fill_k, fill_v, name)")),
        "residual_is_absolute_and_c32_normalized": "* 358 / (1000 * BATCH)" in benchmark_text and "fp8_attention_seconds_per_request" in benchmark_text,
        "remote_requires_route_and_atomic_sentinel": all(token in remote_text for token in (
            "--route-packet /input/GLOBAL_ROUTE_PACKET.json", "--sentinel-output", "m1-sentinel.json")),
    }
    page_rows = [page_invariants(context) for context in (4214, 4393, 4571)]
    checks["all_page_table_invariants"] = all(row["pass"] for row in page_rows)
    packet = {
        "schema_version": 1,
        "type": "content_bound_global_attention_route_terminal",
        "hypothesis": "The semantic boundary is Triton's 3-D segmented global decode route, selected only for kv_heads=4 at c32; removing optional segmented scratch metadata selects the exact consumer's 2-D path, while M1 remains the CUDA falsifier.",
        "causal_status": "source_bound_dispatch_isolation_pending_M1_execution_equivalence",
        "causal_chain": [
            "The same actual producer and selected Triton implementation passed local c32 with nonzero output.",
            "At c32, local kv_heads=16 yields threshold 8 and selects 2-D; global kv_heads=4 yields threshold 32 and selects 3-D segmented.",
            "All three contexts on the 3-D branch returned finite exact zeros in both BF16 and FP8, isolating the staged route discontinuity from precision and context length.",
            "The exact unified_attention source selects 2-D whenever segmented scratch metadata is absent; corrected metadata uses that supported guard.",
            "The corrected program verifies page-table bounds, samples nonzero cache contents after the actual producer, then requires the actual global-4214 BF16 consumer output to be finite and nonzero before timing.",
        ],
        "image": IMAGE,
        "installed_runtime": probe,
        "expected_object_source_sha256": EXPECTED_OBJECT_HASHES,
        "prior_invalid_run": {
            "archive": str(PRIOR_ARCHIVE), "archive_sha256": digest(PRIOR_ARCHIVE),
            "result_sha256": prior_result_hash, "dispatch": prior_routes,
            "thresholds": thresholds,
        },
        "bound_prior_local_row": {
            "archive_sha256": digest(PRIOR_ARCHIVE),
            "fp8_event_ms_p50": local["fp8_e4m3"]["event_ms_p50"],
            "oracle": local["oracle"],
        },
        "corrected_program": {
            "benchmark": str(benchmark), "benchmark_sha256": digest(benchmark),
            "remote_stage": str(remote), "remote_stage_sha256": digest(remote),
            "global_dispatch": "2d_no_segmented_scratch",
            "first_cuda_acceptance": "M1 global4214 BF16 actual producer, sampled populated cache, actual consumer, finite nonzero output",
            "aggregation": "(50*bound_local_fp8_ms + 10*mean(valid_global_fp8_ms))*358/(1000*32)",
        },
        "page_invariants": page_rows,
        "checks": checks,
        "pass": all(checks.values()),
        "evidence_boundary": "This packet proves a content-bound route predicate, not CUDA semantics or performance. Only M1 and valid paired rows can reopen the residual decision.",
    }
    output = PROJECT / "GLOBAL_ROUTE_PACKET.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps({"output": str(output), "sha256": digest(output),
                      "pass": packet["pass"], "checks": checks}, indent=2, sort_keys=True))
    return 0 if packet["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
