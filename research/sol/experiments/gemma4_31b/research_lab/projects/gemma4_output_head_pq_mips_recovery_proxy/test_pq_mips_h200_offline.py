#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

import torch

import pq_mips_h200_worker as worker


PROJECT = Path(__file__).resolve().parent


class PqMipsH200OfflineTest(unittest.TestCase):
    def test_frozen_contract_geometry(self) -> None:
        contract = json.loads((PROJECT / "EXPERIMENT_CONTRACT.json").read_text())
        self.assertEqual(contract["candidate"]["subspaces"], worker.SUBSPACES)
        self.assertEqual(contract["candidate"]["dimensions_per_subspace"], 2)
        self.assertEqual(contract["candidate"]["codebook_rows"], 256)
        self.assertEqual(contract["candidate"]["shortlist_sizes"], [256, 1024, 4096])
        self.assertEqual(contract["stock_control"]["weight_shape"], [262144, 5376])

    def test_vectorized_codes_equal_scalar_formula(self) -> None:
        rows, width = 257, 18
        base = torch.arange(rows * width, dtype=torch.float32).reshape(rows, width)
        weight = (torch.sin(base * 0.019) * 0.3).to(torch.bfloat16)
        variances, means = torch.var_mean(weight.float(), dim=0, correction=0)
        _, _, thresholds = worker.codebook_from_stats(means, variances, torch)
        observed = worker.encode_rows(weight, thresholds, torch, 31)
        scalar = []
        for row in weight:
            coordinates = [
                int(torch.searchsorted(thresholds[column], row[column].float()))
                for column in range(width)
            ]
            scalar.append(
                [
                    coordinates[column] + 16 * coordinates[column + 1]
                    for column in range(0, width, 2)
                ]
            )
        self.assertTrue(torch.equal(observed, torch.tensor(scalar, dtype=torch.uint8)))

    def test_asymmetric_scan_consumes_code_orientation(self) -> None:
        rows, width = 97, 14
        weight = (
            torch.cos(torch.arange(rows * width).reshape(rows, width) * 0.023) * 0.2
        ).to(torch.bfloat16)
        variances, means = torch.var_mean(weight.float(), dim=0, correction=0)
        _, scalar, thresholds = worker.codebook_from_stats(means, variances, torch)
        codebooks = worker.expanded_codebooks(scalar, torch)
        codes = worker.encode_rows(weight, thresholds, torch, 19)
        hidden = (
            torch.sin(torch.arange(5 * width).reshape(5, width) * 0.041) * 0.4
        ).to(torch.bfloat16)
        observed, _ = worker.asymmetric_scan(hidden, codebooks, codes, torch, 3, 23)
        subspaces = torch.arange(width // 2)[None, :]
        reconstructed = codebooks[subspaces, codes.long()].reshape(rows, width)
        reference = hidden.float() @ reconstructed.float().T
        self.assertTrue(torch.equal(observed, reference))

    def test_exact_union_rescore_matches_dense_argmax(self) -> None:
        rows, width = 113, 12
        hidden = (
            torch.sin(torch.arange(64 * width).reshape(64, width) * 0.011) * 0.2
        ).to(torch.bfloat16)
        weight = (
            torch.cos(torch.arange(rows * width).reshape(rows, width) * 0.017) * 0.3
        ).float()
        ids = torch.stack(
            [torch.arange(17, dtype=torch.int64).roll(index % 17) for index in range(64)]
        )
        rescored, unions = worker.exact_union_rescore(hidden, weight, ids, torch)
        dense_candidates = hidden.float() @ weight.T
        expected = ids.gather(
            1, dense_candidates.gather(1, ids).argmax(1, keepdim=True)
        ).squeeze(1)
        self.assertTrue(torch.equal(rescored, expected))
        self.assertEqual([int(value.numel()) for value in unions], [17, 17])

    def test_frozen_traffic_accounting(self) -> None:
        expected = {
            256: (8192, 917520384),
            1024: (32768, 1181958144),
            4096: (131072, 2239709184),
        }
        for shortlist, (union, total) in expected.items():
            self.assertEqual(worker.traffic(shortlist, union)["candidate_total_bytes"], total)


if __name__ == "__main__":
    unittest.main()
