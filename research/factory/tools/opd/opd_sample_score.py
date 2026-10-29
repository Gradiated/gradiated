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
import math
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

    def id_of(self, text: str) -> int | None:
        """Qwen token id whose bytes are exactly this string, or None (special tokens map by content)."""
        if not hasattr(self, "_special_ids"):
            self._special_ids = {v: k for k, v in self.special.items()}
            self._byte_char = {b: c for c, b in self.bytes_of.items()}
        if text in self._special_ids:
            return self._special_ids[text]
        return self.tok.token_to_id("".join(self._byte_char[b] for b in text.encode()))

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
    p.add_argument("--weights", default="", help="advantage multipliers by field kind, e.g. name=20,key=5")
    p.add_argument("--teacher-vllm", default="", help="same-tokenizer teacher served by vLLM at this base URL (prompt_logprobs)")
    p.add_argument("--topk", type=int, default=0, help="also return the teacher's top-k alternatives at 1:1 aligned positions")
    p.add_argument("--same-tokenizer", action="store_true",
                   help="teacher shares the student's tokenizer and template: score the exact token ids via completions echo")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    weights = {k: float(v) for k, v in (item.split("=") for item in args.weights.split(",") if item)}
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
    field_kl: Counter = Counter()
    field_tokens: Counter = Counter()

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

    def score_same_tokenizer(point, ids, logprobs, prompt_ids, text, offsets, tools) -> dict | None:
        """Standard OPD: the teacher scores the student's exact prompt and sample tokens, so every token is covered."""
        if args.teacher_vllm:
            body = {"model": args.teacher, "prompt": prompt_ids + ids, "max_tokens": 1, "prompt_logprobs": 0}
            try:
                response = post(f"{args.teacher_vllm}/completions", body, {})
            except RuntimeError as error:
                stats["teacher_error"] += 1
                print(f"teacher error: {str(error)[:200]}", file=sys.stderr)
                return None
            plp = response["choices"][0]["prompt_logprobs"][len(prompt_ids) : len(prompt_ids) + len(ids)]
            teacher = [(entry or {}).get(str(t), {}).get("logprob", 0.0) for entry, t in zip(plp, ids)]
        else:
            body = {"model": args.teacher, "prompt": prompt_ids + ids, "max_tokens": 1, "echo": True, "logprobs": 1}
            try:
                response = post("https://api.fireworks.ai/inference/v1/completions", body, fireworks)
            except RuntimeError as error:
                stats["teacher_error"] += 1
                print(f"teacher error: {str(error)[:200]}", file=sys.stderr)
                return None
            lp = response["choices"][0]["logprobs"]
            for k, v in (response.get("usage") or {}).items():
                if isinstance(v, int):
                    usage[f"teacher_{k}"] += v
            echoed = lp.get("token_ids") or []
            if echoed[len(prompt_ids) : len(prompt_ids) + len(ids)] != ids:
                stats["teacher_token_mismatch"] += 1
                return None
            teacher = [x if x is not None else 0.0 for x in lp["token_logprobs"][len(prompt_ids) : len(prompt_ids) + len(ids)]]
        raw = [t - s for t, s in zip(teacher, logprobs)]
        kind = ["gap"] * len(ids)
        try:
            _, fields = parse_qwen_output(text, param_types=param_types(tools))
            for f in fields:
                k = f.field.split(".")[-1] if "." in f.field else f.field
                for i, (a, b) in enumerate(offsets):
                    if f.start <= a < b <= f.end:
                        kind[i] = k
        except (ParseError, ValueError):
            stats["parse_error_kinds_only"] += 1
        for i, a in enumerate(raw):
            field_kl[kind[i]] -= a
            field_tokens[kind[i]] += 1
        advantages = [a * weights.get(kind[i], 1.0) for i, a in enumerate(raw)]
        gap_kl = -sum(a for i, a in enumerate(raw) if kind[i] == "gap")
        stats["scored"] += 1
        stats["tokens"] += len(ids)
        stats["covered"] += len(ids)
        stats["gap_tokens"] += kind.count("gap")
        return {"status": "ok", "point_id": point.point_id, "token_ids": ids, "sampler_logprobs": logprobs,
                "advantages": advantages, "reverse_kl": -sum(raw), "covered": len(ids), "gap_kl": gap_kl}

    def score(point, messages, tools, sample, prompt_ids) -> dict | None:
        ids = sample["token_ids"]
        logprobs = [c["logprob"] for c in sample["logprobs"]["content"]]
        if len(ids) != len(logprobs):
            stats["logprob_length_mismatch"] += 1
            return None
        text, offsets = char_offsets(qwen.pieces(ids))
        if args.same_tokenizer:
            return score_same_tokenizer(point, ids, logprobs, prompt_ids, text, offsets, tools)
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
            **({"top_logprobs": args.topk} if args.topk else {}),
        }
        try:
            response = post("https://api.fireworks.ai/inference/v1/chat/completions", body, fireworks)
        except RuntimeError as error:
            if "top_logprobs" not in body or "HTTP 500" not in str(error):
                stats["teacher_error"] += 1
                print(f"teacher error: {str(error)[:200]}", file=sys.stderr)
                return None
            # Fireworks returns 500 on many long prompts when top-k is requested; score this sample without top-k.
            body = {k: v for k, v in body.items() if k != "top_logprobs"}
            stats["topk_fallback"] += 1
            try:
                response = post("https://api.fireworks.ai/inference/v1/chat/completions", body, fireworks)
            except RuntimeError as error2:
                stats["teacher_error"] += 1
                print(f"teacher error: {str(error2)[:200]}", file=sys.stderr)
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
        topk = {}
        if args.topk:
            entries = choice["logprobs"]["content"]
            for span in spans:
                if len(span.student_tokens) != 1 or len(span.teacher_tokens) != 1:
                    continue
                alts = entries[at + span.teacher_tokens.start].get("top_logprobs") or [] if "top_logprobs" in body else []
                mapped = {}
                for alt in alts:
                    qid = qwen.id_of(alt["token"])
                    if qid is not None and alt.get("logprob") is not None:
                        mapped[qid] = max(mapped.get(qid, -1e9), alt["logprob"])
                if mapped and sum(math.exp(v) for v in mapped.values()) >= 0.5:
                    topk[span.student_tokens.start] = sorted(mapped.items(), key=lambda kv: -kv[1])
            stats["topk_positions"] += len(topk)
        if not args.no_gaps:
            spans = with_gaps(spans, len(ids), len(mine))
        raw = token_advantages(spans, logprobs, t_logprobs)
        kind = {}
        for span in spans:
            for i in span.student_tokens:
                kind[i] = span.field.split(".")[-1] if "." in span.field else span.field
        for i, a in enumerate(raw):
            if a is not None:
                field_kl[kind[i]] -= a
                field_tokens[kind[i]] += 1
        advantages = [None if a is None else a * weights.get(kind[i], 1.0) for i, a in enumerate(raw)]
        covered = [a for a in raw if a is not None]
        gap_kl = -sum(a for i, a in enumerate(raw) if a is not None and i not in content)
        stats["gap_tokens"] += sum(1 for i, a in enumerate(raw) if a is not None and i not in content)
        stats["scored"] += 1
        stats["tokens"] += len(ids)
        stats["covered"] += len(covered)
        stats["calls"] += len(turn.calls)
        return {
            "status": "ok", "point_id": point.point_id, "token_ids": ids, "sampler_logprobs": logprobs,
            "advantages": advantages, "reverse_kl": -sum(covered), "covered": len(covered), "gap_kl": gap_kl,
            "topk": {str(i): v for i, v in topk.items()},
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
            record = score(point, messages, tools, sample, prompt_ids)
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
        "field_kl_per_token": {k: round(field_kl[k] / field_tokens[k], 4) for k in field_tokens},
        "field_tokens": dict(field_tokens), "weights": weights,
        "stats": dict(stats), "usage": dict(usage),
    }
    print(json.dumps(summary))
    with open(Path(args.out).with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, indent=1)


if __name__ == "__main__":
    main()
