#!/usr/bin/env python3
"""Collect longitudinal public OpenRouter provider-routing observations."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable
from pathlib import Path


BASE_URL = "https://openrouter.ai"
DEFAULT_PERMASLUG = "z-ai/glm-5.2-20260616"
DEFAULT_VARIANT = "standard"
DEFAULT_DATABASE = Path(".agents/runtime/openrouter-provider-share/glm52.sqlite3")
Fetcher = Callable[[str, int | None], object]
SIGNAL_PATHS = {
    "throughput_3d": "throughput-comparison",
    "latency_3d": "latency-comparison",
    "latency_e2e_3d": "latency-e2e-comparison",
    "tool_error_3d": "tool-call-error-rate",
    "structured_output_error_3d": "structured-output-error-rate",
    "cache_hit_3d": "cache-hit-rate-comparison",
    "benchmark_scores": "benchmark-scores",
    "uptime_recent": "uptime-recent",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY,
    captured_at TEXT NOT NULL,
    permaslug TEXT NOT NULL,
    variant TEXT NOT NULL,
    effective_samples INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_snapshots (
    run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    kind TEXT NOT NULL,
    sample_index INTEGER NOT NULL DEFAULT -1,
    body_sha256 TEXT NOT NULL,
    body_zlib BLOB NOT NULL,
    PRIMARY KEY (run_id, kind, sample_index)
);
CREATE TABLE IF NOT EXISTS provider_share_observations (
    run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    sample_index INTEGER NOT NULL,
    provider_name TEXT NOT NULL,
    provider_slug TEXT NOT NULL,
    total_tokens INTEGER NOT NULL,
    token_share REAL NOT NULL,
    effective_input_price REAL,
    effective_output_price REAL,
    cache_hit_rate REAL,
    PRIMARY KEY (run_id, sample_index, provider_name, provider_slug)
);
CREATE TABLE IF NOT EXISTS endpoint_observations (
    run_id INTEGER NOT NULL REFERENCES collection_runs(id),
    endpoint_id TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    provider_slug TEXT NOT NULL,
    input_price REAL NOT NULL,
    cache_read_price REAL NOT NULL,
    output_price REAL NOT NULL,
    discount REAL,
    quantization TEXT,
    context_length INTEGER,
    max_completion_tokens INTEGER,
    supported_parameters_json TEXT NOT NULL,
    status INTEGER,
    successes_1d INTEGER,
    derankable_errors_1d INTEGER,
    rate_limited_1d INTEGER,
    p50_throughput REAL,
    p50_latency_ms REAL,
    stats_request_count INTEGER,
    stats_window_minutes INTEGER,
    PRIMARY KEY (run_id, endpoint_id)
);
CREATE TABLE IF NOT EXISTS model_observations (
    run_id INTEGER PRIMARY KEY REFERENCES collection_runs(id),
    activity_date TEXT NOT NULL,
    requests INTEGER NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cached_prompt_tokens INTEGER NOT NULL,
    tool_calls INTEGER NOT NULL,
    tool_error_requests INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS provider_share_time_idx
    ON provider_share_observations(provider_slug, provider_name, run_id);
CREATE INDEX IF NOT EXISTS endpoint_time_idx
    ON endpoint_observations(provider_slug, run_id);
"""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _insert_raw(
    connection: sqlite3.Connection,
    run_id: int,
    kind: str,
    value: object,
    sample_index: int = -1,
) -> None:
    body = _json_bytes(value)
    connection.execute(
        "INSERT INTO raw_snapshots "
        "(run_id, kind, sample_index, body_sha256, body_zlib) VALUES (?, ?, ?, ?, ?)",
        (run_id, kind, sample_index, hashlib.sha256(body).hexdigest(), zlib.compress(body, 9)),
    )


def _http_json(path: str) -> object:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"User-Agent": "Inference-Foundry-provider-share-collector/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def make_public_fetcher(permaslug: str, variant: str) -> Fetcher:
    query = urllib.parse.urlencode({"permaslug": permaslug, "variant": variant})

    def fetch(kind: str, sample_index: int | None) -> object:
        if kind == "effective_pricing":
            cache_buster = urllib.parse.urlencode(
                {"collector_sample": f"{sample_index}-{random.random()}"}
            )
            return _http_json(f"/api/frontend/v1/stats/effective-pricing?{query}&{cache_buster}")
        if kind == "endpoints":
            return _http_json(f"/api/frontend/v1/stats/endpoint?{query}")
        if kind == "activity":
            return _http_json(f"/api/frontend/v1/stats/model-activity?{query}")
        if kind in SIGNAL_PATHS:
            signal_query = query + "&" + urllib.parse.urlencode({"timeRange": "3d"})
            return _http_json(
                f"/api/frontend/v1/stats/{SIGNAL_PATHS[kind]}?{signal_query}"
            )
        raise ValueError(f"unsupported snapshot kind: {kind}")

    return fetch


