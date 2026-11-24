"""Build and score closed-book questions about explicit cross-file C++ calls."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import random
import re

BASE = "Qwen/Qwen2.5-Coder-7B-Instruct"
REVISION = "c03e6d358207e414f1eca0bb1891e29f1db0e242"
SYMBOL = r"[A-Za-z_]\w*::[A-Za-z_]\w*"
DEFINITION = re.compile(r"^([^\n;{}]*?)\b(" + SYMBOL + r")\s*\([^;{}]*?\)\s*(?:const\s*)?\{", re.M)
CALL = re.compile(r"\b(" + SYMBOL + r")\s*\(")
COMMENTS = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def build(source):
    definitions = defaultdict(list)
    with gzip.open(source, "rt") as files:
        for row in map(json.loads, files):
            path = row["path"]
            if not (path.startswith("src/") and path.endswith(".cpp")):
                continue
            code = COMMENTS.sub(" ", row["body"])
            for match in DEFINITION.finditer(code):
                if not match[1].strip() or not match[1][0].isalpha():
                    continue
                # DuckDB formats the closing brace of a top-level method at column zero.
                end = re.search(r"^}", code[match.end():], re.M)
                if end:
                    body = code[match.end():match.end() + end.start()]
                    definitions[match[2]].append((path, set(CALL.findall(body))))
    rng = random.Random(8492)
    rows = []
    for caller, locations in sorted(definitions.items()):
        if len(locations) != 1:
            continue
        path, calls = locations[0]
        options = []
        for callee in sorted(calls):
            if len(definitions.get(callee, ())) != 1 or definitions[callee][0][0] == path:
                continue
            owner = callee.split("::")[0]
            alternatives = sorted(k for k in definitions if k.split("::")[0] == owner
                                  and k not in calls and k != caller and len(definitions[k]) == 1)
            if len(alternatives) >= 3:
                choices = [callee, *rng.sample(alternatives, 3)]
                rng.shuffle(choices)
                options.append(dict(caller=caller, path=path, choices=choices, answer=callee))
        if options:
            rows.append(rng.choice(options))
    rng.shuffle(rows)
    return rows[:256]


def score(rows, model_path):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    revision = REVISION if model_path == BASE else None
    tok = AutoTokenizer.from_pretrained(model_path, revision=revision, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_path, revision=revision, dtype=torch.bfloat16).cuda().eval()
    labels = "ABCD"
    ids = [tok.encode(x, add_special_tokens=False) for x in labels]
    assert all(len(x) == 1 for x in ids)
    results = []
    with torch.inference_mode():
        for start in range(0, len(rows), 8):
            prompts = []
            keys = []
            for row in rows[start:start + 8]:
                for rotation in range(4):
                    choices = row["choices"][rotation:] + row["choices"][:rotation]
                    text = (f"In the May 2020 DuckDB source, which function does {row['caller']} "
                            "explicitly call in its implementation?\n" +
                            "\n".join(f"{k}. {c}" for k, c in zip(labels, choices)) +
                            "\nAnswer with the option letter only.")
                    prompts.append(tok.apply_chat_template([dict(role="user", content=text)],
                                                           tokenize=False, add_generation_prompt=True))
                    keys.append(choices.index(row["answer"]))
            batch = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
            logits = model(**batch, logits_to_keep=1).logits[:, -1, [x[0] for x in ids]]
            correct = [int(i == k) for i, k in zip(logits.argmax(-1).tolist(), keys)]
            results.extend(sum(correct[i:i+4])/4 for i in range(0, len(correct), 4))
    return dict(accuracy=sum(results)/len(results), questions=len(results), scores=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model")
    args = parser.parse_args()
    result = score(json.loads(args.input.read_text()), args.model) if args.model else build(args.input)
    args.output.write_text(json.dumps(result) + "\n")
