"""Compute MoE routing statistics from captured top-k indices.

Inputs: experiments/results/twin/granite_routing/routing_topk.npz (+ capture_meta.json)
Outputs (same dir):
  loads.npy        (L, E)    tokens routed to each expert (count over top-k slots)
  coactivation.npy (L, E, E) co-selection counts (diag = loads)
  summary.json     per-layer Gini, hot-set sizes, coverage curves, group stats
"""

import json

import numpy as np

from common import RESULTS

OUT = RESULTS / "granite_routing"


def gini(x: np.ndarray) -> float:
    x = np.sort(x.astype(np.float64))
    n = x.size
    if x.sum() == 0:
        return 0.0
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum / cum[-1]).sum()) / n)


def hot_set_size(loads: np.ndarray, frac: float) -> int:
    order = np.sort(loads)[::-1]
    cum = np.cumsum(order) / order.sum()
    return int(np.searchsorted(cum, frac) + 1)


def greedy_balanced_groups(affinity: np.ndarray, n_groups: int) -> np.ndarray:
    """Balanced greedy agglomeration: seed groups with the mutually least-affine
    experts, then repeatedly assign the unassigned expert with the highest
    affinity to any non-full group."""
    E = affinity.shape[0]
    cap = E // n_groups
    A = affinity.copy()
    np.fill_diagonal(A, -np.inf)

    total_aff = np.where(np.isfinite(A), A, 0).sum(1)
    seeds = [int(np.argmax(total_aff))]
    while len(seeds) < n_groups:
        dist_to_seeds = A[:, seeds].max(1)
        dist_to_seeds[seeds] = np.inf
        seeds.append(int(np.argmin(dist_to_seeds)))

    groups = -np.ones(E, dtype=np.int64)
    for g, s in enumerate(seeds):
        groups[s] = g
    sizes = np.ones(n_groups, dtype=np.int64)
    unassigned = set(range(E)) - set(seeds)
    while unassigned:
        best = (-np.inf, None, None)
        for e in unassigned:
            for g in range(n_groups):
                if sizes[g] >= cap:
                    continue
                members = np.where(groups == g)[0]
                score = A[e, members].mean()
                if score > best[0]:
                    best = (score, e, g)
        _, e, g = best
        groups[e] = g
        sizes[g] += 1
        unassigned.discard(e)
    return groups


def refine_groups(topk: np.ndarray, groups: np.ndarray, n_groups: int, iters: int = 10) -> np.ndarray:
    """Balanced local search: swap pairs of experts across groups if it reduces
    the mean number of distinct groups touched per token."""
    E = groups.size

    def mean_groups(g):
        return np.take(g, topk).astype(np.int64), None

    def cost(g):
        tok_groups = np.take(g, topk)  # (T, k)
        # distinct groups per token
        s = np.sort(tok_groups, axis=1)
        distinct = 1 + (s[:, 1:] != s[:, :-1]).sum(1)
        return distinct.mean()

    cur = cost(groups)
    for _ in range(iters):
        improved = False
        for a in range(E):
            for b in range(a + 1, E):
                if groups[a] == groups[b]:
                    continue
                g2 = groups.copy()
                g2[a], g2[b] = g2[b], g2[a]
                c2 = cost(g2)
                if c2 < cur - 1e-9:
                    groups, cur = g2, c2
                    improved = True
        if not improved:
            break
    return groups


