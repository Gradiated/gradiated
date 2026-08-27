#!/usr/bin/env python3
"""Compare KDA dataflows with measured and analytical evidence.

The specialized row-lane result comes from the KV260 run. The SIMT and tiled
rows are structural proxies. They use the same recurrence and formats, but
are not NVIDIA silicon measurements.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


def load_board(path: Path) -> dict:
    return json.loads(path.read_text())


def rows(head_dim: int, lanes: int, clock_mhz: float, board: dict) -> list[dict]:
    elements = head_dim * head_dim
    groups = head_dim // lanes
    specialized_cycles = 7 * elements // lanes

    # A generic vector kernel needs separate passes for decay, rank-1 update,
    # and output reduction. Each pass reads and writes state. This is a
    # deliberately conservative single-head, batch-1 proxy.
    simt_cycles = 3 * 4 * elements // lanes + 3 * head_dim

    # A 16x16 tiled engine amortises control over tiles, but batch-1 KDA still
    # performs elementwise state update and a reduction. The inner dimension
    # is time-multiplexed over 16 cycles per tile, with three tile phases.
    tile = 16
    tiles = (head_dim // tile) ** 2
    tensor_cycles = tiles * (3 * tile + 4) + head_dim
    measured_dsp_budget = board["resources"]["dsp"]
    tensor_resource_matched_cycles = tensor_cycles * ((256 + measured_dsp_budget - 1) // measured_dsp_budget)

    configs = [
        {
            "name": "specialized_kda_row_lanes",
            "evidence": "measured_kv260",
            "cycles": specialized_cycles,
            "dsp": board["resources"]["dsp"],
            "lut": board["resources"]["lut"],
            "bram": board["resources"]["ramb36"] + board["resources"]["ramb18"] / 2,
            "timing_mhz": board["clock_hz_target"] / 1_000_000,
            "state_bytes_per_token": elements * 3,
            "notes": "Persistent banked state; fused recurrence and readout.",
        },
        {
            "name": "generic_simt_vector_proxy",
            "evidence": "analytical_proxy",
            "cycles": simt_cycles,
            "dsp": lanes,
            "lut": 4200 + lanes * 180,
            "bram": 0,
            "timing_mhz": clock_mhz,
            "state_bytes_per_token": elements * 3 * 4,
            "notes": "Separate vector passes with global synchronization and state traffic.",
        },
        {
            "name": "tiled_tensor_core_proxy",
            "evidence": "analytical_proxy",
            "cycles": tensor_cycles,
            "dsp": tile * tile,
            "lut": 15000,
            "bram": 32,
            "timing_mhz": clock_mhz,
            "state_bytes_per_token": elements * 3,
            "notes": "16x16 tile schedule; better with batch or many independent heads.",
        },
        {
            "name": "tiled_tensor_resource_matched_proxy",
            "evidence": "analytical_proxy",
            "cycles": tensor_resource_matched_cycles,
            "dsp": board["resources"]["dsp"],
            "lut": 9000,
            "bram": 16,
            "timing_mhz": clock_mhz,
            "state_bytes_per_token": elements * 3,
            "notes": "Same tile schedule scaled to the measured 56-DSP budget.",
        },
    ]
    for row in configs:
        row["head_dim"] = head_dim
        row["lanes"] = lanes
        row["clock_mhz_target"] = clock_mhz
        row["latency_us_at_target"] = row["cycles"] / clock_mhz
        row["speedup_vs_specialized"] = specialized_cycles / row["cycles"]
        row["state_read_write_kb"] = row["state_bytes_per_token"] / 1024
        row["macs"] = elements * 4 + elements
        row["groups"] = groups
    return configs


def chart(data: list[dict]) -> str:
    colors = ["#1769aa", "#c05621", "#2f855a"]
    width, height = 780, 340
    left, right, top, bottom = 70, 25, 30, 55
    maximum = max(r["latency_us_at_target"] for r in data) * 1.15
    bar_w = (width - left - right) / len(data) * 0.62
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Latency comparison">']
    for i in range(5):
        value = maximum * i / 4
        y = height - bottom - (height - top - bottom) * value / maximum
        parts.append(f'<line x1="{left}" x2="{width-right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#d9e0db"/>')
        parts.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end">{value:.0f}</text>')
    for i, row in enumerate(data):
        x = left + (i + 0.19) * (width - left - right) / len(data)
        value = row["latency_us_at_target"]
        bar_h = (height - top - bottom) * value / maximum
        y = height - bottom - bar_h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{colors[i % len(colors)]}"/>')
        parts.append(f'<text x="{x+bar_w/2:.1f}" y="{y-8:.1f}" text-anchor="middle">{value:.1f} µs</text>')
        parts.append(f'<text x="{x+bar_w/2:.1f}" y="{height-bottom+20}" text-anchor="middle">{html.escape(row["name"].replace("_", " "))}</text>')
    parts.append(f'<text x="18" y="{(top+height-bottom)/2:.1f}" transform="rotate(-90 18 {(top+height-bottom)/2:.1f})" text-anchor="middle">cycles at 100 MHz (µs)</text>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).resolve().parents[1] / "results")
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--lanes", type=int, default=8)
    parser.add_argument("--clock-mhz", type=float, default=100.0)
    args = parser.parse_args()

    board = load_board(args.results_dir / "kv260" / "d128_l8" / "board_run.json")
    data = rows(args.head_dim, args.lanes, args.clock_mhz, board)
    output_json = args.results_dir / "dataflow_comparison.json"
    output_csv = args.results_dir / "dataflow_comparison.csv"
    output_html = args.results_dir / "dataflow_comparison.html"
    payload = {
        "experiment": {
            "name": "kda_dataflow_comparison",
            "evidence_class": "measured_kv260_plus_analytical_proxies",
            "hypothesis": "Persistent local state and fused scheduling reduce single-head batch-1 KDA latency versus generic multi-pass dataflows.",
            "scope": "One D=128 recurrent head, batch=1, identical fixed-point recurrence, q/k/v 8-bit and state 24-bit.",
            "quality_gate": "Specialized row-lane result must match the software oracle with zero mismatches; proxy rows must be labelled analytical.",
            "transfer_limit": "This does not measure B300, Vera Rubin, CUDA, or full Kimi K3 throughput.",
        },
        "rows": data,
    }
    output_json.write_text(json.dumps(payload, indent=2) + "\n")
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)

    table = "".join(
        f"<tr><td>{html.escape(r['name'])}</td><td>{r['evidence']}</td><td>{r['cycles']:,}</td><td>{r['latency_us_at_target']:.1f}</td><td>{r['dsp']}</td><td>{r['bram']}</td><td>{r['state_read_write_kb']:.1f}</td></tr>"
        for r in data
    )
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>KDA dataflow comparison</title><style>body{{margin:0;background:#f7f7f2;color:#1b2421;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1050px;margin:0 auto;padding:30px}}h1{{margin:0 0 6px;font-size:30px}}h2{{margin:28px 0 8px;font-size:19px}}p{{color:#65736d}}.notice{{border-left:4px solid #d97706;background:#fff8e8;padding:10px 14px;margin:18px 0}}.plot{{background:#fff;border:1px solid #d9e0db;padding:10px}}svg{{display:block;width:100%;height:auto}}text{{fill:#1b2421;font-size:12px}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d9e0db}}th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #d9e0db}}th{{color:#65736d}}code{{background:#edf2ef;padding:2px 4px}}</style></head><body><main><h1>KDA dataflow comparison</h1><p>D=128, batch=1, fixed-point recurrent head, target clock 100 MHz.</p><div class="notice"><strong>Evidence boundary.</strong> The specialized row-lane result is measured on the KV260. The SIMT and Tensor Core rows are analytical structural proxies. They do not predict NVIDIA silicon performance.</div><section class="plot">{chart(data)}</section><h2>Same work, different movement</h2><table><thead><tr><th>Dataflow</th><th>Evidence</th><th>Cycles</th><th>Latency</th><th>DSP proxy</th><th>BRAM proxy</th><th>State traffic</th></tr></thead><tbody>{table}</tbody></table><h2>Interpretation</h2><p>The specialized design keeps the recurrent state in banked local memory and fuses decay, rank-1 update, and readout. This reduces state passes and synchronization.</p><p>The generic SIMT proxy exposes the cost of separate kernels. It is a useful control for GPU-like scheduling, but its resource and cycle values are not a CUDA implementation.</p><p>The full Tensor Core proxy assumes 256 parallel multiply resources. It is an intentionally non-matched upper bound. The resource-matched row scales that schedule to the measured 56-DSP budget. A real 2D KDA tile may still win, but only after we prove its banking, dependencies, timing, and arithmetic correctness in RTL.</p><p>Next FPGA test: implement the SIMT proxy with the same AXI interface and exact oracle, then compare measured cycles, timing, and resource use against this table.</p></main></body></html>'''
    output_html.write_text(page)
    print(output_html)


if __name__ == "__main__":
    main()
