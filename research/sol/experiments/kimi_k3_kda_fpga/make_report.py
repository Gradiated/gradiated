#!/usr/bin/env python3
"""Build a small browser report from the KDA sweep outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


PLOT_FIELDS = (
    "name",
    "kind",
    "latency_us",
    "energy_proxy_uj",
    "logic_cells",
    "dsp_slices",
    "fused",
    "local_state",
    "weights_local",
    "double_buffered",
    "external_bytes",
    "local_bytes",
    "compute_us",
    "vector_us",
    "external_memory_us",
    "local_memory_us",
    "launch_us",
    "overlap_mode",
    "sram_kb",
    "clock_mhz",
    "external_bandwidth_gbps",
    "local_bandwidth_gbps",
    "fits_kv260",
)


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key in PLOT_FIELDS:
            if key not in row:
                continue
            if key in {"name", "kind", "overlap_mode"}:
                continue
            if key in {"fused", "local_state", "weights_local", "double_buffered", "fits_kv260"}:
                row[key] = row[key].lower() == "true"
            else:
                row[key] = float(row[key])
    return rows


def compact(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in PLOT_FIELDS if key in row}


def build_data(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = [row for row in rows if row["kind"] == "fpga" and row["fits_kv260"]]
    frontier_names = {row["name"] for row in summary["pareto_frontier"]}
    stride = max(1, len(feasible) // 900)
    sampled = feasible[::stride]
    sampled.extend(row for row in feasible if row["name"] in frontier_names)
    sampled_by_name = {row["name"]: row for row in sampled}
    selected = [*summary["controls"]]
    for row in rows:
        if row["name"] in {
            summary["best_latency"]["name"],
            summary["best_energy"]["name"],
            summary["best_balanced"]["name"],
        }:
            selected.append(row)
    local_candidates = [row for row in feasible if row["local_state"] and row["weights_local"]]
    if local_candidates:
        selected.append(min(local_candidates, key=lambda row: row["latency_us"]))
    selected_by_name = {row["name"]: row for row in selected}
    top = sorted(feasible, key=lambda row: row["latency_us"])[:8]
    return {
        "experiment": summary["experiment"],
        "workload": summary["workload"],
        "counts": summary["workload_counts"],
        "all_row_count": summary["all_row_count"],
        "candidate_count": summary["candidate_count"],
        "limits": summary["kv260_limits"],
        "plot_rows": [compact(row) for row in sampled_by_name.values()],
        "frontier": [compact(row) for row in summary["pareto_frontier"]],
        "selected": [compact(row) for row in selected_by_name.values()],
        "top": [compact(row) for row in top],
    }


HTML = r'''<div id="report">
<style>
#report { --bg:#f7f7f2; --surface:#ffffff; --ink:#1b2421; --muted:#65736d; --line:#d9e0db; --blue:#2b6cb0; --orange:#d97706; --green:#17835b; --red:#c2414b; max-width:1100px; margin:0 auto; padding:28px; color:var(--ink); background:var(--bg); font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
#report h1 { margin:0 0 5px; font-size:30px; letter-spacing:-.03em; }
#report h2 { margin:28px 0 10px; font-size:20px; }
#report h3 { margin:0 0 8px; font-size:16px; }
#report .subtitle { color:var(--muted); margin-bottom:18px; }
#report .notice { border-left:4px solid var(--orange); background:#fff8e8; padding:10px 14px; margin:0 0 24px; }
#report .charts { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:24px; }
#report .chart-wrap { min-width:0; }
#report svg { display:block; width:100%; height:auto; overflow:visible; }
#report .frame { fill:var(--surface); stroke:var(--line); }
#report .gridline { stroke:var(--line); stroke-width:1; }
#report .axis, #report .axis-title, #report .tick-label, #report .chart-title { fill:var(--ink); font-size:12px; }
#report .chart-title { font-size:14px; font-weight:600; }
#report .dot { stroke:var(--surface); stroke-width:1; cursor:pointer; }
#report .dot:hover { stroke:var(--ink); stroke-width:2; }
#report .legend { color:var(--muted); font-size:12px; margin:5px 0 0 68px; }
#report .legend span { margin-right:14px; white-space:nowrap; }
#report .swatch { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:4px; }
#report .detail { color:var(--muted); min-height:24px; margin:10px 0 0; }
#report .table-wrap { overflow-x:auto; background:var(--surface); border:1px solid var(--line); }
#report table { width:100%; border-collapse:collapse; font-size:13px; }
#report th, #report td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
#report th { color:var(--muted); font-weight:600; }
#report tr:last-child td { border-bottom:0; }
#report code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
#report .tooltip { position:fixed; display:none; pointer-events:none; z-index:5; background:var(--ink); color:#fff; padding:7px 9px; border-radius:4px; font-size:12px; max-width:290px; }
@media (max-width:760px) { #report { padding:18px; } #report h1 { font-size:24px; } #report .charts { grid-template-columns:1fr; gap:14px; } }
</style>
<h1>KDA architecture sweep</h1>
<div class="subtitle">Kimi K3-inspired decode-head screening · one 128×128 head</div>
<div class="notice"><strong>Evidence class: analytical.</strong> These values screen dataflow choices before RTL and KV260 measurement. They do not predict a B300, Vera Rubin, advanced-node ASIC, or product result.</div>
<div class="charts">
  <div class="chart-wrap"><svg id="latency-energy" role="img" aria-label="Latency versus energy scatter plot"></svg><div class="legend"><span><i class="swatch" style="background:var(--blue)"></i>sampled feasible designs</span><span><i class="swatch" style="background:var(--red)"></i>Pareto frontier</span></div></div>
  <div class="chart-wrap"><svg id="latency-dsp" role="img" aria-label="Latency versus DSP usage scatter plot"></svg></div>
  <div class="chart-wrap"><svg id="latency-logic" role="img" aria-label="Latency versus logic cells scatter plot"></svg></div>
  <div class="chart-wrap"><svg id="paths" role="img" aria-label="Compute and memory path comparison"></svg></div>
</div>
<div id="detail" class="detail" aria-live="polite">Select a point to inspect its assumptions.</div>
<h2>Fastest feasible FPGA candidates</h2>
<div class="table-wrap"><table><thead><tr><th>Design</th><th>Latency</th><th>Energy proxy</th><th>DSP</th><th>Logic</th><th>Fusion</th><th>State local</th><th>Weights local</th></tr></thead><tbody id="top-table"></tbody></table></div>
<div class="tooltip" role="tooltip" id="tooltip"></div>
<script id="report-data" type="application/json">__DATA__</script>
<script>
(() => {
  const data = JSON.parse(document.getElementById('report-data').textContent);
  const root = document.getElementById('report');
  const tooltip = document.getElementById('tooltip');
  const frontier = new Set(data.frontier.map(d => d.name));
  const colors = { sample: 'var(--blue)', frontier: 'var(--red)', compute: 'var(--green)', memory: 'var(--orange)' };
  const fmt = (value, digits=2) => Number(value).toLocaleString(undefined, {maximumFractionDigits:digits});
  const short = (name) => name.replace(/^fpga_/, '').replaceAll('_', ' ');
  const show = (row) => {
    document.getElementById('detail').textContent = `${short(row.name)} · ${fmt(row.latency_us)} µs · ${fmt(row.energy_proxy_uj)} µJ · ${fmt(row.external_bytes,0)} external bytes · ${row.overlap_mode}`;
  };
  const tip = (event, row) => {
    tooltip.style.display = 'block';
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY + 12}px`;
    tooltip.textContent = `${short(row.name)} · ${fmt(row.latency_us)} µs · ${fmt(row.energy_proxy_uj)} µJ`;
  };
  const hideTip = () => { tooltip.style.display = 'none'; };
  const log10 = (v) => Math.log(v) / Math.LN10;
  const niceTicks = (lo, hi) => {
    const start = Math.ceil(log10(lo));
    const end = Math.floor(log10(hi));
    const values = [];
    for (let power=start; power<=end; power++) values.push(10 ** power);
    if (values.length < 3) return [lo, (lo * hi) ** .5, hi];
    return values.slice(0, 5);
  };
  const drawScatter = (id, xKey, yKey, title, xLabel, yLabel) => {
    const svg = document.getElementById(id);
    const width = Math.max(320, svg.parentElement.getBoundingClientRect().width);
    const height = 350, m = {top:34, right:18, bottom:48, left:68};
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.innerHTML = '';
    const plotRows = data.plot_rows;
    const xs = plotRows.map(d => d[xKey]).filter(v => v > 0);
    const ys = plotRows.map(d => d[yKey]).filter(v => v > 0);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const px = (v) => m.left + (log10(v)-log10(x0*.85)) / (log10(x1*1.15)-log10(x0*.85)) * (width-m.left-m.right);
    const py = (v) => height-m.bottom - (log10(v)-log10(y0*.85)) / (log10(y1*1.15)-log10(y0*.85)) * (height-m.top-m.bottom);
    const el = (tag, attrs, text='') => { const node=document.createElementNS('http://www.w3.org/2000/svg',tag); Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v)); if(text) node.textContent=text; svg.appendChild(node); return node; };
    el('rect', {x:m.left,y:m.top,width:width-m.left-m.right,height:height-m.top-m.bottom,class:'frame','data-chart-frame':'true'});
    el('text', {x:m.left,y:18,class:'chart-title'}, title);
    niceTicks(x0*.85,x1*1.15).forEach(v => { const x=px(v); el('line',{x1:x,x2:x,y1:m.top,y2:height-m.bottom,class:'gridline'}); el('text',{x:x,y:height-m.bottom+18,'text-anchor':'middle',class:'tick-label'},fmt(v,1)); });
    niceTicks(y0*.85,y1*1.15).forEach(v => { const y=py(v); el('line',{x1:m.left,x2:width-m.right,y1:y,y2:y,class:'gridline'}); el('text',{x:m.left-8,y:y+4,'text-anchor':'end',class:'tick-label'},fmt(v,1)); });
    el('text',{x:(m.left+width-m.right)/2,y:height-8,'text-anchor':'middle',class:'axis-title','data-axis':'x'},xLabel);
    el('text',{x:15,y:(m.top+height-m.bottom)/2,transform:`rotate(-90 15 ${(m.top+height-m.bottom)/2})`,'text-anchor':'middle',class:'axis-title','data-axis':'y'},yLabel);
    plotRows.forEach(row => { const dot=el('circle',{cx:px(row[xKey]),cy:py(row[yKey]),r:frontier.has(row.name)?4:2.5,class:'dot',fill:frontier.has(row.name)?colors.frontier:colors.sample,'data-chart-hit':'true'}); dot.addEventListener('click',()=>show(row)); dot.addEventListener('mousemove',(e)=>tip(e,row)); dot.addEventListener('mouseleave',hideTip); });
  };
  const drawPaths = () => {
    const svg = document.getElementById('paths');
    const width = Math.max(320, svg.parentElement.getBoundingClientRect().width), height=350, m={top:34,right:18,bottom:48,left:112};
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`); svg.innerHTML='';
    const rows = data.selected.slice(0,5);
    const vals = rows.flatMap(d => [d.compute_us+d.vector_us,d.external_memory_us+d.local_memory_us,d.latency_us]);
    const max = Math.max(...vals)*1.1, sx=(v)=>m.left+v/max*(width-m.left-m.right);
    const el=(tag,attrs,text='')=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text)n.textContent=text;svg.appendChild(n);return n;};
    el('rect',{x:m.left,y:m.top,width:width-m.left-m.right,height:height-m.top-m.bottom,class:'frame','data-chart-frame':'true'});
    el('text',{x:m.left,y:18,class:'chart-title'},'Critical paths for selected designs');
    [0,max/2,max].forEach(v=>{const x=sx(v);el('line',{x1:x,x2:x,y1:m.top,y2:height-m.bottom,class:'gridline'});el('text',{x:x,y:height-m.bottom+18,'text-anchor':'middle',class:'tick-label'},fmt(v,1));});
    el('text',{x:(m.left+width-m.right)/2,y:height-8,'text-anchor':'middle',class:'axis-title','data-axis':'x'},'time (µs)');
    rows.forEach((row,i)=>{const y=m.top+42+i*48; const compute=row.compute_us+row.vector_us, memory=row.external_memory_us+row.local_memory_us; el('text',{x:m.left-8,y:y+4,'text-anchor':'end',class:'tick-label'},row.kind==='gpu'?'GPU control':short(row.name).slice(0,16)); el('rect',{x:m.left,y:y-12,width:sx(compute)-m.left,height:12,fill:colors.compute}); el('rect',{x:m.left,y:y+2,width:sx(memory)-m.left,height:12,fill:colors.memory}); el('line',{x1:sx(row.latency_us),x2:sx(row.latency_us),y1:y-16,y2:y+18,stroke:colors.frontier,'stroke-width':2});});
    el('text',{x:m.left,y:height-25,class:'tick-label'},'green compute path · orange memory path · red latency');
  };
  const renderTable = () => { const body=document.getElementById('top-table'); body.innerHTML=''; data.top.forEach(row=>{const tr=document.createElement('tr'); const cells=[short(row.name),`${fmt(row.latency_us)} µs`,`${fmt(row.energy_proxy_uj)} µJ`,fmt(row.dsp_slices,0),fmt(row.logic_cells,0),row.fused?'yes':'no',row.local_state?'yes':'no',row.weights_local?'yes':'no']; cells.forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.appendChild(td);});body.appendChild(tr);});};
  const drawAll = () => { drawScatter('latency-energy','latency_us','energy_proxy_uj','Latency versus energy','latency (µs, log scale)','energy proxy (µJ, log scale)'); drawScatter('latency-dsp','dsp_slices','latency_us','Latency versus DSP use','DSP slices','latency (µs, log scale)'); drawScatter('latency-logic','logic_cells','latency_us','Latency versus logic use','logic cells','latency (µs, log scale)'); drawPaths(); renderTable(); };
  drawAll();
  if (window.ResizeObserver) new ResizeObserver(drawAll).observe(root);
})();
</script>
</div>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the KDA HTML report")
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).parent / "results")
    args = parser.parse_args()
    summary_path = args.results_dir / "summary.json"
    rows_path = args.results_dir / "sweep.csv"
    summary = json.loads(summary_path.read_text())
    data = build_data(summary, read_rows(rows_path))
    output = args.results_dir / "report.html"
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>KDA architecture sweep</title></head><body>"
        + HTML.replace("__DATA__", json.dumps(data, separators=(",", ":")))
        + "</body></html>"
    )
    output.write_text(page)
    print(output)


if __name__ == "__main__":
    main()