def main():
    meta = json.loads((OUT / "capture_meta.json").read_text())
    L, E, K = meta["layers"], meta["experts"], meta["top_k"]
    npz = np.load(OUT / "routing_topk.npz")
    wiki_end = meta["domain_boundary"]

    loads = np.zeros((L, E), dtype=np.int64)
    coact = np.zeros((L, E, E), dtype=np.int64)
    summary = {"meta": meta, "layers": []}

    for li in range(L):
        topk = npz[f"layer_{li:02d}"].astype(np.int64)  # (T, K)
        T = topk.shape[0]
        onehot = np.zeros((T, E), dtype=np.int64)
        np.put_along_axis(onehot, topk, 1, axis=1)
        loads[li] = onehot.sum(0)
        coact[li] = onehot.T @ onehot

        # affinity: cosine-normalised co-activation, diag removed
        d = np.sqrt(np.maximum(loads[li], 1)).astype(np.float64)
        aff = coact[li] / np.outer(d, d)

        layer_stats = {
            "layer": li,
            "gini": round(gini(loads[li]), 4),
            "load_max_over_mean": round(float(loads[li].max() / loads[li].mean()), 2),
            "load_min_over_mean": round(float(loads[li].min() / loads[li].mean()), 3),
            "hot_set_80": hot_set_size(loads[li], 0.80),
            "hot_set_95": hot_set_size(loads[li], 0.95),
            "coverage_curve": [
                round(float(c), 4)
                for c in np.cumsum(np.sort(loads[li])[::-1]) / loads[li].sum()
            ],
            "gini_wiki": round(gini(onehot[:wiki_end].sum(0)), 4),
            "gini_code": round(gini(onehot[wiki_end:].sum(0)), 4),
            "groups": {},
        }

        for G in (4, 8):
            groups = greedy_balanced_groups(aff, G)
            groups = refine_groups(topk, groups, G, iters=4)
            tok_groups = np.take(groups, topk)
            s = np.sort(tok_groups, axis=1)
            distinct = 1 + (s[:, 1:] != s[:, :-1]).sum(1)
            min_possible = int(np.ceil(K / (E // G)))
            layer_stats["groups"][f"G{G}"] = {
                "group_size": E // G,
                "min_groups_per_token": min_possible,
                "mean_groups_per_token": round(float(distinct.mean()), 3),
                "frac_tokens_gt1_group": round(float((distinct > 1).mean()), 4),
                "frac_tokens_gt_min_groups": round(float((distinct > min_possible).mean()), 4),
                "assignment": groups.tolist(),
            }
        summary["layers"].append(layer_stats)
        print(
            f"L{li:02d} gini={layer_stats['gini']:.3f} hot80={layer_stats['hot_set_80']} "
            f"hot95={layer_stats['hot_set_95']} "
            f"G4>1grp={layer_stats['groups']['G4']['frac_tokens_gt1_group']:.3f} "
            f"G8 mean grps={layer_stats['groups']['G8']['mean_groups_per_token']:.2f}",
            flush=True,
        )

    # cross-domain expert overlap: do wiki and code use the same hot sets?
    overlaps = []
    for li in range(L):
        topk = npz[f"layer_{li:02d}"].astype(np.int64)
        oh = np.zeros((topk.shape[0], E), dtype=np.int64)
        np.put_along_axis(oh, topk, 1, axis=1)
        lw, lc = oh[:wiki_end].sum(0), oh[wiki_end:].sum(0)
        hw = set(np.argsort(lw)[::-1][: hot_set_size(lw, 0.80)])
        hc = set(np.argsort(lc)[::-1][: hot_set_size(lc, 0.80)])
        overlaps.append(round(len(hw & hc) / max(len(hw | hc), 1), 3))
    summary["hot80_jaccard_wiki_vs_code_per_layer"] = overlaps

    agg = {
        "gini_mean": round(float(np.mean([l["gini"] for l in summary["layers"]])), 4),
        "gini_min": round(float(np.min([l["gini"] for l in summary["layers"]])), 4),
        "gini_max": round(float(np.max([l["gini"] for l in summary["layers"]])), 4),
        "hot_set_80_mean": round(float(np.mean([l["hot_set_80"] for l in summary["layers"]])), 1),
        "hot_set_95_mean": round(float(np.mean([l["hot_set_95"] for l in summary["layers"]])), 1),
        "G4_frac_gt1_group_mean": round(float(np.mean(
            [l["groups"]["G4"]["frac_tokens_gt1_group"] for l in summary["layers"]])), 4),
        "G4_mean_groups_per_token": round(float(np.mean(
            [l["groups"]["G4"]["mean_groups_per_token"] for l in summary["layers"]])), 3),
        "G8_mean_groups_per_token": round(float(np.mean(
            [l["groups"]["G8"]["mean_groups_per_token"] for l in summary["layers"]])), 3),
        "G8_frac_gt_min_groups_mean": round(float(np.mean(
            [l["groups"]["G8"]["frac_tokens_gt_min_groups"] for l in summary["layers"]])), 4),
        "hot80_jaccard_wiki_vs_code_mean": round(float(np.mean(overlaps)), 3),
    }
    summary["aggregate"] = agg

    np.save(OUT / "loads.npy", loads)
    np.save(OUT / "coactivation.npy", coact)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
