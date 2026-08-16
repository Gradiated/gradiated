#!/usr/bin/env python3
"""Measure OpenRouter's realized provider routing for controlled request cohorts.

The probe never stores prompts, responses, or credentials. It is intentionally
opt-in because it sends paid API traffic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = "https://openrouter.ai"
DEFAULT_DATABASE = Path(".agents/runtime/openrouter-provider-share/route-probes.sqlite3")
DEFAULT_MODEL = "z-ai/glm-5.2"
SCHEMA = """
CREATE TABLE IF NOT EXISTS probe_runs (
    id INTEGER PRIMARY KEY,
    captured_at TEXT NOT NULL,
    model TEXT NOT NULL,
    cohort TEXT NOT NULL,
    requested_samples INTEGER NOT NULL,
    successful_samples INTEGER NOT NULL,
    failed_samples INTEGER NOT NULL,
    total_cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS probe_observations (
    run_id INTEGER NOT NULL REFERENCES probe_runs(id),
    sample_index INTEGER NOT NULL,
    generation_id TEXT,
    provider_name TEXT,
    success INTEGER NOT NULL,
    total_cost REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    latency_ms INTEGER,
    error_type TEXT,
    PRIMARY KEY (run_id, sample_index)
);
"""


def _request_json(
    path: str, api_key: str, *, payload: dict[str, object] | None = None
) -> dict[str, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path,
        data=body,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Inference-Foundry-route-probe/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def _payload(model: str, cohort: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 4,
    }
    if cohort == "tool":
        payload.update(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "return_ok",
                            "description": "Return the fixed probe result.",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "return_ok"},
                },
            }
        )
    elif cohort != "non_tool":
        raise ValueError(f"unsupported cohort: {cohort}")
    return payload


def _generation_metadata(
    generation_id: str, api_key: str, *, attempts: int = 8
) -> dict[str, object]:
    path = "/api/v1/generation?" + urllib.parse.urlencode({"id": generation_id})
    for attempt in range(attempts):
        value = _request_json(path, api_key).get("data") or {}
        if value.get("provider_name"):
            return value
        if attempt + 1 < attempts:
            time.sleep(0.5)
    raise TimeoutError("generation metadata did not expose a provider in time")


def run_probe(
    database: Path,
    *,
    api_key: str,
    model: str,
    cohort: str,
    samples: int,
    max_spend_usd: float,
    delay_seconds: float,
) -> dict[str, object]:
    if samples < 1 or max_spend_usd <= 0:
        raise ValueError("samples and max_spend_usd must be positive")
    observations: list[dict[str, object]] = []
    total_cost = 0.0
    for sample_index in range(samples):
        if total_cost >= max_spend_usd:
            break
        started = time.monotonic()
        try:
            response = _request_json(
                "/api/v1/chat/completions", api_key, payload=_payload(model, cohort)
            )
            generation_id = str(response["id"])
            metadata = _generation_metadata(generation_id, api_key)
            cost = float(metadata.get("total_cost") or metadata.get("usage") or 0.0)
            total_cost += cost
            observations.append(
                {
                    "sample_index": sample_index,
                    "generation_id": generation_id,
                    "provider_name": metadata.get("provider_name"),
                    "success": 1,
                    "total_cost": cost,
                    "prompt_tokens": metadata.get("native_tokens_prompt"),
                    "completion_tokens": metadata.get("native_tokens_completion"),
                    "latency_ms": round((time.monotonic() - started) * 1_000),
                    "error_type": None,
                }
            )
        except Exception as error:
            observations.append(
                {
                    "sample_index": sample_index,
                    "generation_id": None,
                    "provider_name": None,
                    "success": 0,
                    "total_cost": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "latency_ms": round((time.monotonic() - started) * 1_000),
                    "error_type": type(error).__name__,
                }
            )
        if delay_seconds > 0 and sample_index + 1 < samples:
            time.sleep(delay_seconds)

    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    successful = sum(int(row["success"]) for row in observations)
    with connection:
        cursor = connection.execute(
            "INSERT INTO probe_runs "
            "(captured_at, model, cohort, requested_samples, successful_samples, "
            "failed_samples, total_cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                dt.datetime.now(dt.timezone.utc).isoformat(),
                model,
                cohort,
                samples,
                successful,
                len(observations) - successful,
                total_cost,
            ),
        )
        run_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT INTO probe_observations "
            "(run_id, sample_index, generation_id, provider_name, success, total_cost, "
            "prompt_tokens, completion_tokens, latency_ms, error_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id,
                    row["sample_index"],
                    row["generation_id"],
                    row["provider_name"],
                    row["success"],
                    row["total_cost"],
                    row["prompt_tokens"],
                    row["completion_tokens"],
                    row["latency_ms"],
                    row["error_type"],
                )
                for row in observations
            ],
        )
    connection.close()
    providers: dict[str, int] = {}
    for row in observations:
        if row["provider_name"]:
            name = str(row["provider_name"])
            providers[name] = providers.get(name, 0) + 1
    return {
        "run_id": run_id,
        "cohort": cohort,
        "attempted": len(observations),
        "successful": successful,
        "total_cost": total_cost,
        "provider_counts": providers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cohort", choices=("non_tool", "tool"), required=True)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--max-spend-usd", type=float, required=True)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("refusing paid traffic without --execute")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is required")
    print(
        json.dumps(
            run_probe(
                args.database,
                api_key=api_key,
                model=args.model,
                cohort=args.cohort,
                samples=args.samples,
                max_spend_usd=args.max_spend_usd,
                delay_seconds=args.delay_seconds,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
