"""KnowLine (PelaAI/KnowLine-31B-Gen1.5, Gemma-4-31B) as a batched backend for ``gdecide.evaluate``.

Prompts come from KnowLine's own release front end (``knowline_server.py`` and ``knowline_layout.py``, shipped in the
model repo and therefore in every checkpoint directory downloaded from it), with the settings of its Decision Index
run (``knowline_engine.py`` defaults): chat template with thinking off, read twice for text-only requests of at most
3,000 tokens read once, the question header for longer requests whose longest prompt fits 32,768 tokens, per-type
temperatures from ``temperatures.json``. One prompt per question, ending in ``Answer:``; the answer is the softmax over
the label tokens (`` A``, `` B``, ...) of the next-token logits.

What differs from the release engine is only how the forward passes are run: instead of one SGLang (or transformers)
prefill per question, every prompt of a chunk of requests is right-padded into length-sorted batches of at most
``batch_tokens`` padded tokens and run through the Gemma 4 text model in bf16 on one GPU. Only the label rows of the
tied output embedding are applied, in fp32 (as SGLang's ``--enable-fp32-lm-head``), followed by the checkpoint's
``final_logit_softcapping`` (which carries part of the folded readout temperature). Softmax over the label logits is
the same as KnowLine's softmax over label logprobs, since the full-vocabulary normalizer cancels.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

REPO = "PelaAI/KnowLine-31B-Gen1.5"
REVISION = "8e56aa1b236a6dd1064dcfd22ba1e5e360e4c140"
FRONT_END_FILES = ("knowline_server.py", "knowline_layout.py")


class Unsupported(ValueError):
    """A request KnowLine's front end cannot answer as asked (reported as ``unsupported``, never truncated)."""


