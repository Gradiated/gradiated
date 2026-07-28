#!/usr/bin/env python3
"""Exact c32 tied-vocabulary recall scorer; --cuda is the admitted H200 path."""
import argparse, hashlib, json, time
from pathlib import Path

V, H = 262144, 5376
CANDIDATES = [128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768]
WEIGHT_SHA = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(16 << 20), b""):
            h.update(block)
    return h.hexdigest()

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--weight", type=Path, required=True)
    p.add_argument("--capture", type=Path, required=True)
    p.add_argument("--capture-terminal", type=Path, required=True)
    p.add_argument("--prior-terminal", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--science-marker", type=Path)
    p.add_argument("--cuda", action="store_true")
    p.add_argument("--owner-sha256", required=True)
    args = p.parse_args()
    import torch
    from safetensors import safe_open
    if args.cuda and not torch.cuda.is_available():
        raise RuntimeError("cuda_required_but_unavailable")
    device = torch.device("cuda" if args.cuda else "cpu")
    if not args.cuda:
        torch.set_num_threads(16)
    identities = {k: sha(v) for k, v in {
        "weight": args.weight, "capture": args.capture,
        "capture_terminal": args.capture_terminal, "prior_terminal": args.prior_terminal,
        "consumer": Path(__file__).resolve(),
    }.items()}
    identities["owner"] = args.owner_sha256
    if identities["weight"] != WEIGHT_SHA:
        raise RuntimeError("tied_weight_hash_mismatch")
    payload = torch.load(args.capture, map_location="cpu", weights_only=False)
    hidden = payload["hidden_states"].float()
    ownership = payload["ownership"]
    if tuple(hidden.shape) != (1536, H) or len(ownership) != 1536 or not torch.isfinite(hidden).all():
        raise RuntimeError("capture_contract_mismatch")
    request_ids = [str(row["request_id"]) for row in ownership]
    if len(set(request_ids)) != 32:
        raise RuntimeError("request_mapping_mismatch")
    with safe_open(args.weight, framework="pt", device="cpu") as handle:
        weight = handle.get_tensor("model.language_model.embed_tokens.weight")
    if tuple(weight.shape) != (V, H):
        raise RuntimeError("tied_weight_shape_mismatch")
    weight = weight.to(device)
    # The frozen geometry is variance-ranked tied-weight coordinates.
    moments = torch.zeros(H, dtype=torch.float64, device=device)
    for offset in range(0, V, 4096):
        moments += weight[offset:offset + 4096].float().square().sum(0, dtype=torch.float64)
    dims = torch.argsort(moments, descending=True, stable=True)[:256]
    if args.science_marker:
        put(args.science_marker, {"science_started": True, "stage": "h200_exact_dense_recall", "at_unix_s": time.time(), "cuda": args.cuda})
    torch.cuda.synchronize() if args.cuda else None
    started = time.monotonic()
    references, ranks = [], []
    for offset in range(0, 1536, 32 if args.cuda else 64):
        batch = hidden[offset:offset + (32 if args.cuda else 64)].to(device)
        exact = torch.full((batch.shape[0],), float("-inf"), device=device)
        exact_id = torch.zeros(batch.shape[0], dtype=torch.long, device=device)
        approx = torch.empty((batch.shape[0], V), dtype=torch.float32, device=device)
        for row in range(0, V, 4096):
            rows = weight[row:row + 4096].float()
            dense = batch @ rows.T
            values, indices = dense.max(1)
            update = values > exact
            exact[update], exact_id[update] = values[update], indices[update] + row
            approx[:, row:row + 4096] = batch[:, dims] @ rows[:, dims].T
        order = torch.argsort(approx, dim=1, descending=True, stable=True)
        found = (order == exact_id[:, None]).nonzero(as_tuple=False)[:, 1] + 1
        references.extend(exact_id.cpu().tolist())
        ranks.extend(found.cpu().tolist())
    if args.cuda:
        torch.cuda.synchronize()
    elapsed = time.monotonic() - started
    curves = []
    for count in CANDIDATES:
        wins = [rank <= count for rank in ranks]
        per_request = {rid: sum(wins[i] for i, got in enumerate(request_ids) if got == rid) / sum(got == rid for got in request_ids) for rid in sorted(set(request_ids))}
        index_bytes, exact_bytes = V * 256 * 2 + 256 * 2, count * H * 2
        approx_ops, exact_ops = 2 * 1536 * V * 256, 2 * 1536 * count * H
        bound = .00025 + approx_ops / (.25 * 989.5e12) + exact_ops / (.25 * 989.5e12) + (index_bytes + exact_bytes + count * 4) / (.5 * 4.8e12)
        curves.append({"candidate_rows": count, "global_exact_top1_recall": sum(wins) / 1536, "per_request_exact_top1_recall": per_request, "index_bytes": index_bytes, "lower_bound_hbm_bytes": index_bytes + exact_bytes + count * 4, "approximate_arithmetic_ops": approx_ops, "exact_arithmetic_ops": exact_ops, "routing_allowance_seconds": .00025, "analytical_additive_bound_seconds": bound})
    best = next((row for row in curves if row["global_exact_top1_recall"] == 1 and all(v == 1 for v in row["per_request_exact_top1_recall"].values())), None)
    comparator = .004182975769042969
    result = {"schema_version": 1, "classification": "h200_diverse_retrieval_score_terminal", "pass": True, "source_hashes": identities, "execution": {"cuda": args.cuda, "elapsed_seconds": elapsed, "submission_count": 1}, "geometry": {"rows": 1536, "requests": 32, "hidden": H, "vocab": V, "coordinate_dimensions": 256}, "dense_reference": {"top1_ids_sha256": hashlib.sha256(b"".join(int(v).to_bytes(4, "little") for v in references)).hexdigest()}, "candidate_curves": curves, "best_perfect_recall": best, "dense_comparator_seconds": comparator, "decision": {"continue_to_h200_consumer": bool(best and best["candidate_rows"] <= 8192 and best["analytical_additive_bound_seconds"] < comparator), "reason": "perfect global/per-request recall, candidate cap, and 4.183ms bound gate"}, "spend": {"gpu_claimed": args.cuda, "endpoint_requests": 0, "checkpoint_bytes_transferred": 0}}
    put(args.output, result)
    print(json.dumps({"best": None if best is None else best["candidate_rows"], "seconds": elapsed, "continue": result["decision"]["continue_to_h200_consumer"]}, sort_keys=True))

if __name__ == "__main__":
    main()
