import json
import os
import sys
from pathlib import Path

OUT = Path(os.environ["DFLASH_CYCLE_CAPTURE"])


def _rows(value):
    if "draft_tokens" not in value or "target_predict" not in value:
        return []
    import torch
    torch.cuda.synchronize()
    draft = value["draft_tokens"].detach().cpu().tolist()
    target = value["target_predict"].detach().cpu().tolist()
    batch, width = len(draft), len(draft[0])
    logits = value["logits_output"].next_token_logits.view(batch, width, -1)
    ids = value["target_predict"].to(dtype=torch.long).unsqueeze(-1)
    scores = logits.gather(-1, ids).squeeze(-1).detach().float().cpu().tolist()
    tensors = {name: value[name].detach().cpu().tolist() for name in ("accept_len", "commit_lens", "bonus", "out_tokens", "prefix_lens", "new_seq_lens", "positions_2d", "verify_out_cache_loc_2d")}
    seeds = value["next_draft_input"].verified_id.detach().cpu().tolist()
    rows = []
    for i in range(batch):
        accepted, commit = int(tensors["accept_len"][i]), int(tensors["commit_lens"][i])
        rows.append({"request_id": str(i), "cycle_index": None, "block_size": width, "draft_tokens": draft[i], "verifier_top1_ids": target[i], "verifier_top1_logits": scores[i], "accepted_draft_count": accepted, "accepted_prefix": draft[i][1:1 + accepted], "bonus_token": int(tensors["bonus"][i]), "emitted_tokens": tensors["out_tokens"][i][:commit], "kv_write_positions": tensors["positions_2d"][i], "kv_write_locations": tensors["verify_out_cache_loc_2d"][i], "committed_kv_write_locations": tensors["verify_out_cache_loc_2d"][i][:commit], "committed_length_before": int(tensors["prefix_lens"][i]), "commit_length": commit, "committed_length_after": int(tensors["new_seq_lens"][i]), "next_cycle_seed": int(seeds[i]), "next_cycle_committed_length": int(tensors["new_seq_lens"][i]), "ar_cycle_tokens": target[i], "next_ar_token": int(tensors["bonus"][i])})
    return rows


def _trace(frame, event, arg):
    if event == "return" and frame.f_code.co_name == "forward_batch_generation" and frame.f_code.co_filename.endswith("dflash_worker_v2.py"):
        try:
            rows = _rows(frame.f_locals)
            if rows:
                OUT.parent.mkdir(parents=True, exist_ok=True)
                with OUT.open("a") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
        except Exception as exc:
            OUT.with_suffix(".observer-error").write_text(repr(exc) + "\n")
    return _trace


sys.settrace(_trace)
