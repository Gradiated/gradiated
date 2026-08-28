"""Learn Kimi K3 by building its mathematical functions with NumPy.

Run this file after each exercise:

    python3 research/sol/experiments/kimi_k3_from_scratch.py

We use small tensors. This makes every value easy to inspect.

Learning order:

1. Linear projection
2. RMS normalisation
3. Residual connection
4. Sigmoid and SiLU activation
5. Gated MLP and SiTU
6. Attention and KV cache
7. Top-k MoE routing
8. Latent MoE
9. MLA
10. KDA recurrent state
11. One reduced Kimi K3 decoder layer
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


Tensor = NDArray[np.float64]


def linear(x: Tensor, weight: Tensor) -> Tensor:
    """Apply y = x W^T.

    x has shape (..., input_features).
    weight has shape (output_features, input_features).
    y has shape (..., output_features).

    Exercise 1:
    Implement this function with one NumPy matrix operation.
    Do not use a loop.
    """

    return np.matmul(x, weight.T)


def check_linear() -> None:
    x = np.array(
        [
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
        ]
    )
    weight = np.array(
        [
            [1.0, 0.0, -1.0],
            [0.5, 0.5, 0.5],
        ]
    )
    expected = np.array(
        [
            [-2.0, 3.0],
            [-2.0, 7.5],
        ]
    )

    actual = linear(x, weight)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == (2, 2)


def rms_norm(x: Tensor, weight: Tensor, epsilon: float = 1e-5) -> Tensor:
    """Apply RMSNorm over the final tensor dimension.

    For each vector x:

        rms(x) = sqrt(mean(x ** 2) + epsilon)
        y = weight * x / rms(x)

    x has shape (..., features).
    weight has shape (features,).
    y has the same shape as x.

    Exercise 2:
    Implement the two equations with NumPy.
    Keep the reduced dimension so NumPy can broadcast it across x.
    Do not subtract the mean. RMSNorm is not LayerNorm.
    """

    rms = np.sqrt(np.mean(np.power(x, 2), axis=-1, keepdims=True) + epsilon)

    return np.multiply(weight, x / rms)


def check_rms_norm() -> None:
    x = np.array(
        [
            [3.0, 4.0],
            [0.0, 2.0],
        ]
    )
    weight = np.array([2.0, 0.5])
    expected = np.array(
        [
            [1.697056274847714, 0.565685424949238],
            [0.0, 0.707106781186548],
        ]
    )

    actual = rms_norm(x, weight, epsilon=0.0)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == x.shape

    sequence_x = x.reshape(1, 2, 2)
    sequence_expected = expected.reshape(1, 2, 2)
    sequence_actual = rms_norm(sequence_x, weight, epsilon=0.0)
    np.testing.assert_allclose(sequence_actual, sequence_expected)


def residual(x: Tensor, update: Tensor) -> Tensor:
    """Add a computed update to the original activation.

    The equation is:

        y = x + update

    x, update, and y all have shape (..., features).

    Exercise 3:
    Check that the shapes are equal.
    Return their element-wise sum.
    """

    if x.shape != update.shape:
        raise ValueError("x and update must have the same shape")

    return np.add(x, update)


def check_residual() -> None:
    x = np.array(
        [
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
        ]
    )
    update = np.array(
        [
            [0.5, -1.0, 2.0],
            [-2.0, 0.0, 1.0],
        ]
    )
    expected = np.array(
        [
            [1.5, 1.0, 5.0],
            [2.0, 5.0, 7.0],
        ]
    )

    actual = residual(x, update)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == x.shape


def sigmoid(x: Tensor) -> Tensor:
    """Apply sigmoid to each value.

    The equation is:

        sigmoid(x) = 1 / (1 + exp(-x))

    Exercise 4a:
    Implement the equation with NumPy element-wise operations.
    """

    return 1 / (1 + np.exp(-x))


def silu(x: Tensor) -> Tensor:
    """Apply the SiLU activation to each value.

    The equation is:

        silu(x) = x * sigmoid(x)

    Exercise 4b:
    Implement the equation by calling your sigmoid function.
    """

    return x * sigmoid(x)


def check_activations() -> None:
    x = np.array([-2.0, 0.0, 2.0])
    expected_sigmoid = np.array(
        [0.119202922022118, 0.5, 0.880797077977882]
    )
    expected_silu = np.array(
        [-0.238405844044236, 0.0, 1.761594155955765]
    )

    actual_sigmoid = sigmoid(x)
    actual_silu = silu(x)
    np.testing.assert_allclose(actual_sigmoid, expected_sigmoid)
    np.testing.assert_allclose(actual_silu, expected_silu)
    assert actual_sigmoid.shape == x.shape
    assert actual_silu.shape == x.shape


def gated_mlp(
    x: Tensor,
    gate_weight: Tensor,
    up_weight: Tensor,
    down_weight: Tensor,
) -> Tensor:
    """Apply a small gated MLP.

    The equations are:

        gate = linear(x, gate_weight)
        up = linear(x, up_weight)
        hidden = silu(gate) * up
        output = linear(hidden, down_weight)

    Shapes:

        x:            (..., D)
        gate_weight:  (F, D)
        up_weight:    (F, D)
        down_weight:  (D, F)
        gate:         (..., F)
        up:           (..., F)
        hidden:       (..., F)
        output:       (..., D)

    Exercise 5:
    Implement the four equations by calling linear and silu.
    The multiplication between silu(gate) and up is element-wise.
    """

    gate = linear(x, gate_weight)
    up = linear(x, up_weight)
    hidden = silu(gate) * up
    output = linear(hidden, down_weight)
    return output


def check_gated_mlp() -> None:
    x = np.array([[1.0, -1.0]])
    gate_weight = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )
    up_weight = np.array(
        [
            [1.0, 1.0],
            [1.0, -1.0],
        ]
    )
    down_weight = np.array(
        [
            [1.0, 1.0],
            [2.0, -1.0],
        ]
    )
    expected = np.array([[-0.537882842739990, 0.537882842739990]])

    actual = gated_mlp(x, gate_weight, up_weight, down_weight)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == x.shape


def situ_and_mul(
    gate: Tensor,
    up: Tensor,
    beta: float = 4.0,
    linear_beta: float = 25.0,
) -> Tensor:
    """Apply Kimi K3's SiTU gate and element-wise multiplication.

    The equations are:

        bounded_gate = beta * tanh(gate / beta)
        gate_strength = bounded_gate * sigmoid(gate)
        bounded_up = linear_beta * tanh(up / linear_beta)
        hidden = gate_strength * bounded_up

    gate, up, and hidden all have shape (..., F).

    Exercise 6a:
    Implement the four equations with NumPy.
    All operations are element-wise.
    """

    bounded_gate = beta * np.tanh(gate / beta)
    gate_strength = bounded_gate * sigmoid(gate)
    bounded_up = linear_beta * np.tanh(up / linear_beta)
    hidden = gate_strength * bounded_up
    return hidden


def kimi_gated_mlp(
    x: Tensor,
    gate_weight: Tensor,
    up_weight: Tensor,
    down_weight: Tensor,
) -> Tensor:
    """Apply the exact Kimi K3 expert MLP activation structure.

    Exercise 6b:
    Project x into gate and up values.
    Combine them with situ_and_mul.
    Project the hidden values back to D.
    """

    gate = linear(x, gate_weight)
    up = linear(x, up_weight)

    hidden = situ_and_mul(gate, up)

    output = linear(hidden, down_weight)

    return output


def check_situ_mlp() -> None:
    gate = np.array([-4.0, 0.0, 4.0])
    up = np.array([-25.0, 2.0, 25.0])
    expected_hidden = np.array(
        [1.043246327513052, 0.0, 56.959319511084340]
    )
    actual_hidden = situ_and_mul(gate, up)
    np.testing.assert_allclose(actual_hidden, expected_hidden)

    x = np.array([[1.0, -1.0]])
    gate_weight = np.array([[1.0, 0.0], [0.0, 1.0]])
    up_weight = np.array([[1.0, 1.0], [1.0, -1.0]])
    down_weight = np.array([[1.0, 1.0], [2.0, -1.0]])
    expected_output = np.array(
        [[-0.525828895514303, 0.525828895514303]]
    )
    actual_output = kimi_gated_mlp(
        x,
        gate_weight,
        up_weight,
        down_weight,
    )
    np.testing.assert_allclose(actual_output, expected_output)
    assert actual_output.shape == x.shape


def softmax(x: Tensor, axis: int = -1) -> Tensor:
    """Convert scores into positive weights that sum to one.

    The equations are:

        shifted = x - max(x)
        exponentials = exp(shifted)
        weights = exponentials / sum(exponentials)

    Subtracting the maximum does not change the result. It prevents exp from
    overflowing when a score is large.

    Exercise 7a:
    Implement the three equations with NumPy.
    Calculate max and sum along axis.
    Keep each reduced dimension so NumPy can broadcast it across x.
    """

    shifted = x - np.max(x, axis=axis, keepdims=True)

    exponentials = np.exp(shifted)

    weights = exponentials / np.sum(exponentials, axis=axis, keepdims=True)

    return weights

def check_softmax() -> None:
    scores = np.array(
        [
            [1.0, 2.0, 3.0],
            [0.0, 0.0, 0.0],
        ]
    )
    expected = np.array(
        [
            [0.090030573170380, 0.244728471054798, 0.665240955774822],
            [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0],
        ]
    )

    actual = softmax(scores)
    np.testing.assert_allclose(actual, expected)
    np.testing.assert_allclose(np.sum(actual, axis=-1), np.ones(2))
    assert actual.shape == scores.shape


def scaled_attention_scores(query: Tensor, key: Tensor) -> Tensor:
    """Compare every query token with every key token.

    The equation is:

        scores = query @ key.T / sqrt(H)

    Shapes for one attention head:

        query: (T_query, H)
        key:   (T_key, H)
        scores: (T_query, T_key)

    Each scores[i, j] is the scaled dot product between query token i and key
    token j. H is the number of features in each attention head.

    Exercise 7b:
    Check that query and key have the same H dimension.
    Calculate H from the final dimension of query.
    Implement the equation with one matrix multiplication and np.sqrt.
    """

    if query.shape[-1] != key.shape[-1]:
        raise ValueError("query and key must have the same H dimension")

    H = query.shape[-1]

    return query @ key.T / np.sqrt(H)


def check_scaled_attention_scores() -> None:
    query = np.array(
        [
            [1.0, 0.0],
            [0.0, 2.0],
            [1.0, 1.0],
        ]
    )
    key = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ]
    )
    root_two = np.sqrt(2.0)
    expected = np.array(
        [
            [1.0, 0.0, 1.0],
            [0.0, 2.0, 2.0],
            [1.0, 1.0, 2.0],
        ]
    ) / root_two

    actual = scaled_attention_scores(query, key)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == (3, 3)


def causal_attention_weights(scores: Tensor) -> Tensor:
    """Prevent each token from attending to future tokens.

    For a sequence with three tokens, the mask is:

        [[False, True,  True ],
         [False, False, True ],
         [False, False, False]]

    True positions refer to future tokens. Replace their scores with negative
    infinity before softmax. Softmax then converts those positions to zero.

    Shapes:

        scores:  (T, T)
        weights: (T, T)

    Exercise 7c:
    Check that scores is a square matrix.
    Create the Boolean mask with np.triu and k=1.
    Use np.where to replace masked scores with -np.inf.
    Apply your softmax over the final dimension.
    """


    if scores.shape[0] != scores.shape[-1]:
        raise ValueError("scores must be a square matrix")

    mask = np.triu(np.ones(scores.shape), k=1)
    masked_scores = np.where(mask, -np.inf, scores)
    weights = softmax(masked_scores, axis=-1)
    
    return weights


def check_causal_attention_weights() -> None:
    scores = np.zeros((3, 3))
    expected = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.5, 0.5, 0.0],
            [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0],
        ]
    )

    actual = causal_attention_weights(scores)
    np.testing.assert_allclose(actual, expected)
    np.testing.assert_allclose(np.sum(actual, axis=-1), np.ones(3))
    assert actual.shape == scores.shape


def attention_context(weights: Tensor, value: Tensor) -> Tensor:
    """Mix value vectors according to the attention weights.

    The equation is:

        context = weights @ value

    Shapes for one attention head:

        weights: (T_query, T_key)
        value:   (T_key, H_value)
        context: (T_query, H_value)

    Each context row is a weighted sum of all value rows that the query token
    can attend to.

    Exercise 7d:
    Check that the T_key dimensions of weights and value are equal.
    Implement the equation with one matrix multiplication.
    """

    if weights.shape[-1] != value.shape[0]:
        raise ValueError("weights and value must have the same T_key dimension")
    
    return weights @ value


def check_attention_context() -> None:
    weights = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.25, 0.75, 0.0],
            [0.2, 0.3, 0.5],
        ]
    )
    value = np.array(
        [
            [10.0, 0.0],
            [0.0, 20.0],
            [4.0, 6.0],
        ]
    )
    expected = np.array(
        [
            [10.0, 0.0],
            [2.5, 15.0],
            [4.0, 9.0],
        ]
    )

    actual = attention_context(weights, value)
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == (3, 2)


def causal_self_attention(
    x: Tensor,
    query_weight: Tensor,
    key_weight: Tensor,
    value_weight: Tensor,
    output_weight: Tensor,
) -> Tensor:
    """Apply one complete causal self-attention head.

    The equations are:

        query = linear(x, query_weight)
        key = linear(x, key_weight)
        value = linear(x, value_weight)
        scores = scaled_attention_scores(query, key)
        weights = causal_attention_weights(scores)
        context = attention_context(weights, value)
        output = linear(context, output_weight)

    Exercise 7e:
    Implement these equations by calling the functions you already wrote.
    Do not repeat their internal NumPy operations here.
    """

    query = linear(x, query_weight)
    key = linear(x, key_weight)
    value = linear(x, value_weight)
    scores = scaled_attention_scores(query, key)
    weights = causal_attention_weights(scores)
    context = attention_context(weights, value)
    output = linear(context, output_weight)
    return output


def check_causal_self_attention() -> None:
    x = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )
    identity = np.eye(2)
    expected = np.array(
        [
            [1.0, 0.0],
            [0.330238450673343, 0.669761549326657],
        ]
    )

    actual = causal_self_attention(
        x,
        query_weight=identity,
        key_weight=identity,
        value_weight=identity,
        output_weight=identity,
    )
    np.testing.assert_allclose(actual, expected)
    assert actual.shape == x.shape


def append_kv_cache(
    key_cache: Tensor,
    value_cache: Tensor,
    new_key: Tensor,
    new_value: Tensor,
) -> tuple[Tensor, Tensor]:
    """Append new token keys and values to the KV cache.

    Shapes:

        key_cache:   (T_past, H_key)
        value_cache: (T_past, H_value)
        new_key:     (T_new, H_key)
        new_value:   (T_new, H_value)

    The returned caches have T_past + T_new rows.

    Exercise 7f:
    Check that the old key and value caches have the same T_past dimension.
    Check that new_key and new_value have the same T_new dimension.
    Check that old and new feature dimensions agree for each cache.
    Concatenate each old cache with its new values along the token axis.
    """

    if key_cache.shape[0] != value_cache.shape[0]:
        raise ValueError("key_cache and value_cache must have the same T_past dimension")

    if new_key.shape[0] != new_value.shape[0]:
        raise ValueError("new_key and new_value must have the same T_new dimension")

    if key_cache.shape[1] != new_key.shape[1]:
        raise ValueError("key_cache and new_key must have the same H_key dimension")

    if value_cache.shape[1] != new_value.shape[1]:
        raise ValueError("value_cache and new_value must have the same H_value dimension")

    key_cache = np.concatenate([key_cache, new_key], axis=0)
    value_cache = np.concatenate([value_cache, new_value], axis=0)

    return key_cache, value_cache

def check_append_kv_cache() -> None:
    key_cache = np.array([[1.0, 2.0]])
    value_cache = np.array([[10.0, 20.0, 30.0]])
    new_key = np.array([[3.0, 4.0]])
    new_value = np.array([[40.0, 50.0, 60.0]])

    expected_key_cache = np.array(
        [
            [1.0, 2.0],
            [3.0, 4.0],
        ]
    )
    expected_value_cache = np.array(
        [
            [10.0, 20.0, 30.0],
            [40.0, 50.0, 60.0],
        ]
    )

    actual_key_cache, actual_value_cache = append_kv_cache(
        key_cache,
        value_cache,
        new_key,
        new_value,
    )
    np.testing.assert_allclose(actual_key_cache, expected_key_cache)
    np.testing.assert_allclose(actual_value_cache, expected_value_cache)
    assert actual_key_cache.shape == (2, 2)
    assert actual_value_cache.shape == (2, 3)


def cached_self_attention_step(
    x_new: Tensor,
    key_cache: Tensor,
    value_cache: Tensor,
    query_weight: Tensor,
    key_weight: Tensor,
    value_weight: Tensor,
    output_weight: Tensor,
) -> tuple[Tensor, Tensor, Tensor]:
    """Apply self-attention for one new token and update its KV cache.

    The equations are:

        query = linear(x_new, query_weight)
        new_key = linear(x_new, key_weight)
        new_value = linear(x_new, value_weight)
        key_cache, value_cache = append_kv_cache(...)
        scores = scaled_attention_scores(query, key_cache)
        weights = softmax(scores)
        context = attention_context(weights, value_cache)
        output = linear(context, output_weight)

    A causal mask is not required. The cache contains only past tokens and the
    current token. It does not contain future tokens.

    Exercise 7g:
    Check that x_new contains exactly one token.
    Implement the equations by calling the functions you already wrote.
    Return output, the updated key cache, and the updated value cache.
    """

    if x_new.shape[0] != 1:
        raise ValueError("x_new must contain exactly one token")

    query = linear(x_new, query_weight)
    new_key = linear(x_new, key_weight)
    new_value = linear(x_new, value_weight)
    key_cache, value_cache = append_kv_cache()

    raise NotImplementedError("Implement exercise 7g")


def check_cached_self_attention_step() -> None:
    x_new = np.array([[0.0, 1.0]])
    key_cache = np.array([[1.0, 0.0]])
    value_cache = np.array([[1.0, 0.0]])
    identity = np.eye(2)

    expected_output = np.array(
        [[0.330238450673343, 0.669761549326657]]
    )
    expected_key_cache = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ]
    )
    expected_value_cache = expected_key_cache.copy()

    output, updated_key_cache, updated_value_cache = cached_self_attention_step(
        x_new,
        key_cache,
        value_cache,
        query_weight=identity,
        key_weight=identity,
        value_weight=identity,
        output_weight=identity,
    )
    np.testing.assert_allclose(output, expected_output)
    np.testing.assert_allclose(updated_key_cache, expected_key_cache)
    np.testing.assert_allclose(updated_value_cache, expected_value_cache)
    assert output.shape == x_new.shape


def main() -> None:
    check_linear()
    print("PASS exercise 1: linear projection")
    check_rms_norm()
    print("PASS exercise 2: RMS normalisation")
    check_residual()
    print("PASS exercise 3: residual connection")
    check_activations()
    print("PASS exercise 4: sigmoid and SiLU")
    check_gated_mlp()
    print("PASS exercise 5: gated MLP")
    check_situ_mlp()
    print("PASS exercise 6: Kimi SiTU gated MLP")
    check_softmax()
    print("PASS exercise 7a: softmax")
    check_scaled_attention_scores()
    print("PASS exercise 7b: scaled attention scores")
    check_causal_attention_weights()
    print("PASS exercise 7c: causal attention weights")
    check_attention_context()
    print("PASS exercise 7d: attention context")
    check_causal_self_attention()
    print("PASS exercise 7e: complete causal self-attention")
    check_append_kv_cache()
    print("PASS exercise 7f: append KV cache")
    check_cached_self_attention_step()
    print("PASS exercise 7g: cached self-attention step")


if __name__ == "__main__":
    main()
