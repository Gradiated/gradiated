from __future__ import annotations

import dataclasses

import torch

from decode_equivalent_lm_head import project_decode_shapes


@dataclasses.dataclass
class Metadata:
    next_token_logits_buffer: torch.Tensor | None = None


def test_request_major_rows_are_projected_at_decode_batch_shape() -> None:
    batch_size = 3
    draft_tokens = 4
    hidden = torch.arange(batch_size * draft_tokens * 2, dtype=torch.float32).reshape(
        batch_size * draft_tokens, 2
    )
    call_shapes: list[tuple[int, int]] = []

    def original(_processor, states, _head, _metadata, _bias):
        call_shapes.append(tuple(states.shape))
        return torch.stack((states[:, 0], states[:, 1], states.sum(dim=1)), dim=1)

    actual = project_decode_shapes(
        original,
        object(),
        hidden,
        object(),
        Metadata(),
        None,
        draft_tokens,
    )
    expected = torch.stack(
        (hidden[:, 0], hidden[:, 1], hidden.sum(dim=1)), dim=1
    )
    assert torch.equal(actual, expected)
    assert call_shapes == [(batch_size, 2)] * draft_tokens


def test_candidate_writes_the_original_graph_buffer() -> None:
    hidden = torch.arange(12, dtype=torch.float32).reshape(6, 2)
    buffer = torch.empty((6, 1), dtype=torch.float32)

    def original(_processor, states, _head, _metadata, _bias):
        return states[:, :1]

    actual = project_decode_shapes(
        original,
        object(),
        hidden,
        object(),
        Metadata(next_token_logits_buffer=buffer),
        None,
        3,
    )
    assert actual.data_ptr() == buffer.data_ptr()
    assert torch.equal(actual, hidden[:, :1])


def test_nondivisible_verification_shape_fails_closed() -> None:
    hidden = torch.zeros((5, 2))

    def original(*_args):
        raise AssertionError("must not project")

    try:
        project_decode_shapes(
            original,
            object(),
            hidden,
            object(),
            Metadata(),
            None,
            3,
        )
    except RuntimeError as exc:
        assert "decode_equivalent_rows_not_divisible" in str(exc)
    else:
        raise AssertionError("nondivisible target-verify rows were accepted")
