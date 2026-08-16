from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zlib
from pathlib import Path

from collector import collect_once


class CollectorTest(unittest.TestCase):
    def test_collect_once_preserves_discounted_prices_and_normalizes_share(self) -> None:
        effective = {
            "providerSummaries": [
                {
                    "providerName": "Alpha",
                    "providerSlug": "alpha",
                    "effectiveInputPrice": 0.25,
                    "effectiveOutputPrice": 3.0,
                    "cacheHitRate": 0.9,
                    "totalTokens": 75,
                },
                {
                    "providerName": "Beta",
                    "providerSlug": "beta",
                    "effectiveInputPrice": 0.5,
                    "effectiveOutputPrice": 4.0,
                    "cacheHitRate": 0.5,
                    "totalTokens": 25,
                },
                {
                    "providerName": "Alpha Fast",
                    "providerSlug": "alpha",
                    "effectiveInputPrice": 0.3,
                    "effectiveOutputPrice": 3.5,
                    "cacheHitRate": 0.8,
                    "totalTokens": 100,
                },
            ]
        }
        endpoints = [
            {
                "id": "endpoint-alpha",
                "provider_display_name": "Alpha",
                "provider_slug": "alpha/fp8",
                "quantization": "fp8",
                "context_length": 1_000_000,
                "max_completion_tokens": 100_000,
                "supported_parameters": ["tools", "structured_outputs"],
                "pricing": {
                    "prompt": "0.00000095",
                    "completion": "0.000003",
                    "input_cache_read": "0.00000018",
                    "discount": 0.32,
                },
                "status": 0,
                "status_heuristics_1d": {
                    "success": 990,
                    "derankableError": 10,
                    "rateLimited": 5,
                },
                "stats": {
                    "p50_throughput": 30,
                    "p50_latency": 2000,
                    "request_count": 500,
                    "window_minutes": 30,
                },
            }
        ]
        activity = {
            "analytics": [
                {
                    "date": "2026-07-16 00:00:00",
                    "count": 10,
                    "total_prompt_tokens": 1_000,
                    "total_completion_tokens": 100,
                    "total_native_tokens_cached": 800,
                    "total_tool_calls": 6,
                    "requests_with_tool_call_errors": 1,
                }
            ]
        }

        def fetcher(kind: str, sample_index: int | None) -> object:
            if kind == "effective_pricing":
                return effective
            if kind == "endpoints":
                return endpoints
            if kind == "activity":
                return activity
            return {"signal": kind}

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "history.sqlite3"
            run_id = collect_once(
                database,
                permaslug="z-ai/glm-5.2-20260616",
                variant="standard",
                effective_samples=2,
                captured_at="2026-07-16T12:00:00+00:00",
                fetcher=fetcher,
            )
            connection = sqlite3.connect(database)
            price = connection.execute(
                "SELECT input_price, cache_read_price, output_price, discount "
                "FROM endpoint_observations WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            self.assertEqual(price, (0.95, 0.18, 3.0, 0.32))
            shares = connection.execute(
                "SELECT sample_index, provider_slug, token_share "
                "FROM provider_share_observations WHERE run_id = ? "
                "ORDER BY sample_index, provider_slug",
                (run_id,),
            ).fetchall()
            self.assertEqual(
                shares,
                [
                    (0, "alpha", 0.375),
                    (0, "alpha", 0.5),
                    (0, "beta", 0.125),
                    (1, "alpha", 0.375),
                    (1, "alpha", 0.5),
                    (1, "beta", 0.125),
                ],
            )
            body = connection.execute(
                "SELECT body_zlib FROM raw_snapshots "
                "WHERE run_id = ? AND kind = 'endpoints'",
                (run_id,),
            ).fetchone()[0]
            self.assertEqual(json.loads(zlib.decompress(body)), endpoints)
            signal_count = connection.execute(
                "SELECT count(*) FROM raw_snapshots "
                "WHERE run_id = ? AND kind LIKE '%_3d'",
                (run_id,),
            ).fetchone()[0]
            self.assertEqual(signal_count, 6)
            model = connection.execute(
                "SELECT requests, prompt_tokens, output_tokens, cached_prompt_tokens, tool_calls "
                "FROM model_observations WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            self.assertEqual(model, (10, 1_000, 100, 800, 6))


if __name__ == "__main__":
    unittest.main()
