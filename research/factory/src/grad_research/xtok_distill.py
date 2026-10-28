"""Cross-tokenizer on-policy distillation alignment.

A student sample is parsed into content fields (reasoning, response text, tool
names, argument keys and values). The same fields are re-rendered in the
teacher's chat format, so each field has identical text in both renderings.
Inside each field, spans whose two edges are token boundaries for both
tokenizers carry a reverse-KL estimate: teacher span log-probability minus
student span log-probability. Template tokens and tokens that straddle a
field edge carry no teacher signal.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

DSML = "｜DSML｜"
DEEPSEEK_EOS = "<｜end▁of▁sentence｜>"
K3_OPEN = "<|open|>"
K3_CLOSE = "<|close|>"
K3_SEP = "<|sep|>"
K3_END_OF_MSG = "<|end_of_msg|>"


@dataclass(frozen=True)
class Argument:
    key: str
    is_string: bool
    text: str


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: tuple[Argument, ...]


@dataclass(frozen=True)
class AssistantTurn:
    reasoning: str | None
    content: str
    calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class FieldSpan:
    field: str
    start: int
    end: int


@dataclass(frozen=True)
class Segment:
    text: str
    special: bool


@dataclass(frozen=True)
class Rendering:
    segments: tuple[Segment, ...]
    fields: tuple[FieldSpan, ...]

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)


@dataclass(frozen=True)
class AlignedSpan:
    field: str
    student_tokens: range
    teacher_tokens: range


class ParseError(ValueError):
    pass


_INVOKE = re.compile(
    rf'<{DSML} invoke name="(?P<name>[^"]*)">\n(?P<body>.*?)\n</{DSML} invoke>', re.S
)
_PARAMETER = re.compile(
    rf'<{DSML} parameter name="(?P<key>[^"]*)" string="(?P<string>true|false)">'
    rf"(?P<value>.*?)</{DSML} parameter>",
    re.S,
)


def parse_deepseek_output(output: str, *, thinking: bool) -> tuple[AssistantTurn, tuple[FieldSpan, ...]]:
    """Parse a DeepSeek V4.1 completion that follows `<｜Assistant｜><think>` (or `</think>`)."""
    fields: list[FieldSpan] = []
    position = 0
    reasoning = None
    if thinking:
        close = output.find("</think>")
        if close < 0:
            raise ParseError("thinking output has no </think>")
        reasoning = output[:close]
        fields.append(FieldSpan("reasoning", 0, close))
        position = close + len("</think>")

    end = output.find(DEEPSEEK_EOS, position)
    end = len(output) if end < 0 else end
    calls_start = output.find(f"\n\n<{DSML} calls>\n", position, end)
    content_end = end if calls_start < 0 else calls_start
    content = output[position:content_end]
    fields.append(FieldSpan("content", position, content_end))

    calls: list[ToolCall] = []
    if calls_start >= 0:
        block_start = calls_start + len(f"\n\n<{DSML} calls>\n")
        block_end = output.find(f"\n</{DSML} calls>", block_start, end)
        if block_end < 0:
            raise ParseError("tool-call block is not closed")
        cursor = block_start
        for index, invoke in enumerate(_INVOKE.finditer(output, block_start, block_end)):
            if invoke.start() != cursor:
                raise ParseError(f"unexpected text before call {index}")
            fields.append(FieldSpan(f"call{index}.name", *invoke.span("name")))
            arguments = []
            body_start = invoke.start("body")
            arg_cursor = body_start
            for arg_index, parameter in enumerate(
                _PARAMETER.finditer(output, body_start, invoke.end("body"))
            ):
                if output[arg_cursor : parameter.start()] not in ("", "\n"):
                    raise ParseError(f"unexpected text in call {index}")
                prefix = f"call{index}.arg{arg_index}"
                fields.append(FieldSpan(f"{prefix}.key", *parameter.span("key")))
                fields.append(FieldSpan(f"{prefix}.value", *parameter.span("value")))
                arguments.append(
                    Argument(
                        parameter.group("key"),
                        parameter.group("string") == "true",
                        parameter.group("value"),
                    )
                )
                arg_cursor = parameter.end()
            if arg_cursor != invoke.end("body"):
                raise ParseError(f"unexpected trailing text in call {index}")
            calls.append(ToolCall(invoke.group("name"), tuple(arguments)))
            cursor = invoke.end() + 1
        if cursor != block_end + 1:
            raise ParseError("unparsed text in tool-call block")

    return AssistantTurn(reasoning, content, tuple(calls)), tuple(fields)


QWEN_EOS = "<|im_end|>"
_QWEN_CALL = re.compile(
    r"<tool_call>\n<function=(?P<name>[^>\n]*)>\n(?P<body>(?:<parameter=[^>\n]*>\n.*?\n</parameter>\n)*)</function>\n</tool_call>",
    re.S,
)
_QWEN_PARAMETER = re.compile(r"<parameter=(?P<key>[^>\n]*)>\n(?P<value>.*?)\n</parameter>\n", re.S)


def _qwen_is_string(value: str, schema_type: str | None) -> bool:
    """Qwen does not mark string values; the tool schema decides, as vLLM's qwen3_coder parser does."""
    if schema_type is not None:
        return schema_type == "string"
    try:
        return isinstance(json.loads(value), str)
    except ValueError:
        return True