def collect_once(
    database: Path,
    *,
    permaslug: str = DEFAULT_PERMASLUG,
    variant: str = DEFAULT_VARIANT,
    effective_samples: int = 3,
    captured_at: str | None = None,
    fetcher: Fetcher | None = None,
) -> int:
    if effective_samples < 1:
        raise ValueError("effective_samples must be positive")
    fetch = fetcher or make_public_fetcher(permaslug, variant)
    endpoints = fetch("endpoints", None)
    activity = fetch("activity", None)
    effective = [fetch("effective_pricing", index) for index in range(effective_samples)]
    signals: dict[str, object] = {}
    for kind in SIGNAL_PATHS:
        try:
            signals[kind] = fetch(kind, None)
        except Exception as error:
            # A missing secondary chart must not discard the required share snapshot.
            signals[kind] = {
                "collector_error": type(error).__name__,
                "message": str(error),
            }
    if not isinstance(endpoints, list):
        raise TypeError("endpoint response must be a list")
    if not isinstance(activity, dict) or not activity.get("analytics"):
        raise TypeError("activity response must contain analytics")

    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(SCHEMA)
    timestamp = captured_at or dt.datetime.now(dt.timezone.utc).isoformat()

    with connection:
        cursor = connection.execute(
            "INSERT INTO collection_runs "
            "(captured_at, permaslug, variant, effective_samples) VALUES (?, ?, ?, ?)",
            (timestamp, permaslug, variant, effective_samples),
        )
        run_id = int(cursor.lastrowid)
        _insert_raw(connection, run_id, "endpoints", endpoints)
        _insert_raw(connection, run_id, "activity", activity)
        for kind, signal in signals.items():
            _insert_raw(connection, run_id, kind, signal)
        for sample_index, sample in enumerate(effective):
            _insert_raw(connection, run_id, "effective_pricing", sample, sample_index)
            summaries = sample.get("providerSummaries", [])
            total_tokens = sum(int(row["totalTokens"]) for row in summaries)
            if total_tokens <= 0:
                raise ValueError("effective-pricing sample has no tokens")
            for row in summaries:
                connection.execute(
                    "INSERT INTO provider_share_observations "
                    "(run_id, sample_index, provider_name, provider_slug, total_tokens, "
                    "token_share, effective_input_price, effective_output_price, cache_hit_rate) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        sample_index,
                        row["providerName"],
                        row["providerSlug"],
                        int(row["totalTokens"]),
                        int(row["totalTokens"]) / total_tokens,
                        row.get("effectiveInputPrice"),
                        row.get("effectiveOutputPrice"),
                        row.get("cacheHitRate"),
                    ),
                )

        for endpoint in endpoints:
            pricing = endpoint["pricing"]
            stats = endpoint.get("stats") or {}
            status = endpoint.get("status_heuristics_1d") or {}
            input_price = float(pricing["prompt"]) * 1_000_000
            cache_price = float(pricing.get("input_cache_read") or pricing["prompt"]) * 1_000_000
            output_price = float(pricing["completion"]) * 1_000_000
            connection.execute(
                "INSERT INTO endpoint_observations "
                "(run_id, endpoint_id, provider_name, provider_slug, input_price, "
                "cache_read_price, output_price, discount, quantization, context_length, "
                "max_completion_tokens, supported_parameters_json, status, successes_1d, "
                "derankable_errors_1d, rate_limited_1d, p50_throughput, p50_latency_ms, "
                "stats_request_count, stats_window_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    endpoint["id"],
                    endpoint["provider_display_name"],
                    endpoint["provider_slug"],
                    input_price,
                    cache_price,
                    output_price,
                    pricing.get("discount"),
                    endpoint.get("quantization"),
                    endpoint.get("context_length"),
                    endpoint.get("max_completion_tokens"),
                    json.dumps(sorted(endpoint.get("supported_parameters") or [])),
                    endpoint.get("status"),
                    status.get("success"),
                    status.get("derankableError"),
                    status.get("rateLimited"),
                    stats.get("p50_throughput"),
                    stats.get("p50_latency"),
                    stats.get("request_count"),
                    stats.get("window_minutes"),
                ),
            )

        latest = max(activity["analytics"], key=lambda row: row["date"])
        connection.execute(
            "INSERT INTO model_observations "
            "(run_id, activity_date, requests, prompt_tokens, output_tokens, "
            "cached_prompt_tokens, tool_calls, tool_error_requests) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                latest["date"],
                int(latest["count"]),
                int(latest["total_prompt_tokens"]),
                int(latest["total_completion_tokens"]),
                int(latest["total_native_tokens_cached"]),
                int(latest["total_tool_calls"]),
                int(latest["requests_with_tool_call_errors"]),
            ),
        )
    connection.close()
    return run_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("once", "loop"), nargs="?", default="once")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--permaslug", default=DEFAULT_PERMASLUG)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--effective-samples", type=int, default=3)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--max-runs", type=int)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.mode == "loop" and args.interval_seconds < 60:
        raise SystemExit("loop interval must be at least 60 seconds")
    completed = 0
    while True:
        try:
            run_id = collect_once(
                args.database,
                permaslug=args.permaslug,
                variant=args.variant,
                effective_samples=args.effective_samples,
            )
            completed += 1
            print(
                json.dumps(
                    {
                        "status": "collected",
                        "run_id": run_id,
                        "database": os.fspath(args.database),
                        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                ),
                flush=True,
            )
        except Exception as error:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_type": type(error).__name__,
                        "message": str(error),
                        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            if args.mode == "once":
                return 1
        if args.mode == "once" or (args.max_runs is not None and completed >= args.max_runs):
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
