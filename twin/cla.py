"""CLA-style cross-layer KV sharing retrofit for SmolLM2-135M (Llama arch).

Adjacent layer pairs share one KV: layer 2k+1 ("consumer") reuses the
post-RoPE key/value states produced by layer 2k ("producer") and its own
k_proj/v_proj are deleted. Implemented as a per-instance forward patch of
LlamaAttention that mirrors the stock transformers 5.13 forward exactly.

Supports cache-free forward only (teacher-forced eval + training);
config.use_cache is forced off. KV cache bytes/token halve architecturally.
"""

import types

import torch
from transformers import AutoModelForCausalLM
from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
from transformers.models.llama.modeling_llama import (
    apply_rotary_pos_emb,
    eager_attention_forward,
)


def _cla_forward(self, hidden_states, position_embeddings=None, attention_mask=None,
                 past_key_values=None, **kwargs):
    if past_key_values is not None:
        raise NotImplementedError("CLA patch is cache-free (eval/training only)")
    input_shape = hidden_states.shape[:-1]
    hidden_shape = (*input_shape, -1, self.head_dim)
    query_states = self.q_proj(hidden_states).view(hidden_shape).transpose(1, 2)
    cos, sin = position_embeddings

    if self._cla_role == "producer":
        key_states = self.k_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        value_states = self.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        query_states, key_states = apply_rotary_pos_emb(query_states, key_states, cos, sin)
        self._cla_shared[self._cla_pair] = (key_states, value_states)
    else:
        query_states, _ = apply_rotary_pos_emb(query_states, query_states, cos, sin)
        key_states, value_states = self._cla_shared[self._cla_pair]

    attention_interface = ALL_ATTENTION_FUNCTIONS.get_interface(
        self.config._attn_implementation, eager_attention_forward
    )
    attn_output, attn_weights = attention_interface(
        self, query_states, key_states, value_states, attention_mask,
        dropout=0.0 if not self.training else self.attention_dropout,
        scaling=self.scaling, **kwargs,
    )
    attn_output = attn_output.reshape(*input_shape, -1).contiguous()
    return self.o_proj(attn_output), attn_weights


def apply_cla(model, replica_mode: bool = False):
    """Patch a LlamaForCausalLM in place.

    replica_mode=True keeps every layer a self-producer (no sharing, no
    deletion) — output must be bit-identical to the stock model; used as the
    correctness test for the reimplemented forward.
    """
    shared = {}
    for idx, layer in enumerate(model.model.layers):
        attn = layer.self_attn
        consumer = (idx % 2 == 1) and not replica_mode
        attn._cla_role = "consumer" if consumer else "producer"
        attn._cla_pair = idx if replica_mode else idx // 2
        attn._cla_shared = shared
        if consumer:
            attn.k_proj = None
            attn.v_proj = None
        attn.forward = types.MethodType(_cla_forward, attn)
    model.config.use_cache = False
    if not replica_mode:
        model.config.kv_sharing = "cla2"
    return model


def load_cla(model_dir, dtype=torch.float32):
    """Load a CLA checkpoint (or a base checkpoint to be retrofitted)."""
    model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=dtype)
    return apply_cla(model)


def cla_param_count(model):
    return sum(p.numel() for p in model.parameters())