def parse_qwen_output(
    output: str, *, param_types: dict[str, dict[str, str | None]] | None = None
) -> tuple[AssistantTurn, tuple[FieldSpan, ...]]:
    """Parse a non-thinking Qwen 3.x completion that follows `<think>\\n\\n</think>\\n\\n`.

    `param_types` maps tool name to parameter name to its JSON-schema type, when known.
    """
    end = output.find(QWEN_EOS)
    end = len(output) if end < 0 else end
    first = output.find("<tool_call>", 0, end)
    calls_start = end if first < 0 else first
    content_end = calls_start
    if first >= 0:
        if output.endswith("\n\n", 0, calls_start):
            content_end -= 2
        elif output.endswith("\n", 0, calls_start):
            content_end -= 1
    fields = [FieldSpan("content", 0, content_end)]
    calls: list[ToolCall] = []
    cursor = calls_start
    for index, call in enumerate(_QWEN_CALL.finditer(output, calls_start, end)):
        gap = output[cursor : call.start()]
        if gap not in ("", "\n"):
            raise ParseError(f"unexpected text before call {index}")
        name = call.group("name")
        fields.append(FieldSpan(f"call{index}.name", *call.span("name")))
        types = (param_types or {}).get(name, {})
        arguments = []
        for arg_index, parameter in enumerate(_QWEN_PARAMETER.finditer(output, call.start("body"), call.end("body"))):
            prefix = f"call{index}.arg{arg_index}"
            key, value = parameter.group("key"), parameter.group("value")
            fields.append(FieldSpan(f"{prefix}.key", *parameter.span("key")))
            fields.append(FieldSpan(f"{prefix}.value", *parameter.span("value")))
            arguments.append(Argument(key, _qwen_is_string(value, types.get(key)), value))
        calls.append(ToolCall(name, tuple(arguments)))
        cursor = call.end()
    if output[cursor:end].strip():
        raise ParseError("unparsed text after the tool calls")
    return AssistantTurn(None, output[:content_end], tuple(calls)), tuple(fields)


def _json_type(argument: Argument) -> str:
    if argument.is_string:
        return "string"
    value = json.loads(argument.text)
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    return "object" if isinstance(value, dict) else "array"


class _Builder:
    def __init__(self) -> None:
        self.segments: list[Segment] = []
        self.fields: list[FieldSpan] = []
        self.length = 0

    def text(self, text: str, field: str | None = None) -> None:
        if field is not None:
            self.fields.append(FieldSpan(field, self.length, self.length + len(text)))
        if text:
            self.segments.append(Segment(text, False))
            self.length += len(text)

    def control(self, text: str) -> None:
        self.segments.append(Segment(text, True))
        self.length += len(text)

    def open_tag(self, tag: str, attrs: Iterable[tuple[str, str, str | None]] = ()) -> None:
        self.control(K3_OPEN)
        self.text(tag)
        for key, value, field in attrs:
            self.text(f" {key}")
            self.text('="')
            escaped = value.replace("&", "&amp;").replace('"', "&quot;")
            self.text(escaped, field if escaped == value else None)
            self.text('"')
        self.control(K3_SEP)

    def close_tag(self, tag: str) -> None:
        self.control(K3_CLOSE)
        self.text(tag)
        self.control(K3_SEP)


