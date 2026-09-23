"""CPU-only doubles for the Kev adapter tests; never used by the serving runtime.

With KEV_SOURCE set, the pinned upstream API and pure encoder replace the doubles.
"""
import ast
import json
import os
from pathlib import Path
import re
import sys
import threading
from types import SimpleNamespace

import adapter


def model_validate(data):
    return SimpleNamespace(**{**data, "questions": {
        key: SimpleNamespace(**{**q, "criteria": q.get("criteria")})
        for key, q in data["questions"].items()}})


def to_record(req):
    questions, meta = [], []
    for key, q in req.questions.items():
        keys = (list(q.criteria) if q.type == "choice" else ["false", "true"]
                if q.type == "noul" else [str(i) for i in range(len(q.criteria))])
        options = ([f"{k}: {v}" for k, v in q.criteria.items()] if q.type == "choice"
                   else ["no", "yes"] if q.type == "noul" else q.criteria)
        questions.append({"instr": q.instructions, "options": options, "label": 0})
        meta.append({"id": key, "type": q.type, "keys": keys, "legend": dict(zip(keys, options))})
    return {"state": req.state, "questions": questions}, meta


def to_answers(probabilities, meta):
    result = {}
    for p, m in zip(probabilities, meta):
        answer = {"type": m["type"]}
        if m["type"] == "noul":
            answer["noul"] = p[1]
        else:
            answer.update(probabilities=dict(zip(m["keys"], p)), confidence=0.0)
            if m["type"] == "choice":
                answer["choice"] = m["keys"][p.index(max(p))]
            else:
                answer.update(score=sum(i * v for i, v in enumerate(p)), legend=m["legend"])
        result[m["id"]] = answer
    return result


def encode(tok, rec, *, max_state, max_branch, strict, option_isolation):
    assert strict is True
    ids = [100000] + tok(rec["state"]).input_ids
    state_length = len(ids)
    if state_length > max_state:
        raise ValueError("state exceeds limit")

    segments, options = [0] * state_length, []
    for i, question in enumerate(rec["questions"], 1):
        branch = [100001] + tok(question["instr"]).input_ids
        offsets = []
        for option in question["options"]:
            branch += [100002] + tok(option).input_ids + [100003]
            offsets.append(len(ids) + len(branch) - 1)
        branch += [100004]
        if state_length + len(branch) > max_branch:
            raise ValueError("branch exceeds limit")

        ids.extend(branch)
        segments.extend([i] * len(branch))
        options.append(offsets)
    return {"ids": ids, "seg": segments, "opt_idx": options, "option_isolation": option_isolation}


SOURCE = Path(os.environ["KEV_SOURCE"]) if os.environ.get("KEV_SOURCE") else None
namespace = {"re": re, "_SPECIAL_RE": re.compile(r"<\|([A-Za-z0-9_]+)\|>"),
             "SPECIAL": ["<|fim_prefix|>", "<|fim_middle|>", "<|box_start|>", "<|box_end|>", "<|fim_suffix|>"],
             "MAX_STATE": 384, "MAX_BRANCH": 1024, "OPT_NONE": -1, "OPT_DECIDE": -2,
             "encode": encode}
api = SimpleNamespace(SystemOneRequest=SimpleNamespace(model_validate=model_validate),
                      to_record=to_record, to_answers=to_answers)
if SOURCE is not None:
    sys.path.insert(0, str(SOURCE))
    from kev import api

    # Execute only pure upstream functions, without importing torch/transformers.
    tree = ast.parse((SOURCE / "kev/model.py").read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("user_tokens", "encode")]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE / "kev/model.py"), "exec"), namespace)


class Tokenizer:
    def __call__(self, text, **kwargs):
        return SimpleNamespace(input_ids=[ord(char) for char in text])

    def convert_tokens_to_ids(self, token):
        return 100000 + namespace["SPECIAL"].index(token)


class Probabilities(list):
    def tolist(self):
        return list(self)


class Model:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.isolation = False
        self.output = None

    def encode(self, tok, rec, **kwargs):
        return namespace["encode"](tok, rec, option_isolation=self.isolation, **kwargs)

    def probs(self, enc):
        self.calls.append("plain")
        if self.output is not None:
            return self.output
        return [Probabilities([1 / len(options)] * len(options)) for options in enc["opt_idx"]]

    def probs_and_prefix(self, enc):
        result = self.probs(enc)
        self.calls[-1] = "miss"
        return result, tuple(enc["ids"][:enc["seg"].count(0)])

    def probs_with_prefix(self, enc, prefix):
        if self.fail:
            raise RuntimeError("secret model payload must not leak")

        assert prefix == tuple(enc["ids"][:enc["seg"].count(0)])
        result = self.probs(enc)
        self.calls[-1] = "hit"
        return result


def reject(data):
    raise ValueError("upstream schema rejected secret request payload")


rejecting_api = SimpleNamespace(SystemOneRequest=SimpleNamespace(model_validate=reject),
                                to_record=to_record, to_answers=to_answers)


def engine(sync=lambda device: None, upstream=None):
    server = SimpleNamespace(model=Model(), tok=Tokenizer(), prefix_cache={}, lock=threading.Lock(),
                             device="stub")
    return adapter.Engine(server, upstream or api, sync)


def request(state="x" * 400):
    return {"model": adapter.MODEL, "state": state, "questions": {
        "choose": {"type": "choice", "instructions": "pick", "criteria": {"a": "A", "b": "B"}},
        "yes": {"type": "noul", "instructions": "yes?"},
        "rank": {"type": "score", "instructions": "rank", "criteria": ["low", "high"]}}}


async def exchange(app, data=None, *, path="/v1/systemone", method="POST", headers=None, chunks=None):
    body = json.dumps(data).encode() if data is not None else b""
    events = list(chunks) if chunks is not None else [{"type": "http.request", "body": body}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(event):
        sent.append(event)

    await app({"type": "http", "path": path, "method": method,
               "headers": [(k.lower(), v) for k, v in headers] if headers is not None
               else [(b"content-type", b"application/json")]}, receive, send)
    return sent


async def call(app, data=None, *, path="/v1/systemone", method="POST", headers=None, chunks=None):
    sent = await exchange(app, data, path=path, method=method, headers=headers, chunks=chunks)
    if not sent:
        return None, None

    return sent[0]["status"], json.loads(sent[1]["body"])
