"""Direct human-label and programmatic sources; no teacher probabilities substituted."""

import hashlib
import json

from data import validate_row


def stable_id(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def normalize_snli(row):
    labels = ["entailment", "neutral", "contradiction"]
    label = row["label"]
    if label not in range(3):
        raise ValueError("SNLI has no agreed gold label")
    if not row["premise"] or not row["hypothesis"]:
        raise ValueError("missing NLI input")
    state = {"premise": row["premise"], "hypothesis": row["hypothesis"]}
    repo = "stanfordnlp/snli"
    return validate_row(
        {
            "id": repo + ":" + stable_id(state),
            "source": repo,
            "source_task": "snli",
            "family_group": "snli",
            "license": "cc-by-sa-4.0",
            "state": state,
            "question": {
                "type": "choice",
                "instructions": "Given the premise, what is the relation of the hypothesis to it?",
                "criteria": labels,
            },
            "labels": labels,
            "descriptions": [
                "Entailed by the premise.",
                "Neither entailed nor contradicted by the premise.",
                "Contradicted by the premise.",
            ],
            "target": [float(i == label) for i in range(3)],
            "group": "nli-premise:" + stable_id(row["premise"]),
            "label_evidence": "original_human_gold",
            "language": "en",
        }
    )


def normalize_esci(row):
    labels = ["Exact", "Substitute", "Complement", "Irrelevant"]
    if row["esci_label"] not in labels:
        raise ValueError("unknown ESCI gold label")
    if not row["query"] or not row["product_title"]:
        raise ValueError("missing ESCI query/product input")
    product = {
        name.removeprefix("product_"): row.get(name)
        for name in (
            "product_title",
            "product_description",
            "product_bullet_point",
            "product_brand",
            "product_color",
        )
        if row.get(name)
    }
    repo = "tasksource/esci"
    return validate_row(
        {
            "id": repo
            + ":"
            + str(row["product_locale"])
            + ":"
            + str(row["example_id"]),
            "source": repo,
            "source_task": "esci",
            "family_group": "esci",
            "license": "apache-2.0",
            "state": {"query": row["query"], "product": product},
            "question": {
                "type": "choice",
                "instructions": "How relevant is this product to the search query?",
                "criteria": labels,
            },
            "labels": labels,
            "descriptions": [
                "An exact match that satisfies the query.",
                "A substitute that serves a similar purpose but is not an exact match.",
                "A complementary product used with the requested product.",
                "Irrelevant to the requested product or purpose.",
            ],
            "target": [float(label == row["esci_label"]) for label in labels],
            "group": repo
            + ":"
            + str(row["product_locale"])
            + ":"
            + str(row["query_id"]),
            "label_evidence": "original_query_product_gold",
            "language": {"us": "en", "es": "es", "jp": "ja"}.get(
                row["product_locale"], row["product_locale"]
            ),
        }
    )


def normalize_eikos(row):
    if (
        row.get("split") != "train"
        or row.get("item_writer") != "program"
        or row.get("label_source") not in ("program", "exact_probability")
    ):
        return None
    upstream = row.get("upstream")
    license_terms = row.get("license") or "cc-by-4.0"
    upstream_license = row.get("upstream_license") or row.get("source_license")
    if upstream:
        if row.get("upstream_split") != "train" and "train" not in upstream.lower():
            return None
        upstream_license = upstream_license or {
            "GSM8K train (MIT)": "mit",
            "TAT-QA (CC BY 4.0)": "cc-by-4.0",
        }.get(upstream)
        if not upstream_license:
            raise ValueError("Eikos upstream terms are unavailable")
        if upstream_license != license_terms:
            license_terms += "/" + upstream_license
    options = row["options"]
    labels = [option["label"] for option in options]
    descriptions = [option.get("description") or option["label"] for option in options]
    repo = "caiovicentino1/eikos-decisions"
    return validate_row(
        {
            "id": repo + ":" + row["id"],
            "source": repo,
            "source_task": "eikos/" + row["family"],
            "family_group": "eikos/" + row["family"],
            "license": license_terms,
            "attribution": {
                "upstream": upstream,
                "upstream_license": upstream_license,
                "source_origin": row.get("source"),
                "source_attribution": row.get("attribution"),
            },
            "state": row["state"],
            "question": {
                "type": row["question_type"],
                "instructions": row["instructions"],
                "criteria": descriptions,
            },
            "labels": labels,
            "descriptions": descriptions,
            "target": row["target_probs"],
            "group": repo + ":" + row["id"],
            "label_evidence": "source_programmatic_exact"
            if row["label_source"] == "exact_probability"
            else "source_programmatic_smoothed",
            "language": row.get("lang"),
        }
    )