def render_k3_completion(turn: AssistantTurn, *, thinking: bool) -> Rendering:
    """Render the assistant turn as K3 continues it after its generation prompt.

    K3's generation prompt ends with the opening `think` tag in thinking mode or
    the opening `response` tag otherwise; the returned text starts right after it.
    """
    out = _Builder()
    if thinking:
        out.text(turn.reasoning or "", "reasoning")
        out.close_tag("think")
        out.open_tag("response")
    out.text(turn.content, "content")
    out.close_tag("response")
    if turn.calls:
        out.open_tag("tools")
        for index, call in enumerate(turn.calls):
            out.open_tag(
                "call", [("tool", call.name, f"call{index}.name"), ("index", str(index + 1), None)]
            )
            for arg_index, argument in enumerate(call.arguments):
                prefix = f"call{index}.arg{arg_index}"
                out.open_tag(
                    "argument",
                    [("key", argument.key, f"{prefix}.key"), ("type", _json_type(argument), None)],
                )
                out.text(argument.text, f"{prefix}.value")
                out.close_tag("argument")
            out.close_tag("call")
        out.close_tag("tools")
    out.close_tag("message")
    out.control(K3_END_OF_MSG)
    return Rendering(tuple(out.segments), tuple(out.fields))


def offsets_from_pieces(pieces: Sequence[str]) -> list[tuple[int, int]]:
    """Character spans of consecutive token texts; an empty piece (a partial character) has no span."""
    spans, position = [], 0
    for piece in pieces:
        spans.append((position, position + len(piece)))
        position += len(piece)
    return spans


def _tokens_inside(offsets: Sequence[tuple[int, int]], field: FieldSpan) -> dict[int, int]:
    return {
        start - field.start: index
        for index, (start, end) in enumerate(offsets)
        if field.start <= start < end <= field.end
    }


def align(
    student_offsets: Sequence[tuple[int, int]],
    student_fields: Sequence[FieldSpan],
    teacher_offsets: Sequence[tuple[int, int]],
    teacher_fields: Sequence[FieldSpan],
) -> list[AlignedSpan]:
    """Minimal spans sharing both edges with token boundaries in both tokenizations."""
    teacher_by_name = {field.field: field for field in teacher_fields}
    spans: list[AlignedSpan] = []
    for s_field in student_fields:
        t_field = teacher_by_name.get(s_field.field)
        if t_field is None:
            continue
        if s_field.end - s_field.start != t_field.end - t_field.start:
            raise ValueError(f"field {s_field.field} differs in length between renderings")
        s_starts = _tokens_inside(student_offsets, s_field)
        t_starts = _tokens_inside(teacher_offsets, t_field)
        for position in sorted(s_starts.keys() & t_starts.keys()):
            i = first_i = s_starts[position]
            j = first_j = t_starts[position]
            s_end = student_offsets[i][1] - s_field.start
            t_end = teacher_offsets[j][1] - t_field.start
            while s_end != t_end:
                if s_end < t_end:
                    i += 1
                    if s_starts.get(s_end) != i:
                        break
                    s_end = student_offsets[i][1] - s_field.start
                else:
                    j += 1
                    if t_starts.get(t_end) != j:
                        break
                    t_end = teacher_offsets[j][1] - t_field.start
            if s_end == t_end:
                spans.append(AlignedSpan(s_field.field, range(first_i, i + 1), range(first_j, j + 1)))
    return spans


def token_advantages(
    spans: Sequence[AlignedSpan],
    student_logprobs: Sequence[float],
    teacher_logprobs: Sequence[float],
) -> list[float | None]:
    """Per-student-token negative reverse-KL estimate; None where no teacher signal applies.

    Each span's teacher-minus-student log-probability is split evenly over the
    student tokens in it, so per-token values sum to the span estimate.
    """
    advantages: list[float | None] = [None] * len(student_logprobs)
    for span in spans:
        teacher = sum(teacher_logprobs[j] for j in span.teacher_tokens)
        student = sum(student_logprobs[i] for i in span.student_tokens)
        share = (teacher - student) / len(span.student_tokens)
        for i in span.student_tokens:
            advantages[i] = share
    return advantages


def coverage(spans: Sequence[AlignedSpan], student_token_count: int) -> float:
    covered = sum(len(span.student_tokens) for span in spans)
    return covered / student_token_count if student_token_count else 0.0
