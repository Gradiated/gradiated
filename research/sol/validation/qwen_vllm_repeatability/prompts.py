from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


@dataclass(frozen=True)
class PromptRecord:
    request_id: str
    prompt: str
    prompt_sha256: str
    input_tokens: int
    output_tokens: int

    def identity_mapping(self) -> dict:
        value = asdict(self)
        value.pop("prompt")
        return value


@dataclass(frozen=True)
class PromptManifest:
    schema_version: int
    generator: str
    generator_revision: str
    seed: int
    requests: tuple[PromptRecord, ...]
    content_id: str

    def to_mapping(self, include_prompts: bool = True) -> dict:
        requests = (
            [asdict(request) for request in self.requests]
            if include_prompts
            else [request.identity_mapping() for request in self.requests]
        )
        return {
            "schema_version": self.schema_version,
            "generator": self.generator,
            "generator_revision": self.generator_revision,
            "seed": self.seed,
            "requests": requests,
            "content_id": self.content_id,
        }


def build_prompt_manifest(
    prompts: Iterable[tuple[str, int, int]], seed: int, generator_revision: str
) -> PromptManifest:
    requests = tuple(
        PromptRecord(
            request_id=f"qwen-fixed-{index}",
            prompt=prompt,
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        for index, (prompt, input_tokens, output_tokens) in enumerate(prompts)
    )
    identity = {
        "schema_version": 1,
        "generator": "vllm-random-dataset-frozen-jsonl",
        "generator_revision": generator_revision,
        "seed": seed,
        "requests": [asdict(request) for request in requests],
    }
    return PromptManifest(
        schema_version=1,
        generator="vllm-random-dataset-frozen-jsonl",
        generator_revision=generator_revision,
        seed=seed,
        requests=requests,
        content_id=hashlib.sha256(_canonical_bytes(identity)).hexdigest(),
    )


def generate_vllm_prompt_manifest(
    model_path: Path,
    seed: int,
    generator_revision: str,
    num_prompts: int,
    input_tokens: int,
    output_tokens: int,
) -> PromptManifest:
    from vllm.benchmarks.datasets import RandomDataset
    from vllm.tokenizers import get_tokenizer

    tokenizer = get_tokenizer(model_path, trust_remote_code=False)
    sampled = RandomDataset(random_seed=seed, disable_shuffle=True).sample(
        tokenizer=tokenizer,
        num_requests=num_prompts,
        request_id_prefix="qwen-fixed-",
        prefix_len=0,
        range_ratio=0.0,
        input_len=input_tokens,
        output_len=output_tokens,
    )
    prompts = [
        (str(request.prompt), request.prompt_len, int(request.expected_output_len or 0))
        for request in sampled
    ]
    manifest = build_prompt_manifest(prompts, seed, generator_revision)
    if len(manifest.requests) != num_prompts or any(
        request.input_tokens != input_tokens or request.output_tokens != output_tokens
        for request in manifest.requests
    ):
        raise ValueError("generated prompts do not match the frozen geometry")
    return manifest


def write_prompt_fixture(manifest: PromptManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"output_tokens": request.output_tokens, "prompt": request.prompt},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for request in manifest.requests
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
