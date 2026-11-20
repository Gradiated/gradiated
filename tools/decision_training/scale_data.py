"""Adapters for audited scale-up candidates; conversion does not admit a source."""

import json
import re

from data import text, validate_row


def canonical_family(source):
    return re.sub(r"(?:\+(?:fmt|long|para))+$", "", source).lower()


def repair_event_probability_wording(task, key, instructions):
    """Make native k/n event targets answer an event, not a probability threshold."""
    if task != "arithmetic" or "more likely than not" not in instructions:
        return instructions
    if key == "random_is_deposit" and instructions == (
        "If one transaction is picked uniformly at random, "
        "is it more likely than not to be a deposit?"
    ):
        return "If one transaction is picked uniformly at random, is it a deposit?"
    if key == "random_is_deposit" and instructions == (
        "Is a randomly chosen transaction more likely than not a deposit?"
    ):
        return "Is a uniformly randomly chosen transaction a deposit?"
    match = re.fullmatch(
        r"Is a randomly chosen line more likely than not to order (\d+) or more units\?",
        instructions,
    )
    if key == "random_line_bulk" and match:
        return f"Does a uniformly randomly chosen line order {match[1]} or more units?"
    match = re.fullmatch(
        r"If one order line is picked uniformly at random, is its quantity "
        r"more likely than not to be at least (\d+)\?",
        instructions,
    )
    if key == "random_line_bulk" and match:
        return (
            "If one order line is picked uniformly at random, "
            f"is its quantity at least {match[1]}?"
        )
    match = re.fullmatch(
        r"If one task is picked uniformly at random, is it more likely than not "
        r"to last more than (\d+) minutes\?",
        instructions,
    )
    if key == "random_is_long" and match:
        return (
            "If one task is picked uniformly at random, "
            f"does it last more than {match[1]} minutes?"
        )
    match = re.fullmatch(
        r"Is a randomly chosen task more likely than not to take longer "
        r"than (\d+) minutes\?",
        instructions,
    )
    if key == "random_is_long" and match:
        return f"Does a uniformly randomly chosen task take longer than {match[1]} minutes?"
    raise ValueError("unreviewed arithmetic probability-threshold wording")


def normalize_verqen(row, question_offset=0):
    """Keep source-family grouping across format, context and paraphrase stages."""
    repo = "zorqelis-ai/verqen-decisions"
    source = canonical_family(row["source"])
    questions = row["questions"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    for index, question in enumerate(questions, start=question_offset):
        options = question["options"]
        kind = question["type"]
        if len(set(map(text, options))) != len(options):
            raise ValueError("ambiguous repeated option descriptions")
        if not question["text"].strip():
            raise ValueError("empty question instructions")
        labels = [str(i) for i in range(len(options))]
        yield validate_row(
            {
                "id": f"{repo}:{row['id']}:q{index}",
                "source": repo,
                "source_task": source,
                "license": row["license"],
                "state": row["state"],
                "question": {
                    "type": kind,
                    "instructions": question["text"],
                    "criteria": options,
                },
                "labels": labels,
                "descriptions": options,
                "target": question["target"],
                "group": repo + ":" + row["id"],
                "family_group": source,
                "label_evidence": "source_target_requires_semantic_audit",
            }
        )


def normalize_procedural(row):
    """Expand native questions with exact probability/option alignment preserved."""
    repo = "tasksource/procedural-typed-decisions"
    questions = row["questions"]
    answers = row["answers"]
    if isinstance(questions, str):
        questions = json.loads(questions)
    if isinstance(answers, str):
        answers = json.loads(answers)
    if set(questions) != set(answers):
        raise ValueError("native question/answer IDs differ")
    for key, question in questions.items():
        answer = answers[key]
        kind = question["type"]
        criteria = question.get("criteria")
        if kind == "noul":
            labels, descriptions = ["false", "true"], ["No", "Yes"]
            p_true = answer["noul"]
            target = [1 - p_true, p_true]
        elif kind == "score":
            labels = [str(i) for i in range(len(criteria))]
            descriptions = criteria
            target = [answer["probabilities"][label] for label in labels]
        elif kind == "choice":
            labels = list(criteria)
            descriptions = [criteria[label] or label for label in labels]
            target = [answer["probabilities"][label] for label in labels]
        else:
            raise ValueError("unsupported native question type")
        if len(set(map(text, descriptions))) != len(descriptions):
            raise ValueError("ambiguous repeated option descriptions")
        instructions = repair_event_probability_wording(
            row["task"], key, question["instructions"]
        )
        yield validate_row(
            {
                "id": f"{repo}:{row['id']}:{key}",
                "source": repo,
                "source_task": repo + "/" + row["task"] + "/" + key,
                "license": "apache-2.0",
                "state": row["state"],
                "question": {
                    **question,
                    "criteria": criteria,
                    "instructions": instructions,
                },
                "labels": labels,
                "descriptions": descriptions,
                "target": target,
                "group": repo + ":" + row["id"],
                "family_group": repo + "/" + row["task"],
                "label_evidence": "programmatic_target_requires_rendering_audit",
                "curation": (
                    {
                        "repair": "native-event-probability-wording-v1",
                        "original_instructions": question["instructions"],
                    }
                    if instructions != question["instructions"]
                    else None
                ),
            }
        )
