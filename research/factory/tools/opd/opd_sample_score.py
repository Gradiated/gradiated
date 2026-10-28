"""One round of on-policy distillation data: the student samples, the teacher scores, the aligner assigns credit.

The student (Qwen 3.8 27B plus the current LoRA, served by vLLM) samples the next assistant turn on anonymized
training prefixes. Kimi K3 scores each sample through Fireworks chat completions with `echo`: the sample is sent back
as the final assistant message, so Fireworks renders it with K3's own template and returns a logprob per prompt token.
The cross-tokenizer aligner turns the two tokenizations into per-student-token advantages (teacher minus student
span logprob). Runs on fbf8 with the serve-env Python; prints aggregates only.

    opd_sample_score.py --round 0 --student qwen27b-base --prefixes 32 --samples 4 --out runs/opd/round-000.jsonl
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = Path("/opt/posthog-sft/eval")
sys.path.insert(0, str(EVAL))
sys.path.insert(0, str(HERE))

import tiktoken  # noqa: E402
from formats import anthropic_to_openai, openai_tools  # noqa: E402
from providers import restore_required_properties  # noqa: E402
from sampling import _clean, enumerate_points  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402
from xtok_distill import ParseError, align, parse_qwen_output, render_k3_completion, token_advantages, with_gaps  # noqa: E402

QWEN_DIR = Path("/opt/posthog-sft/models/Qwen3.8-27B")
K3_PATTERN = "|".join([
    r"""[\p{Han}]+""",
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""\p{N}{1,3}""",
    r""" ?[^\s\p{L}\p{N}]+[\r\n]*""",
    r"""\s*[\r\n]+""",
    r"""\s+(?!\S)""",
    r"""\s+""",
])


def load_k3(directory: Path) -> tuple[tiktoken.Encoding, dict[str, int]]:
    ranks = {}
    for line in (directory / "kimi.tiktoken.model").read_bytes().splitlines():
        if line.strip():
            token, rank = line.split()
            ranks[base64.b64decode(token)] = int(rank)
    config = json.loads((directory / "kimi.tokenizer_config.json").read_text())
    special = {v["content"]: int(k) for k, v in config["added_tokens_decoder"].items()}
    return tiktoken.Encoding("kimi", pat_str=K3_PATTERN, mergeable_ranks=ranks, special_tokens=special), special


def byte_decoder() -> dict[str, int]:
    """Inverse of the GPT-2 byte-to-unicode table used by byte-level BPE vocabularies."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


def char_offsets(pieces: list[bytes]) -> tuple[str, list[tuple[int, int]]]:
    """Text of concatenated token bytes and each token's character span; a token ending mid-character gets an empty span."""
    data = b"".join(pieces)
    offsets, consumed, start = [], 0, 0
    for piece in pieces:
        consumed += len(piece)
        end = len(data[:consumed].decode(errors="ignore"))
        offsets.append((start, end))
        start = end
    return data.decode(errors="replace"), offsets


class Qwen:
    def __init__(self) -> None:
        self.tok = Tokenizer.from_file(str(QWEN_DIR / "tokenizer.json"))
        added = json.loads((QWEN_DIR / "tokenizer.json").read_text())["added_tokens"]
        self.special = {a["id"]: a["content"] for a in added}
        self.bytes_of = byte_decoder()

    def pieces(self, ids: list[int]) -> list[bytes]:
        out = []
        for i in ids:
            if i in self.special:
                out.append(self.special[i].encode())
            else:
                out.append(bytes(self.bytes_of[c] for c in self.tok.id_to_token(i)))
        return out


