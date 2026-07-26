from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time


SOURCE_SHA256 = {
    "detokenizer_manager": "3fe32c007e5a25517a61281565d191b18b007d26e4d16bf4af00cf21f96ca4e3",
    "tokenizer_manager": "c128e82824bad3d5aa6ae0f2da144c989bf5ce2f32502eb86b7e61b49eebab4d",
}


def _json(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return str(value)


def _append(row: dict) -> None:
    path = pathlib.Path(os.environ["TOKEN_TRACE_EVENTS"])
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(descriptor, (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _source_hash(module: object) -> str:
    return hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()


def install() -> None:
    if not os.environ.get("TOKEN_TRACE_EVENTS"):
        return
    from sglang.srt.managers import detokenizer_manager, tokenizer_manager

    observed = {
        "detokenizer_manager": _source_hash(detokenizer_manager),
        "tokenizer_manager": _source_hash(tokenizer_manager),
    }
    if observed != SOURCE_SHA256:
        raise RuntimeError(f"token trace source mismatch: {observed}")

    detokenizer = detokenizer_manager.DetokenizerManager
    if not getattr(detokenizer, "_ngram_trace_installed", False):
        original_detokenize = detokenizer.handle_batch_token_id_out

        def traced_detokenize(self, recv_obj):
            for index, rid in enumerate(recv_obj.rids):
                _append(
                    {
                        "stage": "scheduler_to_detokenizer",
                        "rid": rid,
                        "scheduler_output_ids_delta": list(recv_obj.output_ids[index]),
                        "completion_counter": recv_obj.completion_tokens[index],
                        "finish_reason": _json(recv_obj.finished_reasons[index]),
                        "prompt_tokens": recv_obj.prompt_tokens[index],
                        "at_monotonic": time.monotonic(),
                    }
                )
            return original_detokenize(self, recv_obj)

        detokenizer.handle_batch_token_id_out = traced_detokenize
        detokenizer._ngram_trace_installed = True

    manager = tokenizer_manager.TokenizerManager
    if not getattr(manager, "_ngram_trace_installed", False):
        original_handle = manager._handle_batch_output

        async def traced_handle(self, recv_obj):
            for index, rid in enumerate(recv_obj.rids):
                if recv_obj.finished_reasons[index] is None:
                    continue
                text = recv_obj.output_strs[index]
                token_ids = list(recv_obj.output_ids[index])
                _append(
                    {
                        "stage": "post_generation_pre_parser_final",
                        "rid": rid,
                        "scheduler_output_ids": token_ids,
                        "emitted_token_ids": token_ids,
                        "parser_input_utf8_hex": text.encode("utf-8").hex(),
                        "completion_counter": recv_obj.completion_tokens[index],
                        "completion_counter_inputs": {
                            "emitted_token_count": len(token_ids),
                            "final_delta_ids": token_ids,
                        },
                        "finish_reason": _json(recv_obj.finished_reasons[index]),
                        "prompt_tokens": recv_obj.prompt_tokens[index],
                        "at_monotonic": time.monotonic(),
                    }
                )
            result = await original_handle(self, recv_obj)
            return result

        manager._handle_batch_output = traced_handle
        manager._ngram_trace_installed = True
