import math

import numpy as np

from gdecide import gate as G


def synthetic(n=400, seed=0):
    """Model B is right on non-ASCII questions, model A elsewhere; each is confident either way."""
    r = np.random.default_rng(seed)
    data = []
    for i in range(n):
        foreign = i % 2 == 0
        gold = int(r.integers(4))
        wrong = (gold + 1) % 4
        def dist(right):
            p = np.full(4, 0.05)
            p[gold if right else wrong] = 0.85
            return p
        pa, pb = dist(not foreign), dist(foreign)
        keys = list("ABCD")
        x = G.features(dict(zip(keys, pa)), dict(zip(keys, pb)), {"type": "choice"}, "é" * 50 if foreign else "e" * 50, 1)
        t = np.zeros(4)
        t[gold] = 1
        data.append((x, pa, pb, t))
    return data


def test_gradient_matches_finite_differences():
    b = G.Batch(synthetic(60))
    for hidden in (0, 4):
        g = G.Gate(b.X.shape[1], hidden, seed=1)
        g.mean, g.std = b.X.mean(0), b.X.std(0) + 1e-6
        g.mean[0], g.std[0] = 0.0, 1.0
        g.log_t = 0.2
        _, grads, glt = G.nll(g, b, 1e-3)
        p = g.params()[0]
        idx = (1, 0) if p.ndim == 2 else (1,)
        old = p[idx]
        p[idx] = old + 1e-5
        up = G.nll(g, b, 1e-3)[0]
        p[idx] = old - 1e-5
        down = G.nll(g, b, 1e-3)[0]
        p[idx] = old
        assert math.isclose(grads[0][idx], (up - down) / 2e-5, rel_tol=1e-3, abs_tol=1e-7)
        g.log_t += 1e-5
        up = G.nll(g, b, 1e-3)[0]
        g.log_t -= 2e-5
        down = G.nll(g, b, 1e-3)[0]
        assert math.isclose(glt, (up - down) / 2e-5, rel_tol=1e-3, abs_tol=1e-7)


def test_gate_learns_who_to_trust():
    data = synthetic()
    g = G.train(data, hidden=0, steps=300)
    b = G.Batch(data)
    assert G.evaluate(b, g.weight(b.X), g.log_t)["acc"] > 95
    assert G.evaluate(b, 0.5)["acc"] < 80  # ties between two confident answers


def test_gold_key():
    assert G.gold_key({"type": "noul"}, 0.9) == "true"
    assert G.gold_key({"type": "choice"}, {"A": 0.2, "B": 0.8}) == "B"
    assert G.gold_key({"type": "score"}, 2) == "2"