def post(url: str, body: dict, headers: dict, attempts: int = 6, timeout: int = 600) -> dict:
    for attempt in range(attempts):
        request = urllib.request.Request(url, json.dumps(body).encode(), {**headers, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            text = error.read().decode(errors="replace")[:300]
            # Fireworks returns a bare 500 for some long requests every time; retry those once, not with full backoff.
            if error.code not in (408, 429, 500, 502, 503, 504, 529, 583) or attempt == attempts - 1 or (error.code == 500 and attempt >= 1):
                raise RuntimeError(f"HTTP {error.code}: {text}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == attempts - 1:
                raise RuntimeError(f"{type(error).__name__}: {error}") from None
        time.sleep(min(60, 2 ** attempt + random.random()))
    raise AssertionError("unreachable")


def param_types(tools: list[dict]) -> dict[str, dict[str, str | None]]:
    out = {}
    for tool in tools:
        fn = tool["function"]
        props = (fn.get("parameters") or {}).get("properties") or {}
        out[fn["name"]] = {k: (v.get("type") if isinstance(v.get("type"), str) else None) for k, v in props.items()}
    return out


def assistant_message(turn) -> dict:
    """The parsed sample as an OpenAI assistant message. Arguments stay a JSON string so K3's encoder keeps each
    non-string value's literal text, exactly as the student wrote it."""
    message: dict = {"role": "assistant", "content": turn.content}
    if turn.calls:
        message["tool_calls"] = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": "{" + ",".join(
                        json.dumps(a.key, ensure_ascii=False) + ":" + (json.dumps(a.text, ensure_ascii=False) if a.is_string else a.text)
                        for a in call.arguments
                    ) + "}",
                },
            }
            for i, call in enumerate(turn.calls)
        ]
    return message


