"""Separate padding defects from batch-dependent floating-point effects."""

import argparse
import json
import time
from pathlib import Path

from data import read_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--target", default="hard-sol-b-long_policy-06")
    parser.add_argument("--pad", type=int, default=32)
    parser.add_argument("--extra", action="store_true")
    args = parser.parse_args()
    import torch
    from transformers import AutoTokenizer, Inkling2LoopForConditionalGeneration

    root = args.run_dir
    row = next(
        r
        for r in read_jsonl(root / "data/jevbench-231.jsonl")
        if r["id"] == args.target
    )
    tokenizer = AutoTokenizer.from_pretrained(root / "model")
    q = row["question"]
    if q["type"] == "noul":
        descriptions = [
            (q.get("criteria") or {}).get("false" if k == "no" else "true", k)
            for k in row["labels"]
        ]
    elif q["type"] == "score":
        descriptions = [q["criteria"][int(k)] for k in row["labels"]]
    else:
        descriptions = [q["criteria"][k] for k in row["labels"]]
    state = (
        row["state"]
        if isinstance(row["state"], str)
        else json.dumps(row["state"], ensure_ascii=False, sort_keys=True)
    )
    options = "\n".join(f"{chr(65 + i)}: {d}" for i, d in enumerate(descriptions))
    content = f"State:\n{state}\n\nQuestion:\n{q['instructions']}\n\nOptions:\n{options}\n\nChoose the correct option. Reply with its letter only."
    prompt = (
        tokenizer.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=False,
            reasoning_effort="none",
        )
        + "<|message_model|><|content_text|>"
    )
    ids = tokenizer.encode(prompt, add_special_tokens=False)
    labels = [
        tokenizer.encode(chr(65 + i), add_special_tokens=False)[0]
        for i in range(len(row["labels"]))
    ]
    model = Inkling2LoopForConditionalGeneration.from_pretrained(
        root / "model", dtype=torch.bfloat16, device_map="cuda"
    ).eval()
    torch.set_num_threads(12)
    records = []

    def run(name, batch=1, padding=0, explicit_positions=False):
        x = torch.tensor(
            [[tokenizer.pad_token_id] * padding + ids] * batch, device="cuda"
        )
        mask = torch.tensor([[0] * padding + [1] * len(ids)] * batch, device="cuda")
        inputs = {"input_ids": x, "attention_mask": mask}
        if explicit_positions:
            inputs["position_ids"] = (mask.cumsum(-1) - 1).clamp(min=0)
        start = time.monotonic()
        with torch.no_grad():
            z = (
                model(**inputs, use_cache=False, logits_to_keep=1)
                .logits[0, -1, labels]
                .float()
            )
            p = z.softmax(-1).tolist()
        torch.cuda.synchronize()
        record = {
            "name": name,
            "batch": batch,
            "padding": padding,
            "tokens": len(ids),
            "logits": z.tolist(),
            "probabilities": p,
            "seconds": time.monotonic() - start,
        }
        records.append(record)
        print(json.dumps(record), flush=True)

    if args.extra:
        run("bf16_repeated16", batch=16)
        run("bf16_large_padding", padding=args.pad)
    else:
        run("bf16_single")
        run("bf16_repeated", batch=4)
        run("bf16_padding", padding=args.pad)
        run("bf16_padding_positions", padding=args.pad, explicit_positions=True)
        torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = False
        run("bf16_full_reduction_single")
        run("bf16_full_reduction_padding", padding=args.pad)
    model.float()
    torch.backends.cuda.matmul.allow_tf32 = False
    if args.extra:
        run("fp32_repeated16", batch=16)
        run("fp32_large_padding", padding=args.pad)
    else:
        run("fp32_single")
        run("fp32_repeated", batch=4)
        run("fp32_padding", padding=args.pad)
    (
        root / ("batch-probe-extra.json" if args.extra else "batch-probe.json")
    ).write_text(json.dumps({"target": args.target, "records": records}, indent=2))


if __name__ == "__main__":
    main()
