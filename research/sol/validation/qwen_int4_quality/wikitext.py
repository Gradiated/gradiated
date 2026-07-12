from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .provenance import tokenizer_identity


@dataclass(frozen=True)
class SelectedTokenWindow:
    source_row_index: int
    selection_sha256: str
    prompt: str
    completion: str


@dataclass(frozen=True)
class SequentialTokenWindow:
    window_index: int
    prompt_start_token: int
    target_start_token: int
    token_ids_sha256: str
    prompt: str
    completion: str


def select_token_windows(
    rows: Iterable[str],
    tokenizer: Any,
    *,
    example_count: int,
    context_tokens: int,
    target_tokens: int,
    selection_seed: str,
) -> tuple[tuple[SelectedTokenWindow, ...], int]:
    if example_count <= 0 or context_tokens <= 0 or target_tokens <= 0:
        raise ValueError("example, context, and target token counts must be positive")
    window_tokens = context_tokens + target_tokens
    eligible: list[SelectedTokenWindow] = []
    for index, text in enumerate(rows):
        if not text.strip() or text.lstrip().startswith("="):
            continue
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        if len(token_ids) < window_tokens:
            continue
        prompt = tokenizer.decode(
            token_ids[:context_tokens],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        completion = tokenizer.decode(
            token_ids[context_tokens:window_tokens],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        roundtrip_target_tokens = tokenizer.encode(completion, add_special_tokens=False)
        if len(roundtrip_target_tokens) != target_tokens:
            continue
        selection_sha256 = hashlib.sha256(
            f"{selection_seed}\0{index}\0{text}".encode("utf-8")
        ).hexdigest()
        eligible.append(
            SelectedTokenWindow(
                source_row_index=index,
                selection_sha256=selection_sha256,
                prompt=prompt,
                completion=completion,
            )
        )
    eligible.sort(key=lambda window: window.selection_sha256)
    if len(eligible) < example_count:
        raise ValueError(
            f"only {len(eligible)} eligible WikiText rows for {example_count} examples"
        )
    return tuple(eligible[:example_count]), len(eligible)


def select_sequential_token_windows(
    rows: Iterable[str],
    tokenizer: Any,
    *,
    example_count: int,
    context_tokens: int,
    target_tokens: int,
) -> tuple[tuple[SequentialTokenWindow, ...], int, str]:
    if example_count <= 0 or context_tokens <= 0 or target_tokens <= 0:
        raise ValueError("example, context, and target token counts must be positive")
    stream = "\n\n".join(rows)
    stream_sha256 = hashlib.sha256(stream.encode("utf-8")).hexdigest()
    stream_token_ids = tokenizer.encode(stream, add_special_tokens=False)
    required_tokens = context_tokens + example_count * target_tokens
    if len(stream_token_ids) < required_tokens:
        raise ValueError(
            f"WikiText stream has {len(stream_token_ids)} tokens; {required_tokens} required"
        )
    windows: list[SequentialTokenWindow] = []
    for index in range(example_count):
        prompt_start = index * target_tokens
        target_start = prompt_start + context_tokens
        target_end = target_start + target_tokens
        prompt_ids = stream_token_ids[prompt_start:target_start]
        target_ids = stream_token_ids[target_start:target_end]
        prompt = tokenizer.decode(
            prompt_ids,
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        completion = tokenizer.decode(
            target_ids,
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
        if len(tokenizer.encode(completion, add_special_tokens=False)) != target_tokens:
            raise ValueError(
                f"target token roundtrip changed at sequential window {index}"
            )
        token_ids_sha256 = hashlib.sha256(
            ",".join(str(token_id) for token_id in prompt_ids + target_ids).encode(
                "utf-8"
            )
        ).hexdigest()
        windows.append(
            SequentialTokenWindow(
                window_index=index,
                prompt_start_token=prompt_start,
                target_start_token=target_start,
                token_ids_sha256=token_ids_sha256,
                prompt=prompt,
                completion=completion,
            )
        )
    return tuple(windows), len(stream_token_ids), stream_sha256


def build_corpus_document(
    manifest: dict[str, object],
    windows: tuple[SelectedTokenWindow, ...],
    *,
    eligible_row_count: int,
) -> dict[str, object]:
    source = _object(manifest, "source")
    generation = dict(_object(manifest, "generation"))
    tokenizer = _object(manifest, "tokenizer")
    expected_example_count = int(generation.get("example_count", 0))
    target_tokens_per_example = int(generation.get("target_tokens_per_example", 0))
    if expected_example_count != len(windows):
        raise ValueError("selected window count does not match the manifest")
    if target_tokens_per_example <= 0:
        raise ValueError("target_tokens_per_example must be positive")
    generation["eligible_row_count"] = eligible_row_count
    generation["selected_row_indices"] = [window.source_row_index for window in windows]
    generation["selected_row_sha256"] = [window.selection_sha256 for window in windows]
    return {
        "schema_version": "inference-foundry.corpus.v2",
        "kind": "held_out_language_modeling_subset",
        "description": "Deterministic token-window subset of the pinned WikiText-2 raw test split for teacher-forced quality proxies.",
        "task": "teacher_forced_next_token_prediction",
        "is_standard_benchmark": False,
        "source": source,
        "generation": generation,
        "tokenizer": tokenizer,
        "expected_example_count": expected_example_count,
        "expected_target_tokens": expected_example_count * target_tokens_per_example,
        "examples": [
            {
                "id": f"wikitext-test-row-{window.source_row_index:04d}",
                "prompt": window.prompt,
                "completion": window.completion,
            }
            for window in windows
        ],
    }


def build_sequential_corpus_document(
    manifest: dict[str, object],
    windows: tuple[SequentialTokenWindow, ...],
    *,
    dataset_row_count: int,
    stream_token_count: int,
    stream_text_sha256: str,
) -> dict[str, object]:
    source = _object(manifest, "source")
    generation = dict(_object(manifest, "generation"))
    tokenizer = _object(manifest, "tokenizer")
    expected_example_count = int(generation.get("example_count", 0))
    target_tokens_per_example = int(generation.get("target_tokens_per_example", 0))
    if expected_example_count != len(windows):
        raise ValueError("selected window count does not match the manifest")
    if target_tokens_per_example <= 0:
        raise ValueError("target_tokens_per_example must be positive")
    generation["dataset_row_count"] = dataset_row_count
    generation["stream_token_count"] = stream_token_count
    generation["stream_text_sha256"] = stream_text_sha256
    generation["prompt_start_tokens"] = [
        window.prompt_start_token for window in windows
    ]
    generation["target_start_tokens"] = [
        window.target_start_token for window in windows
    ]
    generation["window_token_ids_sha256"] = [
        window.token_ids_sha256 for window in windows
    ]
    return {
        "schema_version": "inference-foundry.corpus.v2",
        "kind": "held_out_sequential_language_modeling_subset",
        "description": "Deterministic contiguous target windows from the pinned WikiText-2 raw test token stream for teacher-forced quality proxies.",
        "task": "teacher_forced_next_token_prediction",
        "is_standard_benchmark": False,
        "source": source,
        "generation": generation,
        "tokenizer": tokenizer,
        "expected_example_count": expected_example_count,
        "expected_target_tokens": expected_example_count * target_tokens_per_example,
        "examples": [
            {
                "id": f"wikitext-test-token-{window.target_start_token:06d}",
                "prompt": window.prompt,
                "completion": window.completion,
            }
            for window in windows
        ],
    }


def serialize_corpus(document: dict[str, object]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate_corpus(manifest_path: Path, model_path: Path) -> dict[str, object]:
    manifest = _load_manifest(manifest_path)
    source = _object(manifest, "source")
    generation = _object(manifest, "generation")
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from datasets import load_dataset
    from transformers import AutoTokenizer

    dataset = load_dataset(
        str(source["dataset_id"]),
        str(source["dataset_config"]),
        split=str(source["split"]),
    )
    fingerprint = str(getattr(dataset, "_fingerprint", ""))
    if fingerprint != str(source["dataset_fingerprint"]):
        raise ValueError(
            f"dataset fingerprint mismatch: expected {source['dataset_fingerprint']}, measured {fingerprint}"
        )
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    actual_tokenizer = tokenizer_identity(model_path, tokenizer)
    _validate_tokenizer(_object(manifest, "tokenizer"), actual_tokenizer)
    mode = str(generation.get("mode", "hash_ranked_rows"))
    if mode == "sequential_stream":
        sequential_windows, stream_token_count, stream_text_sha256 = (
            select_sequential_token_windows(
                dataset["text"],
                tokenizer,
                example_count=int(generation["example_count"]),
                context_tokens=int(generation["context_tokens_per_example"]),
                target_tokens=int(generation["target_tokens_per_example"]),
            )
        )
        document = build_sequential_corpus_document(
            manifest,
            sequential_windows,
            dataset_row_count=len(dataset),
            stream_token_count=stream_token_count,
            stream_text_sha256=stream_text_sha256,
        )
    elif mode == "hash_ranked_rows":
        windows, eligible_row_count = select_token_windows(
            dataset["text"],
            tokenizer,
            example_count=int(generation["example_count"]),
            context_tokens=int(generation["context_tokens_per_example"]),
            target_tokens=int(generation["target_tokens_per_example"]),
            selection_seed=str(generation["selection_seed"]),
        )
        document = build_corpus_document(
            manifest,
            windows,
            eligible_row_count=eligible_row_count,
        )
    else:
        raise ValueError(f"unsupported WikiText generation mode: {mode}")
    serialized = serialize_corpus(document)
    corpus_sha256 = hashlib.sha256(serialized).hexdigest()
    if mode == "sequential_stream":
        _validate_sequential_expectations(
            manifest,
            dataset_row_count=len(dataset),
            stream_token_count=stream_token_count,
            stream_text_sha256=stream_text_sha256,
            windows=sequential_windows,
            target_tokens=int(document["expected_target_tokens"]),
            corpus_sha256=corpus_sha256,
        )
    else:
        _validate_expectations(
            manifest,
            dataset_row_count=len(dataset),
            eligible_row_count=eligible_row_count,
            windows=windows,
            target_tokens=int(document["expected_target_tokens"]),
            corpus_sha256=corpus_sha256,
        )
    repo_root = manifest_path.resolve().parents[2]
    output_path = repo_root / str(manifest["generated_corpus_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(serialized)
    return {
        "output": str(output_path),
        "corpus_sha256": corpus_sha256,
        "dataset_fingerprint": fingerprint,
        "example_count": int(document["expected_example_count"]),
        "target_tokens": document["expected_target_tokens"],
    }


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"WikiText manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid WikiText manifest: {path}") from error
    if not isinstance(value, dict):
        raise ValueError("WikiText manifest must be an object")
    if value.get("schema_version") != "inference-foundry.wikitext-corpus-manifest.v1":
        raise ValueError("unsupported WikiText manifest schema")
    return value


def _validate_tokenizer(
    expected: dict[str, object],
    actual: dict[str, object],
) -> None:
    for field in ("class", "vocab_size"):
        if expected.get(field) != actual.get(field):
            raise ValueError(f"tokenizer {field} does not match the manifest")
    actual_files = {
        str(value.get("name")): str(value.get("sha256"))
        for value in actual.get("files", [])
        if isinstance(value, dict)
    }
    for value in expected.get("files", []):
        if not isinstance(value, dict):
            raise ValueError("manifest tokenizer files must contain objects")
        name = str(value.get("name", ""))
        if actual_files.get(name) != str(value.get("sha256", "")):
            raise ValueError(f"tokenizer file does not match the manifest: {name}")


def _validate_expectations(
    manifest: dict[str, object],
    *,
    dataset_row_count: int,
    eligible_row_count: int,
    windows: tuple[SelectedTokenWindow, ...],
    target_tokens: int,
    corpus_sha256: str,
) -> None:
    expected = _object(manifest, "expected")
    measured = {
        "dataset_row_count": dataset_row_count,
        "eligible_row_count": eligible_row_count,
        "selected_row_indices": [window.source_row_index for window in windows],
        "target_tokens": target_tokens,
        "generated_corpus_sha256": corpus_sha256,
    }
    for field, value in measured.items():
        if expected.get(field) != value:
            raise ValueError(
                f"generated corpus {field} mismatch: expected {expected.get(field)}, measured {value}"
            )


def _validate_sequential_expectations(
    manifest: dict[str, object],
    *,
    dataset_row_count: int,
    stream_token_count: int,
    stream_text_sha256: str,
    windows: tuple[SequentialTokenWindow, ...],
    target_tokens: int,
    corpus_sha256: str,
) -> None:
    expected = _object(manifest, "expected")
    measured = {
        "dataset_row_count": dataset_row_count,
        "stream_token_count": stream_token_count,
        "stream_text_sha256": stream_text_sha256,
        "target_start_tokens": [window.target_start_token for window in windows],
        "target_tokens": target_tokens,
        "generated_corpus_sha256": corpus_sha256,
    }
    for field, value in measured.items():
        if expected.get(field) != value:
            raise ValueError(
                f"generated corpus {field} mismatch: expected {expected.get(field)}, measured {value}"
            )


def _object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"manifest {key} must be an object")
    return value


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the pinned held-out WikiText-2 quality corpus from the local cache."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args(arguments)
    result = generate_corpus(args.manifest, args.model)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
