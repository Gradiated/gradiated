#!/usr/bin/env python3
import hashlib
import json
import pathlib
import shutil

P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[1]
SOURCES = {
    "binding": P / "EVIDENCE_BINDING.json",
    "trace_packet": ROOT / "projects/gemma_exact_cache_trace_contract/TRACE_PACKET.json",
    "trace_terminal": ROOT / "projects/gemma_exact_cache_trace_contract/TRACE_TERMINAL.json",
    "launch": ROOT / "projects/gemma4_h200_ngram_decode_equivalent_production_validation/artifacts/quality-final-20260724t1304z/ngram-launch.json",
}

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out = P / "consumer_v2"
    out.mkdir(exist_ok=True)
    records = {}
    for name, source in SOURCES.items():
        target = out / source.name
        if not target.exists():
            shutil.copyfile(source, target)
            target.chmod(0o444)
        records[name] = {"file": target.name, "bytes": target.stat().st_size, "sha256": digest(target)}
    packet = json.loads((out / "TRACE_PACKET.json").read_text())
    binding = json.loads((out / "EVIDENCE_BINDING.json").read_text())
    frozen = {
        "kind": "immutable_ngram_sustainable_cost_consumer",
        "files": records,
        "model": binding["model"],
        "runtime": binding["runtime"],
        "arrival_rate_requests_per_second": binding["economic_gate"]["fixed_arrival_rate_requests_per_second"],
        "arrival_spacing_seconds": binding["economic_gate"]["fixed_arrival_spacing_seconds"],
        "duration_seconds": 720,
        "primary_group": "primary_c1",
        "primary_prompt_tokens": binding["trace_contract"]["prompt_tokens"],
        "primary_output_tokens": binding["trace_contract"]["requested_output_tokens"],
        "cacheable_prompt_share": binding["trace_contract"]["maximum_cacheable_prompt_fraction"],
        "separate_10k": packet["separate_10k_stream"],
    }
    data = json.dumps(frozen, indent=2, sort_keys=True).encode() + b"\n"
    path = P / "IMMUTABLE_CONSUMER_v2.json"
    path.write_bytes(data)
    path.chmod(0o444)
    print(json.dumps({"path": str(path), "sha256": digest(path), "bytes": len(data)}, sort_keys=True))

if __name__ == "__main__": main()