def front_end(path: str | Path):
    """Import ``knowline_server`` / ``knowline_layout`` from a checkpoint (or model repo) directory."""
    path = Path(path).resolve()
    missing = [f for f in FRONT_END_FILES if not (path / f).exists()]
    if missing:
        raise FileNotFoundError(f"{path} lacks KnowLine's front end files {missing}")
    loaded = sys.modules.get("knowline_server")
    if loaded is not None and Path(loaded.__file__).resolve().parent != path:
        raise RuntimeError(f"knowline_server already imported from {loaded.__file__}, not {path}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    import knowline_layout
    import knowline_server

    return knowline_server, knowline_layout


class _NoBackend:
    def warm(self, prefix, media):
        raise RuntimeError("rendering only")

    def score(self, text, media, ids):
        raise RuntimeError("rendering only")


@dataclasses.dataclass
class Prompt:
    request: int
    qid: str
    keys: list[str]
    ids: list[int]
    temperature: float


class Renderer:
    """KnowLine's release prompts and label ids, without a model. ``read_twice=False`` reads every request once
    (no header); ``header_when_long=0`` gives the Gen1 prompts."""

    def __init__(self, checkpoint: str, front_end_dir: str | None = None, temperature: float = 1.0,
                 read_twice: bool = True, twice_max_tokens: int = 3000, header_when_long: int = 32768,
                 temperatures: str | dict | None = "default"):
        from transformers import AutoTokenizer

        self.ks, layout_mod = front_end(front_end_dir or checkpoint)
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        if temperatures == "default":
            file = Path(front_end_dir or checkpoint) / "temperatures.json"
            temperatures = json.loads(file.read_text()) if file.exists() else {}
        elif isinstance(temperatures, str):
            temperatures = {} if temperatures in ("", "none") else json.loads(Path(temperatures).read_text())
        layout = layout_mod.Layout(read_twice=True, twice_max_tokens=int(twice_max_tokens)) if read_twice else None
        self.engine = self.ks.KnowLine(self.tokenizer, _NoBackend(), float(temperature), 1, temperatures or {}, layout,
                                       header_long_max=int(header_when_long) if layout else 0)
        self.engine.pool.shutdown(wait=False)
        self.label_ids = list(self.engine.ids)
        self.settings = {"temperature": float(temperature), "temperatures": dict(temperatures or {}),
                         "read_twice": bool(read_twice), "twice_max_tokens": int(twice_max_tokens),
                         "header_when_long": int(header_when_long) if layout else 0, "labels": len(self.label_ids)}

    def texts(self, request: dict) -> dict[str, tuple[str, list[str]]]:
        """{qid: (prompt text ending in "Answer:", answer keys in shown order)}, exactly as the release engine renders."""
        state, questions = request.get("state", ""), request.get("questions") or {}
        ks = self.ks
        if not 1 <= len(questions) <= ks.MAX_QUESTIONS:
            raise Unsupported(f"{len(questions)} questions; 1..{ks.MAX_QUESTIONS} per request")
        for qid, q in questions.items():
            if not isinstance(q, dict) or q.get("type") not in ("choice", "noul", "score"):
                raise Unsupported(f"question {qid!r}: type must be choice, noul or score")
        try:
            _, prompts, media = self.engine._render(state, questions, False)
        except ValueError as exc:
            raise Unsupported(str(exc)) from exc
        if media:
            raise Unsupported("requests with images need KnowLine's SGLang backend")
        return prompts

    def prompts(self, request: dict, index: int = 0) -> list[Prompt]:
        out = []
        for qid, (text, keys) in self.texts(request).items():
            q = request["questions"][qid]
            ids = self.tokenizer.encode(text, add_special_tokens=False)
            out.append(Prompt(index, qid, keys, ids, self.engine.T_by_type.get(q.get("type"), self.engine.T)))
        return out

    def answers(self, request: dict, prompts: list[Prompt], logits: list[list[float]]) -> dict:
        ks = self.ks
        got = {p.qid: ks.answer(request["questions"][p.qid], p.keys, ks.softmax(row[: len(p.keys)], p.temperature))
               for p, row in zip(prompts, logits, strict=True)}
        return {qid: got[qid] for qid in request["questions"]}


def plan_batches(lengths: list[int], budget: int, max_rows: int = 256) -> list[list[int]]:
    """Indices grouped longest first so that width * rows <= budget (a longer single prompt runs alone)."""
    order = sorted(range(len(lengths)), key=lambda i: -lengths[i])
    out, group, width = [], [], 0
    for i in order:
        w = max(width, lengths[i])
        if group and (w * (len(group) + 1) > budget or len(group) >= max_rows):
            out.append(group)
            group, w = [], lengths[i]
        group.append(i)
        width = w
    if group:
        out.append(group)
    return out


class KnowLineDecider:
    """``decide(request | [requests])`` -> response(s) with ``answers`` in the Decisions-API format."""

    unsupported = (Unsupported,)

    def __init__(self, renderer: Renderer, model, device: str, max_length: int, batch_tokens: int):
        import torch

        self.renderer, self.model, self.device = renderer, model, device
        self.max_length, self.batch_tokens = int(max_length), int(batch_tokens)
        self.text = model.model.language_model
        weight = model.get_output_embeddings().weight
        self.label_weight = weight[torch.tensor(renderer.label_ids, device=weight.device)].float().contiguous()
        self.softcap = model.config.get_text_config().final_logit_softcapping
        self.temperature = renderer.settings["temperature"]

    @classmethod
    def from_pretrained(cls, checkpoint: str, device: str = "cuda", max_length: int = 131072,
                        batch_tokens: int = 32768, **options):
        import torch
        from transformers import Gemma4ForConditionalGeneration

        torch.backends.cuda.enable_cudnn_sdp(False)
        renderer = Renderer(checkpoint, **options)
        model = Gemma4ForConditionalGeneration.from_pretrained(checkpoint, dtype=torch.bfloat16, attn_implementation="sdpa",
                                                               device_map={"": device})
        model.requires_grad_(False).eval()
        return cls(renderer, model, device, max_length, batch_tokens)

    def label_logits(self, batch: list[list[int]]):
        """Capped label logits (fp32) at the last token of each right-padded sequence -> [batch, labels]."""
        import torch

        width = max(len(x) for x in batch)
        pad = self.model.config.get_text_config().pad_token_id or 0
        ids = torch.full((len(batch), width), pad, dtype=torch.long)
        for b, x in enumerate(batch):
            ids[b, : len(x)] = torch.tensor(x, dtype=torch.long)
        last = torch.tensor([len(x) - 1 for x in batch], device=self.device)
        with torch.inference_mode():
            hidden = self.text(input_ids=ids.to(self.device), use_cache=False).last_hidden_state
            z = hidden[torch.arange(len(batch), device=self.device), last].float() @ self.label_weight.T
            if self.softcap is not None:
                z = torch.tanh(z / self.softcap) * self.softcap
        return z.cpu()

    def decide(self, requests, temperature: float | None = None):
        single = isinstance(requests, dict)
        batch = [requests] if single else list(requests)
        if temperature is not None and temperature != self.renderer.engine.T:
            raise ValueError("KnowLine's base temperature is set at load (it is folded into the weights; use 1.0)")
        prompts = [self.renderer.prompts(r, i) for i, r in enumerate(batch)]
        for ps in prompts:
            longest = max(len(p.ids) for p in ps)
            if longest > self.max_length:
                raise Unsupported(f"prompt of {longest} tokens exceeds max_length {self.max_length}; never truncated")
        flat = [p for ps in prompts for p in ps]
        rows: list[list[float] | None] = [None] * len(flat)
        for group in plan_batches([len(p.ids) for p in flat], self.batch_tokens):
            z = self.label_logits([flat[i].ids for i in group])
            for j, i in enumerate(group):
                rows[i] = z[j].tolist()
        out, cursor = [], 0
        for r, ps in zip(batch, prompts, strict=True):
            mine = rows[cursor : cursor + len(ps)]
            cursor += len(ps)
            usage = {"input_tokens": sum(len(p.ids) for p in ps), "output_tokens": len(ps)}
            out.append({"answers": self.renderer.answers(r, ps, mine), "usage": usage})
        return out[0] if single else out
