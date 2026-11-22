"""Independent NumPy FP32 Llama arithmetic oracle; no MLX imports or cache."""
import json
import math
import numpy as np

def rms_norm(x, weight, epsilon):
    mean_square = np.mean(np.square(x), axis=-1, keepdims=True, dtype=np.float32)
    return (x / np.sqrt(mean_square + np.float32(epsilon))) * weight


def rotary(x, theta, positions):
    """Split-half RoPE on [heads, positions, head_dim], position zero identity."""
    dim = x.shape[-1]
    if dim % 2:
        raise ValueError('RoPE head dimension must be even')
    powers = np.arange(0, dim, 2, dtype=np.float32) / np.float32(dim)
    inverse_frequency = np.power(np.float32(theta), -powers)
    angle = np.asarray(positions, dtype=np.float32)[:, None] * inverse_frequency[None, :]
    cosine, sine = np.cos(angle)[None, :, :], np.sin(angle)[None, :, :]
    first, second = np.split(x, 2, axis=-1)
    return np.concatenate((first * cosine - second * sine,
                           second * cosine + first * sine), axis=-1)


def causal_probabilities(q, k):
    """q,k:[query_heads, sequence, head_dim]; stable, explicitly causal softmax."""
    scores = (q @ k.swapaxes(-1, -2)) * np.float32(1 / math.sqrt(q.shape[-1]))
    future = np.triu(np.ones(scores.shape[-2:], dtype=bool), k=1)
    scores = np.where(future, np.float32(-np.inf), scores)
    scores -= np.max(scores, axis=-1, keepdims=True)
    probabilities = np.exp(scores)
    probabilities /= np.sum(probabilities, axis=-1, keepdims=True, dtype=np.float32)
    return probabilities


def silu(x):
    # Stable sigmoid: exp(-abs(x)) cannot overflow for large negative inputs.
    exp_neg_abs = np.exp(-np.abs(x))
    sigmoid = np.where(x >= 0, 1 / (1 + exp_neg_abs), exp_neg_abs / (1 + exp_neg_abs))
    return x * sigmoid


def validate_config(config):
    if config.get('model_type') != 'llama' or config.get('hidden_act') != 'silu':
        raise ValueError('This reference supports Llama with SiLU only')
    if config.get('attention_bias', False) or config.get('mlp_bias', False):
        raise ValueError('Biases are outside this reference scope')
    if config.get('rope_scaling') is not None or config.get('rope_interleaved', False) or config.get('rope_traditional', False):
        raise ValueError('This reference requires unscaled split-half RoPE')
    if config.get('sliding_window') or config.get('layer_types'):
        raise ValueError('Only full causal attention is supported')
    if not config.get('tie_word_embeddings', False):
        raise ValueError('This reference requires a tied embedding/output head')
    for key in ('hidden_size', 'intermediate_size', 'num_attention_heads', 'num_key_value_heads', 'num_hidden_layers', 'vocab_size'):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ValueError(f'Invalid positive dimension: {key}')
    if config['hidden_size'] % config['num_attention_heads'] or config['num_attention_heads'] % config['num_key_value_heads']:
        raise ValueError('Incompatible attention dimensions')
    dim = config['hidden_size'] // config['num_attention_heads']
    if dim % 2 or config.get('head_dim', dim) != dim:
        raise ValueError('Unsupported head dimension')
    for key, default in (('rms_norm_eps', None), ('rope_theta', 10000)):
        value = config.get(key, default)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'Invalid positive {key}')


def forward(weights, config, tokens, report=False):
    validate_config(config)
    if not isinstance(tokens, list) or not tokens or any(type(n) is not int or not 0 <= n < config['vocab_size'] for n in tokens):
        raise ValueError('Tokens must be a nonempty list of vocabulary token IDs')
    if len(tokens) > config.get('max_position_embeddings', 8192):
        raise ValueError('Prompt exceeds checkpoint context limit')
    hidden = config['hidden_size']
    heads = config['num_attention_heads']
    kv_heads = config['num_key_value_heads']
    dim = hidden // heads
    n = len(tokens)
    positions = np.arange(n, dtype=np.float32)
    epsilon = config['rms_norm_eps']
    theta = config.get('rope_theta', 10000)
    if weights.shape('model.embed_tokens.weight') != (config['vocab_size'], hidden):
        raise ValueError('Embedding shape/config mismatch')
    x = weights.get('model.embed_tokens.weight', rows=np.asarray(tokens, dtype=np.int64))

    def linear(value, name, output_dims):
        if weights.shape(name) != (output_dims, value.shape[-1]):
            raise ValueError(f'Linear shape mismatch: {name}')
        matrix = weights.get(name)
        return value @ matrix.T

    def norm(value, name):
        if weights.shape(name) != (hidden,):
            raise ValueError(f'RMSNorm shape mismatch: {name}')
        return rms_norm(value, weights.get(name), epsilon)

    for layer in range(config['num_hidden_layers']):
        prefix = f'model.layers.{layer}.'
        normalized = norm(x, prefix + 'input_layernorm.weight')
        q = linear(normalized, prefix + 'self_attn.q_proj.weight', heads * dim)
        k = linear(normalized, prefix + 'self_attn.k_proj.weight', kv_heads * dim)
        v = linear(normalized, prefix + 'self_attn.v_proj.weight', kv_heads * dim)
        q = rotary(q.reshape(n, heads, dim).transpose(1, 0, 2), theta, positions)
        k = rotary(k.reshape(n, kv_heads, dim).transpose(1, 0, 2), theta, positions)
        v = v.reshape(n, kv_heads, dim).transpose(1, 0, 2)
        k = np.repeat(k, heads // kv_heads, axis=0)
        v = np.repeat(v, heads // kv_heads, axis=0)
        probabilities = causal_probabilities(q, k)
        context = (probabilities @ v).transpose(1, 0, 2).reshape(n, hidden)
        x = x + linear(context, prefix + 'self_attn.o_proj.weight', hidden)
        normalized = norm(x, prefix + 'post_attention_layernorm.weight')
        gate = linear(normalized, prefix + 'mlp.gate_proj.weight', config['intermediate_size'])
        up = linear(normalized, prefix + 'mlp.up_proj.weight', config['intermediate_size'])
        x = x + linear(silu(gate) * up, prefix + 'mlp.down_proj.weight', hidden)
        if x.dtype != np.float32 or not np.isfinite(x).all():
            raise FloatingPointError(f'Invalid FP32 state after layer {layer}')
        if report:
            print(json.dumps({'completed_layer': layer, 'hidden_rms': float(np.sqrt(np.mean(x * x)))}), flush=True)
    last = norm(x[-1:], 'model.norm.weight')[0]
    # Chunk the tied head to bound temporary storage.
    logits = np.empty(config['vocab_size'], dtype=np.float32)
    for begin in range(0, len(logits), 4096):
        end = min(begin + 4096, len(logits))
        logits[begin:end] = weights.get('model.embed_tokens.weight', rows=slice(begin, end)) @ last
    if not np.isfinite(logits).all():
        raise FloatingPointError('Nonfinite final logits')
    return logits
