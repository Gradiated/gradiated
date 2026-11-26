"""One exact visible-input renderer for training and tokenizer audits."""

import json


def render_prompt(tokenizer, row):
    state = row["state"]
    if not isinstance(state, str):
        state = json.dumps(state, ensure_ascii=False, sort_keys=True)
    instruction = row["question"]["instructions"]
    if not isinstance(instruction, str):
        instruction = json.dumps(instruction, ensure_ascii=False)
    options = "\n".join(
        f"{chr(65 + i)}: {description}"
        for i, description in enumerate(row["descriptions"])
    )
    content = f"State:\n{state}\n\nQuestion:\n{instruction}\n\nOptions:\n{options}\n\nChoose the correct option. Reply with its letter only."
    return (
        tokenizer.apply_chat_template(
            [{"role": "user", "content": content}],
            tokenize=False,
            reasoning_effort="none",
        )
        + "<|message_model|><|content_text|>"
    )
