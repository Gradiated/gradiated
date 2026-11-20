"""Jeeves (PostHog/jeeves) as an SGLang model: SGLang's Qwen3.5 text model with Jeeves's pointer head.

A question's prompt ends with its options, each closed by </opt>, and <decide>. Option i's score is the scaled dot
product of the head's query projection of the final hidden state at <decide> with its key projection of the final
hidden state at the option's </opt> (those after the prompt's last </think>). SGLang computes logits only at each
request's last token, so the model computes the scores in `forward`, where it sees every token of the extend step,
and the logits processor returns them as the logits of token ids 0, 1, ... (option i's score at id i, -inf for ids
past the question's options, 0 for every other id). The runtime reads them with `token_ids_logprob`; a log
probability differs from its logit by one constant per request, so the softmax over the options is unchanged. A
question whose options are not all in its step gets NaN scores, which the runtime refuses. This port follows
PostHog/hogference's vLLM model (jeeves/server/jeeves_vllm.py); its fused kernels and last-layer split are not
ported.

The checkpoint (PostHog/jeeves-fp8, branch vllm) has no lm_head: nothing samples from the vocabulary, so none is
allocated. Its pointer head is `pointer.safetensors` (fp32), listed in the checkpoint's weight index.

SGLang finds this class through SGLANG_EXTERNAL_MODEL_PACKAGE=jeeves_sglang; the checkpoint's config names it.
"""
from __future__ import annotations

from typing import Iterable, Tuple

import torch
from torch import nn

from sglang.srt.layers.quantization.base_config import QuantizeMethodBase
from sglang.srt.models.qwen3_5_text import Qwen3_5ForCausalLM

from jeeves_sglang.readout import MAX_OPTIONS, plan

POINTER_WEIGHTS = {'q.weight', 'q.bias', 'k.weight', 'k.bias'}


class OptionScores(QuantizeMethodBase):
    """The logits processor's lm_head computation: its input rows carry option scores, which become the logits of
    token ids 0..254. SGLang's logits processor calls `apply` for an lm_head that has a quant method and no weight."""

    def __init__(self, vocab_size):
        self.vocab_size = vocab_size

    def create_weights(self, layer, *args, **kwargs):
        pass

    def apply(self, layer, x, bias=None):
        logits = torch.zeros((x.shape[0], self.vocab_size), dtype=torch.float32, device=x.device)
        logits[:, :MAX_OPTIONS] = x[:, :MAX_OPTIONS].float()
        return logits

    def process_weights_after_loading(self, layer):
        pass


class PointerLogits(nn.Module):
    def __init__(self, vocab_size):
        super().__init__()
        self.quant_method = OptionScores(vocab_size)


class JeevesForCausalLM(Qwen3_5ForCausalLM):
    def __init__(self, config, quant_config=None, prefix: str = ''):
        # The base class allocates an untied 2 GB lm_head unless the embeddings are tied; this model has none.
        tied = config.tie_word_embeddings
        config.tie_word_embeddings = True
        try:
            super().__init__(config=config, quant_config=quant_config, prefix=prefix)
        finally:
            config.tie_word_embeddings = tied
        if self.pp_group.world_size != 1:
            raise ValueError('JeevesForCausalLM runs on one GPU: no pipeline parallelism')
        jeeves = config.jeeves
        self.markers = {name: int(jeeves[f'{name}_id']) for name in ('opt_end', 'decide', 'think_end')}
        head_dim = int(jeeves['head_dim'])
        self.pointer = nn.Module()
        self.pointer.q = nn.Linear(config.hidden_size, head_dim, dtype=torch.float32)
        self.pointer.k = nn.Linear(config.hidden_size, head_dim, dtype=torch.float32)
        self.scale = head_dim ** -0.5
        self.lm_head = PointerLogits(config.vocab_size)

    @torch.no_grad()
    def forward(self, input_ids, positions, forward_batch, input_embeds=None, pp_proxy_tensors=None, **kwargs):
        if self.is_mrope_enabled:
            positions = forward_batch.mrope_positions
        hidden = self.model(input_ids, positions, forward_batch, input_embeds, pp_proxy_tensors=pp_proxy_tensors)
        if isinstance(hidden, tuple):
            hidden = hidden[0]
        rows = self.option_scores(input_ids, hidden, forward_batch)
        return self.logits_processor(input_ids, rows, self.lm_head, forward_batch)

    def option_scores(self, input_ids, hidden, forward_batch):
        """One row per token of the step: at a question's <decide>, its options' scores; zeros elsewhere."""
        rows = torch.zeros((hidden.shape[0], MAX_OPTIONS + 1), dtype=torch.float32, device=hidden.device)
        seq_lens = forward_batch.extend_seq_lens_cpu
        if input_ids is None or not forward_batch.forward_mode.is_extend() or not seq_lens:
            return rows
        prefix_lens = forward_batch.extend_prefix_lens_cpu or [0] * len(seq_lens)
        questions = plan(input_ids[:sum(seq_lens)].tolist(), seq_lens, prefix_lens, self.markers)
        if not questions:
            return rows
        device = hidden.device
        unreadable = [decide for decide, read in questions if read is None]
        if unreadable:
            rows[torch.tensor(unreadable, device=device)] = float('nan')
        readable = [(decide, read) for decide, read in questions if read is not None]
        if not readable:
            return rows
        decide = torch.tensor([d for d, _ in readable], device=device)
        options = torch.tensor([p for _, read in readable for p in read], device=device)
        owner = torch.tensor([j for j, (_, read) in enumerate(readable) for _ in read], device=device)
        index = torch.tensor([i for _, read in readable for i in range(len(read))], device=device)
        queries = self.pointer.q(hidden[decide].float())
        keys = self.pointer.k(hidden[options].float())
        rows[decide] = float('-inf')
        rows[decide[owner], index] = (keys * queries[owner]).sum(-1) * self.scale
        return rows

    def load_weights(self, weights: Iterable[Tuple[str, torch.Tensor]]):
        pointer = {}

        def body():
            for name, weight in weights:
                if name.startswith('pointer.'):
                    pointer[name[len('pointer.'):]] = weight
                else:
                    yield name, weight

        loaded = set(super().load_weights(body()))
        if set(pointer) != POINTER_WEIGHTS:
            raise RuntimeError(f'the checkpoint must hold the pointer head {sorted(POINTER_WEIGHTS)}')
        params = dict(self.pointer.named_parameters())
        for name, weight in pointer.items():
            if tuple(params[name].shape) != tuple(weight.shape):
                raise RuntimeError(f'pointer.{name} has shape {tuple(weight.shape)}')
            params[name].data.copy_(weight.to(torch.float32))
        return loaded | {f'pointer.{name}' for name in pointer}


EntryClass = JeevesForCausalLM
