"""Jeeves's no-think prompt: the request rendered as Jeeves was trained, then the empty thinking, the options again
and <decide>, whose hidden states the pointer head reads.

Ported from github.com/PostHog/jeeves at 954d063d (prep/format.py `render`, `option_text` and `Question.options`;
loader/dataloader.py `Encoder.prompt_text`, `remainder_text` and `sanitize`), with the escaping of literal thinking
markers that PostHog/hogference's jeeves/server/jeeves_server.py adds. Jeeves's code is under the MIT License:

    Copyright (c) 2026 Nicholas P. Waltz

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
    to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
    copyright notice and this permission notice shall be included in all copies or substantial portions of the
    Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
    LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
    SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
    OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.
"""
from __future__ import annotations

import re

STATE, QUESTION, OPT, OPT_END, DECIDE = '<|fim_prefix|>', '<|fim_middle|>', '<|box_start|>', '<|box_end|>', \
    '<|fim_suffix|>'
THINK, THINK_END = '<think>', '</think>'
CONTROL_RE = re.compile(r'<\|([A-Za-z0-9_]+)\|>')


def render(value, indent=0):
    pad = '  ' * indent
    if value is None:
        return ''
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return '\n'.join(f'{pad}- {render(x, indent + 1).lstrip()}' for x in value)
    return '\n'.join(
        f'{pad}{k}:\n{render(v, indent + 1)}' if isinstance(v, (dict, list)) else f'{pad}{k}: {render(v)}'
        for k, v in value.items())


def option_text(name, desc):
    return name if desc is None or desc == '' else f'{name}: {render(desc)}'


def sanitize(text):
    """Jeeves escapes its <|...|> markers in any text it renders."""
    return CONTROL_RE.sub(r'<¦\1¦>', text)


def escaped_thinking(text):
    """The tokenizer reads a literal <think> or </think> as the marker, which would move where the head reads the
    options; hogference escapes them as Jeeves escapes its <|...|> markers."""
    return text.replace(THINK, '<¦think¦>').replace(THINK_END, '<¦/think¦>')


def keys(question):
    """The outcome keys in Jeeves's option order: noul false then true."""
    if question['type'] == 'choice':
        return list(question['criteria'])
    if question['type'] == 'noul':
        return ['false', 'true']
    return [str(i) for i in range(len(question['criteria']))]


def options(question):
    if question['type'] == 'choice':
        return [option_text(k, v) for k, v in question['criteria'].items()]
    if question['type'] == 'noul':
        criteria = question.get('criteria') or {}
        return [option_text('no', criteria.get('false')), option_text('yes', criteria.get('true'))]
    return [render(x) for x in question['criteria']]


def option_block(question):
    return ''.join(f'{OPT}{sanitize(o)}{OPT_END}\n' for o in options(question))


class Prompts:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        ids = tokenizer.convert_tokens_to_ids([OPT_END, DECIDE, THINK_END])
        if any(i is None or i == tokenizer.unk_token_id for i in ids):
            raise ValueError('marker tokens missing from tokenizer')
        self.opt_end_id, self.decide_id, self.think_end_id = ids
        self.empty_think = self.encode('\n')

    def encode(self, text):
        return self.tokenizer(text, add_special_tokens=False).input_ids

    def chat(self, content):
        return self.tokenizer.apply_chat_template([{'role': 'user', 'content': content}], tokenize=False,
                                                  add_generation_prompt=True, enable_thinking=True)

    def prompt_text(self, state, question):
        text = self.chat(f'{STATE}{sanitize(render(state))}\n{QUESTION}{sanitize(render(question.get("instructions")))}'
                         f'\n{option_block(question)}')
        # Every thinking marker is escaped but the <think> of the chat template, which ends the prompt.
        head, think, tail = text.rpartition(THINK)
        return escaped_thinking(head) + think + tail

    def remainder_text(self, question):
        head, think_end, tail = f'{THINK_END}\n\n{option_block(question)}{DECIDE}'.partition(THINK_END)
        return head + think_end + escaped_thinking(tail)

    def ids(self, state, question):
        """The no-think sequence of Jeeves's engine: its prompt, empty thinking, then the options and <decide>."""
        ids = self.encode(self.prompt_text(state, question)) + list(self.empty_think) + self.encode(
            self.remainder_text(question))
        tail = ids[len(ids) - 1 - ids[::-1].index(self.think_end_id):]
        if ids[-1] != self.decide_id or tail.count(self.opt_end_id) != len(options(question)):
            raise ValueError('the question does not render as Jeeves reads it')
        return ids
