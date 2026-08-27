#!/usr/bin/env python3
"""Build an analytical Kimi K3 decode workload and roofline report."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
from typing import Any


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def expected_unique_experts(experts: int, selected: int, batch: int) -> float:
    return experts * (1.0 - (1.0 - selected / experts) ** batch)


def component_model(spec: dict[str, Any], context: int, batch: int) -> list[dict[str, Any]]:
    model = spec["model"]
    formats = spec["formats"]
    h = model["hidden_size"]
    heads = model["attention_heads"]
    d = model["attention_head_dim"]
    rope = model["qk_rope_head_dim"]
    projection = heads * d
    sparse_layers = model["total_layers"] - model["dense_layers"]
    latent = model["latent_moe_dimension"]
    expert_intermediate = model["expert_intermediate_size"]
    selected = model["selected_experts"]
    experts = model["experts"]
    shared = model["shared_experts"]
    routed_bytes = formats["routed_weight_bytes"]
    full_bytes = formats["unquantized_weight_bytes"]
    state_bytes = formats["state_bytes"]
    cache_bytes = formats["mla_cache_bytes"]
    unique = expected_unique_experts(experts, selected, batch)

    rows: list[dict[str, Any]] = []

    def add(
        name: str,
        block: str,
        layers: int,
        macs_per_layer: float,
        common_parameters_per_layer: float,
        bytes_per_parameter: float,
        note: str,
        routed_parameters_per_expert: float = 0.0,
    ) -> None:
        common_weight_bytes = layers * common_parameters_per_layer * bytes_per_parameter / batch
        routed_weight_bytes = layers * routed_parameters_per_expert * unique * bytes_per_parameter / batch
        rows.append(
            {
                "name": name,
                "block": block,
                "layers": layers,
                "macs_per_token": layers * macs_per_layer,
                "weight_bytes_per_token": common_weight_bytes + routed_weight_bytes,
                "note": note,
            }
        )

    add(
        "router",
        "moe",
        sparse_layers,
        h * experts,
        h * experts,
        full_bytes,
        "One score for every routed expert.",
    )
    add(
        "latent_moe_projection",
        "moe",
        sparse_layers,
        2 * h * latent,
        2 * h * latent,
        routed_bytes,
        "Shared down and up projections around the routed experts.",
    )
    add(
        "routed_experts",
        "moe",
        sparse_layers,
        selected * 3 * latent * expert_intermediate,
        0,
        routed_bytes,
        "Three matrices for each selected routed expert.",
        routed_parameters_per_expert=3 * latent * expert_intermediate,
    )
    add(
        "shared_experts",
        "moe",
        sparse_layers,
        3 * h * expert_intermediate * shared,
        3 * h * expert_intermediate * shared,
        full_bytes,
        "Two shared experts represented by one wider MLP.",
    )

    kda_projection_macs = (
        3 * h * projection
        + h * d
        + d * projection
        + h * heads
        + h * projection
        + projection * h
    )
    kda_projection_parameters = kda_projection_macs
    add(
        "kda_projections_and_gates",
        "kda",
        model["kda_layers"],
        kda_projection_macs,
        kda_projection_parameters,
        full_bytes,
        "Q/K/V, gate, beta, and output projections.",
    )
    add(
        "kda_recurrence",
        "kda",
        model["kda_layers"],
        5 * heads * d * d,
        0,
        0,
        "Five MAC-equivalent state operations per state value.",
    )
    add(
        "kda_short_convolution",
        "kda",
        model["kda_layers"],
        3 * projection * model["short_conv_kernel_size"],
        3 * projection * model["short_conv_kernel_size"],
        full_bytes,
        "Depthwise short convolution for Q, K, and V.",
    )

    q_head = d + rope
    q_rank = model["q_lora_rank"]
    kv_rank = model["kv_lora_rank"]
    mla_fixed = (
        h * q_rank
        + q_rank * heads * q_head
        + h * (kv_rank + rope)
        + kv_rank * heads * (d + d)
        + h * projection
        + projection * h
    )
    add(
        "mla_projections_and_gate",
        "mla",
        model["mla_layers"],
        mla_fixed,
        mla_fixed,
        full_bytes,
        "Low-rank Q/KV projections, output gate, and output projection.",
    )
    add(
        "mla_context_attention",
        "mla",
        model["mla_layers"],
        heads * context * (q_head + d),
        0,
        0,
        "Logical decode attention work. Optimised kernels may transform it.",
    )

    add(
        "dense_layer_mlp",
        "dense",
        model["dense_layers"],
        3 * h * model["dense_intermediate_size"],
        3 * h * model["dense_intermediate_size"],
        full_bytes,
        "The first dense channel-mixing layer.",
    )
    add(
        "language_model_head",
        "output",
        1,
        h * model["vocabulary_size"],
        h * model["vocabulary_size"],
        full_bytes,
        "Vocabulary logits for one generated token.",
    )

    kda_state_values = model["kda_layers"] * heads * d * d
    kda_state_traffic = 2 * kda_state_values * state_bytes
    mla_cache_read = model["mla_layers"] * context * (kv_rank + rope) * cache_bytes
    mla_cache_write = model["mla_layers"] * (kv_rank + rope) * cache_bytes
    for row in rows:
        row["context"] = context
        row["batch"] = batch
        row["expected_unique_experts_per_layer"] = unique
        row["kda_state_bytes_per_sequence"] = kda_state_values * state_bytes
        row["kda_state_traffic_bytes_per_token"] = kda_state_traffic
        row["mla_cache_bytes_per_sequence"] = model["mla_layers"] * context * (kv_rank + rope) * cache_bytes
        row["mla_cache_traffic_bytes_per_token"] = mla_cache_read + mla_cache_write
    return rows


def roofline_rows(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    roofline = spec["roofline"]
    component_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for context in spec["workloads"]["context_lengths"]:
        for batch in spec["workloads"]["batch_sizes"]:
            components = component_model(spec, context, batch)
            component_rows.extend(components)
            macs = sum(row["macs_per_token"] for row in components)
            weights = sum(row["weight_bytes_per_token"] for row in components)
            kda_state = components[0]["kda_state_traffic_bytes_per_token"]
            mla_cache = components[0]["mla_cache_traffic_bytes_per_token"]
            kda_capacity = components[0]["kda_state_bytes_per_sequence"] * batch
            mla_capacity = components[0]["mla_cache_bytes_per_sequence"] * batch
            for scenario in ("external_state", "local_kda_state"):
                external_bytes = weights + mla_cache
                local_bytes = 0.0
                if scenario == "external_state":
                    external_bytes += kda_state
                else:
                    local_bytes = kda_state
                compute_us = macs / roofline["compute_peak_macs_per_second"] * 1e6
                external_us = external_bytes / roofline["external_bandwidth_bytes_per_second"] * 1e6
                local_us = local_bytes / roofline["local_bandwidth_bytes_per_second"] * 1e6
                lower_bound = max(compute_us, external_us, local_us)
                bottleneck = max(
                    ((compute_us, "compute"), (external_us, "external_memory"), (local_us, "local_memory")),
                    key=lambda item: item[0],
                )[1]
                summaries.append(
                    {
                        "context": context,
                        "batch": batch,
                        "scenario": scenario,
                        "evidence": "analytical_lower_bound",
                        "macs_per_token": macs,
                        "weight_gb_per_token": weights / 1e9,
                        "kda_state_traffic_gb_per_token": kda_state / 1e9,
                        "mla_cache_traffic_gb_per_token": mla_cache / 1e9,
                        "external_gb_per_token": external_bytes / 1e9,
                        "local_gb_per_token": local_bytes / 1e9,
                        "kda_state_capacity_gb_for_batch": kda_capacity / 1e9,
                        "mla_cache_capacity_gb_for_batch": mla_capacity / 1e9,
                        "compute_us_lower_bound": compute_us,
                        "external_memory_us_lower_bound": external_us,
                        "local_memory_us_lower_bound": local_us,
                        "latency_us_lower_bound": lower_bound,
                        "bottleneck": bottleneck,
                        "arithmetic_intensity_mac_per_external_byte": macs / external_bytes,
                    }
                )
    return summaries, component_rows


def format_number(value: float) -> str:
    if value >= 1e12:
        return f"{value / 1e12:.2f}T"
    if value >= 1e9:
        return f"{value / 1e9:.2f}B"
    if value >= 1e6:
        return f"{value / 1e6:.2f}M"
    return f"{value:.0f}"


def bar_chart(rows: list[dict[str, Any]], context: int, batch: int) -> str:
    selected = [row for row in rows if row["context"] == context and row["batch"] == batch]
    by_block: dict[str, float] = {}
    for row in selected:
        by_block[row["block"]] = by_block.get(row["block"], 0.0) + row["macs_per_token"]
    colors = {"moe": "#1769aa", "kda": "#2f855a", "mla": "#d97706", "dense": "#805ad5", "output": "#c2414b"}
    width, height = 820, 235
    left, right, top, bottom = 85, 20, 22, 45
    maximum = max(by_block.values()) * 1.15
    slot = (width - left - right) / len(by_block)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Operation count by block">']
    for index, (name, value) in enumerate(by_block.items()):
        x = left + index * slot + slot * 0.18
        bar_width = slot * 0.64
        bar_height = (height - top - bottom) * value / maximum
        y = height - bottom - bar_height
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{colors[name]}"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 7:.1f}" text-anchor="middle">{format_number(value)}</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{height - bottom + 20}" text-anchor="middle">{html.escape(name.upper())}</text>')
    parts.append('<text x="18" y="110" transform="rotate(-90 18 110)" text-anchor="middle">MACs per token</text>')
    parts.append("</svg>")
    return "".join(parts)


def make_html(spec: dict[str, Any], summaries: list[dict[str, Any]], components: list[dict[str, Any]]) -> str:
    model = spec["model"]
    base = next(row for row in summaries if row["context"] == 8192 and row["batch"] == 1 and row["scenario"] == "external_state")
    summary_table = "".join(
        "<tr>"
        f"<td>{row['context']:,}</td><td>{row['batch']}</td><td>{html.escape(row['scenario'])}</td>"
        f"<td>{row['macs_per_token'] / 1e9:.1f}B</td><td>{row['weight_gb_per_token']:.1f} GB</td>"
        f"<td>{row['kda_state_traffic_gb_per_token']:.2f} GB</td><td>{row['mla_cache_traffic_gb_per_token']:.2f} GB</td>"
        f"<td>{row['latency_us_lower_bound']:.1f} µs</td><td>{html.escape(row['bottleneck'])}</td></tr>"
        for row in summaries
    )
    component_table = "".join(
        "<tr>"
        f"<td>{html.escape(row['name'])}</td><td>{html.escape(row['block'])}</td>"
        f"<td>{row['macs_per_token'] / 1e9:.2f}B</td><td>{row['weight_bytes_per_token'] / 1e9:.2f} GB</td>"
        f"<td>{html.escape(row['note'])}</td></tr>"
        for row in components
        if row["context"] == 8192 and row["batch"] == 1
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kimi K3 workload model</title><style>body{{margin:0;background:#f6f7f3;color:#18211e;font:15px/1.48 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1120px;margin:0 auto;padding:30px}}h1{{margin:0 0 5px;font-size:30px}}h2{{margin:30px 0 8px;font-size:20px}}p{{color:#596a63}}.notice{{border-left:4px solid #d97706;background:#fff8e8;padding:12px 15px;margin:18px 0}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card,.plot{{background:white;border:1px solid #d8e0dc;padding:14px}}.value{{font-size:24px;font-weight:650}}table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d8e0dc;font-size:13px}}th,td{{padding:8px 9px;text-align:left;border-bottom:1px solid #e2e8e5}}th{{color:#596a63}}svg{{display:block;width:100%;height:auto}}text{{fill:#18211e;font-size:12px}}@media(max-width:800px){{main{{padding:18px}}.cards{{grid-template-columns:1fr 1fr}}.scroll{{overflow-x:auto}}}}</style></head><body><main><h1>Kimi K3 decode workload model</h1><p>First analytical pass for the model-specific inference-chip microarchitecture.</p><div class="notice"><strong>Evidence boundary.</strong> Model geometry is vendor-reported. Operation counts and traffic are analytical. Roofline latency is a synthetic ideal lower bound. It is not a GPU or ASIC measurement.</div><section class="cards"><div class="card"><div class="value">{model['total_layers']}</div><div>model layers</div></div><div class="card"><div class="value">{model['experts']}</div><div>routed experts</div></div><div class="card"><div class="value">{model['selected_experts']}</div><div>selected per token</div></div><div class="card"><div class="value">{base['macs_per_token']/1e9:.1f}B</div><div>MACs/token at 8K context</div></div></section><h2>Where the arithmetic is</h2><p>This chart uses batch 1 and an 8,192-token context. It includes the full 93-layer text model and the vocabulary head.</p><section class="plot">{bar_chart(components, 8192, 1)}</section><h2>Component breakdown</h2><div class="scroll"><table><thead><tr><th>Component</th><th>Block</th><th>MACs/token</th><th>Weight bytes/token</th><th>Meaning</th></tr></thead><tbody>{component_table}</tbody></table></div><h2>Context, batch, and state locality</h2><p>The local-state case moves KDA state traffic to a synthetic high-bandwidth local store. Its required capacity is still reported in the JSON output. Common weights are amortised over the batch. Routed-expert reuse uses independent uniform routing until a real trace replaces it.</p><div class="scroll"><table><thead><tr><th>Context</th><th>Batch</th><th>Scenario</th><th>MACs/token</th><th>Weights</th><th>KDA traffic</th><th>MLA traffic</th><th>Ideal bound</th><th>Bottleneck</th></tr></thead><tbody>{summary_table}</tbody></table></div><h2>What this tells us next</h2><p>Use this model to decide what to measure. The first required calibration is an expert-routing and memory trace from a real Kimi K3 decode run. The next hardware controls are streamed-state KDA, local-state KDA, and a resource-matched tiled engine.</p></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("workload.json"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()
    spec = load_spec(args.spec)
    summaries, components = roofline_rows(spec)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": json.loads(Path(__file__).with_name("experiment.json").read_text()),
        "input": spec,
        "summary_rows": summaries,
        "component_rows": components,
    }
    (args.output_dir / "workload_analysis.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (args.output_dir / "roofline_rows.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    (args.output_dir / "report.html").write_text(make_html(spec, summaries, components))
    print(args.output_dir / "report.html")


if __name__ == "__main__":
    main()
