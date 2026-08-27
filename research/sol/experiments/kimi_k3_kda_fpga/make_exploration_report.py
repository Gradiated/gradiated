#!/usr/bin/env python3
"""Build a compact HTML report for the second-pass exploration."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


COLORS = ["#2b6cb0", "#17835b", "#d97706", "#c2414b", "#7048a8"]


def scale(value: float, low: float, high: float, start: float, end: float) -> float:
    return start + (value - low) / max(high - low, 1e-9) * (end - start)


def line_chart(rows: list[dict], names: list[str]) -> str:
    width, height = 760, 360
    left, right, top, bottom = 72, 18, 34, 54
    xs = sorted({row["external_bandwidth_gbps"] for row in rows})
    ys = [row["latency_us"] for row in rows]
    lo, hi = min(ys) * 0.9, max(ys) * 1.05
    sx = lambda value: scale(value, min(xs), max(xs), left, width - right)
    sy = lambda value: scale(value, lo, hi, height - bottom, top)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Latency versus external bandwidth">']
    parts.append(f'<rect x="{left}" y="{top}" width="{width-left-right}" height="{height-top-bottom}" fill="white" stroke="#d9e0db"/>')
    for x in xs:
        px = sx(x)
        parts.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{top}" y2="{height-bottom}" stroke="#d9e0db"/>')
        parts.append(f'<text x="{px:.1f}" y="{height-bottom+20}" text-anchor="middle">{x:g}</text>')
    for i in range(5):
        y = lo + (hi - lo) * i / 4
        py = sy(y)
        parts.append(f'<line x1="{left}" x2="{width-right}" y1="{py:.1f}" y2="{py:.1f}" stroke="#d9e0db"/>')
        parts.append(f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end">{y:.1f}</text>')
    for index, name in enumerate(names):
        series = sorted((row for row in rows if row["name"] == name), key=lambda row: row["external_bandwidth_gbps"])
        points = " ".join(f"{sx(row['external_bandwidth_gbps']):.1f},{sy(row['latency_us']):.1f}" for row in series)
        color = COLORS[index % len(COLORS)]
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for row in series:
            parts.append(f'<circle cx="{sx(row["external_bandwidth_gbps"]):.1f}" cy="{sy(row["latency_us"]):.1f}" r="3" fill="{color}"/>')
    parts.append(f'<text x="{(left+width-right)/2:.1f}" y="{height-10}" text-anchor="middle">external bandwidth (Gb/s)</text>')
    parts.append(f'<text x="15" y="{(top+height-bottom)/2:.1f}" transform="rotate(-90 15 {(top+height-bottom)/2:.1f})" text-anchor="middle">latency (µs)</text>')
    parts.append("</svg>")
    return "".join(parts)


def winner_chart(best_counts: dict[str, int]) -> str:
    width, height = 760, 270
    left, right, top, bottom = 190, 25, 28, 42
    maximum = max(best_counts.values())
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Number of workloads won by each architecture">']
    for i, (name, count) in enumerate(sorted(best_counts.items(), key=lambda item: -item[1])):
        y = top + i * 42
        bar = (width - left - right) * count / maximum
        parts.append(f'<text x="{left-10}" y="{y+16}" text-anchor="end">{html.escape(name)}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="22" fill="{COLORS[i % len(COLORS)]}"/>')
        parts.append(f'<text x="{left+bar+8:.1f}" y="{y+16}">{count}</text>')
    parts.append(f'<text x="{(left+width-right)/2:.1f}" y="{height-8}" text-anchor="middle">workload cases won</text>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap(amdahl: list[dict]) -> str:
    fractions = sorted({row["kda_fraction_of_total_time"] for row in amdahl})
    speedups = sorted({row["kda_unit_speedup"] for row in amdahl})
    width, height = 760, 280
    left, top, cell_w, cell_h = 175, 45, 110, 40
    values = {(row["kda_fraction_of_total_time"], row["kda_unit_speedup"]): row["whole_model_speedup"] for row in amdahl}
    maximum = max(values.values())
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Whole-model Amdahl speedup heatmap">']
    for j, speedup in enumerate(speedups):
        x = left + j * cell_w
        parts.append(f'<text x="{x+cell_w/2}" y="28" text-anchor="middle">{speedup:g}× unit</text>')
    for i, fraction in enumerate(fractions):
        y = top + i * cell_h
        parts.append(f'<text x="{left-12}" y="{y+25}" text-anchor="end">{fraction:.0%} KDA time</text>')
        for j, speedup in enumerate(speedups):
            x = left + j * cell_w
            value = values[(fraction, speedup)]
            intensity = 0.12 + 0.68 * value / maximum
            parts.append(f'<rect x="{x}" y="{y}" width="{cell_w-4}" height="{cell_h-4}" fill="rgba(43,108,176,{intensity:.3f})"/>')
            parts.append(f'<text x="{x+(cell_w-4)/2}" y="{y+25}" text-anchor="middle">{value:.2f}×</text>')
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the exploration report")
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()
    data = json.loads((args.results_dir / "exploration.json").read_text())
    names = ["streaming", "weights_local", "state_local", "state_weights_local"]
    bandwidth = line_chart(data["bandwidth_rows"], names)
    winners = winner_chart(data["best_counts"])
    amdahl = heatmap(data["amdahl"])
    base_rows = [row for row in data["rankings"] if row["workload"] in {"kda_d64_u4_w0.5_a2.0", "kda_d128_u4_w0.5_a2.0", "kda_d256_u4_w0.5_a2.0"}]
    table = "".join(
        f"<tr><td>{r['head_dim']}</td><td>{html.escape(r['best_fpga'])}</td><td>{r['best_fpga_latency_us']:.2f} µs</td><td>{r['best_fpga_to_gpu_latency_ratio']:.2f}×</td><td>{r['feasible_fpga_count']}</td></tr>"
        for r in sorted(base_rows, key=lambda row: row["head_dim"])
    )
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>KDA second-pass exploration</title>
<style>body{{margin:0;background:#f7f7f2;color:#1b2421;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1000px;margin:0 auto;padding:30px}}h1{{margin:0 0 5px;font-size:30px}}h2{{margin:28px 0 8px;font-size:19px}}p{{color:#65736d}}.notice{{border-left:4px solid #d97706;background:#fff8e8;padding:10px 14px;margin:18px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:22px}}.plot{{min-width:0;background:#fff;border:1px solid #d9e0db;padding:8px}}svg{{display:block;width:100%;height:auto}}text{{fill:#1b2421;font-size:12px}}table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d9e0db}}th,td{{padding:8px 10px;text-align:left;border-bottom:1px solid #d9e0db}}th{{color:#65736d}}@media(max-width:760px){{main{{padding:18px}}.grid{{grid-template-columns:1fr}}h1{{font-size:24px}}}}</style></head><body><main>
<h1>KDA second-pass exploration</h1><p>Architecture screening across head size, state-update density, precision, and memory bandwidth.</p>
<div class="notice"><strong>Analytical evidence only.</strong> The GPU is a synthetic control. These results do not measure Vera Rubin, FPGA timing, model quality, or full-model throughput.</div>
<div class="grid"><section class="plot"><h2>Winner by workload</h2>{winners}</section><section class="plot"><h2>Latency versus external bandwidth</h2>{bandwidth}</section></div>
<h2>Whole-model improvement ceiling</h2><p>This heatmap shows the maximum whole-model speedup if a KDA unit improves by the stated factor and KDA accounts for the stated share of total time.</p><section class="plot">{amdahl}</section>
<h2>Representative head-size results</h2><table><thead><tr><th>Head dimension</th><th>Best FPGA candidate</th><th>Analytical latency</th><th>FPGA / GPU latency</th><th>Feasible FPGA designs</th></tr></thead><tbody>{table}</tbody></table>
<h2>What to take to FPGA</h2><p>Implement state-local and streamed-state variants first. Measure state SRAM bandwidth, feedback hazards, GEMV utilization, and the gate-convolution path. Keep the 128-wide streamed design as a negative control.</p>
</main></body></html>'''
    output = args.results_dir / "exploration_report.html"
    output.write_text(page)
    print(output)


if __name__ == "__main__":
    main()