def find_last(haystack: list[int], needle: list[int]) -> int | None:
    for i in range(len(haystack) - len(needle), -1, -1):
        if haystack[i : i + len(needle)] == needle:
            return i
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--student", required=True, help="vLLM model or adapter name")
    p.add_argument("--data", default="/opt/posthog-sft/root_agent/data_all/train.jsonl")
    p.add_argument("--prefixes", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--max-prompt-tokens", type=int, default=32000)
    p.add_argument("--vllm", default="http://127.0.0.1:18000/v1")
    p.add_argument("--teacher", default="accounts/fireworks/models/kimi-k3")
    p.add_argument("--tok-dir", default=str(HERE))
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--no-gaps", action="store_true", help="leave template runs between content spans unscored")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    qwen = Qwen()
    kimi, k3_special = load_k3(Path(args.tok_dir))
    fireworks = {"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}

    # Read line by line: some records contain U+2028, which str.splitlines() in load_conversations treats as a newline.
    with open(args.data) as f:
        conversations = [_clean(json.loads(line), default_id=f"train:{i}") for i, line in enumerate(f) if line.strip()]
    points = enumerate_points(conversations)
    rng = random.Random(1_000 + args.round)
    rng.shuffle(points)
    stats: Counter = Counter()
    usage: Counter = Counter()

    def k3_ids(rendering) -> tuple[list[int], list[tuple[int, int]]]:
        ids, offsets, position = [], [], 0
        for segment in rendering.segments:
            if segment.special:
                ids.append(k3_special[segment.text])
                offsets.append((position, position + len(segment.text)))
            else:
                data, consumed, start = segment.text.encode(), 0, position
                for token in kimi.encode_ordinary(segment.text):
                    ids.append(token)
                    consumed += len(kimi.decode_single_token_bytes(token))
                    end = position + len(data[:consumed].decode(errors="ignore"))
                    offsets.append((start, end))
                    start = end
            position += len(segment.text)
        return ids, offsets

    def score(point, messages, tools, sample) -> dict | None:
        ids = sample["token_ids"]
        logprobs = [c["logprob"] for c in sample["logprobs"]["content"]]
        if len(ids) != len(logprobs):
            stats["logprob_length_mismatch"] += 1
            return None
        text, offsets = char_offsets(qwen.pieces(ids))
        try:
            turn, fields = parse_qwen_output(text, param_types=param_types(tools))
            rendering = render_k3_completion(turn, thinking=False)
        except (ParseError, ValueError):
            stats["parse_error"] += 1
            return {"status": "parse_error", "token_ids": ids, "sampler_logprobs": logprobs}
        body = {
            "model": args.teacher, "messages": messages + [assistant_message(turn)],
            "tools": [restore_required_properties(t) for t in tools], "max_tokens": 1, "echo": True,
            "logprobs": True, "raw_output": True, "chat_template_kwargs": {"thinking": False},
        }
        try:
            response = post("https://api.fireworks.ai/inference/v1/chat/completions", body, fireworks)
        except RuntimeError as error:
            stats["teacher_error"] += 1
            print(f"teacher error: {str(error)[:200]}", file=sys.stderr)
            return None
        choice = response["choices"][0]
        for k, v in (response.get("usage") or {}).items():
            if isinstance(v, int):
                usage[f"teacher_{k}"] += v
        prompt_ids = choice["raw_output"]["prompt_token_ids"]
        teacher_lp = [c.get("logprob") for c in choice["logprobs"]["content"]]
        mine, t_offsets = k3_ids(rendering)
        at = find_last(prompt_ids, mine)
        if at is None:
            stats["teacher_render_mismatch"] += 1
            return None
        t_logprobs = [x if x is not None else 0.0 for x in teacher_lp[at : at + len(mine)]]
        try:
            spans = align(offsets, fields, t_offsets, rendering.fields)
        except ValueError:
            stats["align_error"] += 1
            return None
        content = {i for s in spans for i in s.student_tokens}
        if not args.no_gaps:
            spans = with_gaps(spans, len(ids), len(mine))
        advantages = token_advantages(spans, logprobs, t_logprobs)
        covered = [a for a in advantages if a is not None]
        gap_kl = -sum(a for i, a in enumerate(advantages) if a is not None and i not in content)
        stats["gap_tokens"] += sum(1 for i, a in enumerate(advantages) if a is not None and i not in content)
        stats["scored"] += 1
        stats["tokens"] += len(ids)
        stats["covered"] += len(covered)
        stats["calls"] += len(turn.calls)
        return {
            "status": "ok", "point_id": point.point_id, "token_ids": ids, "sampler_logprobs": logprobs,
            "advantages": advantages, "reverse_kl": -sum(covered), "covered": len(covered), "gap_kl": gap_kl,
        }

    def run_prefix(point) -> list[dict]:
        tools = openai_tools(point.tools)
        messages = anthropic_to_openai(point.system, point.history)
        body = {
            "model": args.student, "messages": messages, "tools": tools, "tool_choice": "none",
            "n": args.samples, "temperature": args.temperature, "max_tokens": args.max_tokens,
            "logprobs": True, "return_token_ids": True, "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = post(f"{args.vllm}/chat/completions", body, {}, attempts=2)
        except RuntimeError as error:
            stats["student_error"] += 1
            if "No user query" not in str(error) and "maximum context" not in str(error):
                print(f"student error: {str(error)[:200]}", file=sys.stderr)
            return []
        prompt_ids = response["prompt_token_ids"]
        if len(prompt_ids) > args.max_prompt_tokens:
            stats["prompt_too_long"] += 1
            return []
        out = []
        for sample in response["choices"]:
            stats["samples"] += 1
            if sample["finish_reason"] != "stop":
                stats["truncated"] += 1
            record = score(point, messages, tools, sample)
            if record is not None:
                record.update({"round": args.round, "prompt_token_ids": prompt_ids, "finish": sample["finish_reason"]})
                out.append(record)
        return out

    started = time.time()
    records: list[dict] = []
    with ThreadPoolExecutor(args.workers) as pool:
        for batch in pool.map(run_prefix, points[: args.prefixes]):
            records.extend(batch)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    ok = [r for r in records if r["status"] == "ok"]
    summary = {
        "round": args.round, "student": args.student, "seconds": round(time.time() - started),
        "prefixes": len({r["point_id"] for r in ok}), "records": len(records), "scored": len(ok),
        "coverage": round(stats["covered"] / max(1, stats["tokens"]), 4),
        "reverse_kl_per_covered_token": round(sum(r["reverse_kl"] for r in ok) / max(1, stats["covered"]), 4),
        "reverse_kl_per_sample": round(sum(r["reverse_kl"] for r in ok) / max(1, len(ok)), 3),
        "mean_tokens": round(stats["tokens"] / max(1, len(ok)), 1),
        "gap_kl_per_sample": round(sum(r["gap_kl"] for r in ok) / max(1, len(ok)), 3),
        "stats": dict(stats), "usage": dict(usage),
    }
    print(json.dumps(summary))
    with open(Path(args.out).with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
