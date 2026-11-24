"""Which tokens of an SGLang extend step the Jeeves pointer head reads. Pure Python, so the CPU tests cover it."""
from __future__ import annotations

MAX_OPTIONS = 255


def plan(ids, seq_lens, markers):
    """The questions of one extend step: [(decide position, option positions or None)], positions into the step.

    ids are the step's tokens, flattened request by request; seq_lens counts each request's tokens in
    this step. A request whose last token is <decide> is a question. The head reads
    the hidden state at <decide> and at each </opt> after the request's last </think>. Option positions are None when
    the suffix is incomplete: it must contain the real </think> delimiter, all subsequent option ends and
    <decide>. User-supplied text escapes these delimiters. Reject option counts outside 1..255.
    """
    questions, start = [], 0
    for length in seq_lens:
        end = start + length
        if length and ids[end - 1] == markers['decide']:
            decide = end - 1
            read = None
            think_end = next((i for i in range(decide - 1, start - 1, -1) if ids[i] == markers['think_end']), None)
            if think_end is not None:
                read = [i for i in range(think_end + 1, decide) if ids[i] == markers['opt_end']]
                if not 1 <= len(read) <= MAX_OPTIONS:
                    read = None
            questions.append((decide, read))
        start = end
    return questions
