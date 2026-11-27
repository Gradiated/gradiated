"""Draw the decide-1 post charts from data.json as standalone SVGs (no dependencies).

Usage: python3 make_charts.py   (reads data.json next to this file, writes loss.svg, dev.svg, blend.svg, panel.svg)
Colours: the dataviz reference palette, validated for these pairs (blue #2a78d6 / orange #eb6834, light and dark).
Each mark carries a <title>, so browsers show the value on hover; the numbers are also in facts.md.
"""
import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.load(open(HERE / "data.json"))

STYLE = """<style>
svg{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#e6e5e1;--s1:#2a78d6;--s2:#eb6834;
--pos:#2a78d6;--neg:#e34948;--ref:#8a8984;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
@media (prefers-color-scheme: dark){svg{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e88;--grid:#33332f;
--s1:#3987e5;--s2:#d95926;--pos:#3987e5;--neg:#e66767;--ref:#8f8e88}}
.bg{fill:var(--surface)}.t{fill:var(--ink);font-size:15px;font-weight:600}.st{fill:var(--ink2);font-size:12px}
.ax{fill:var(--ink2);font-size:11px}.lab{fill:var(--ink);font-size:12px}.mut{fill:var(--muted);font-size:11px}
.grid{stroke:var(--grid);stroke-width:1}.base{stroke:var(--ink2);stroke-width:1}
</style>"""


def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{escape(title)}">{STYLE}<rect class="bg" width="{w}" height="{h}"/>{body}</svg>\n')


def scale(d0, d1, r0, r1):
    return lambda v: r0 + (v - d0) / (d1 - d0) * (r1 - r0)


def ema(xs, a=0.25):
    out, m = [], None
    for x in xs:
        m = x if m is None else a * x + (1 - a) * m
        out.append(m)
    return out


def path(pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def loss_chart():
    k1, k2 = D["runs"]["gd-kl1"], D["runs"]["gd-kl2"]
    t1, t2 = k1["real_tokens_per_step"], k2["real_tokens_per_step"]
    off = k1["steps"] * t1
    s1 = [(r["step"] * t1 / 1e6, r["ce"]) for r in k1["train"]]
    s2 = [((off + r["step"] * t2) / 1e6, r["ce"]) for r in k2["train"]]
    W, H, L, R, T, B = 760, 380, 58, 24, 70, 50
    xmax = (off + k2["steps"] * t2) / 1e6
    x = scale(0, xmax, L, W - R)
    y = scale(0.2, 0.7, H - B, T)
    b = [f'<text class="t" x="{L}" y="26">Training loss over {xmax:,.0f}M tokens</text>',
         f'<text class="st" x="{L}" y="46">Soft cross-entropy on the answer distribution, mean of each 10-step window; '
         f'line = moving average.</text>',
         f'<text class="st" x="{L}" y="61">gd-kl2 trains on a different mix, so its loss level is not comparable with gd-kl1\'s.</text>']
    for v in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        b.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text class="ax" x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{v:.1f}</text>')
    for v in range(0, int(xmax) + 1, 100):
        b.append(f'<text class="ax" x="{x(v):.1f}" y="{H - B + 18}" text-anchor="middle">{v}M</text>')
    b.append(f'<line class="base" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>')
    b.append(f'<text class="ax" x="{(L + W - R) / 2}" y="{H - 10}" text-anchor="middle">training tokens seen (real, unpadded)</text>')
    b.append(f'<line stroke="var(--muted)" stroke-dasharray="3 3" x1="{x(off / 1e6):.1f}" x2="{x(off / 1e6):.1f}" '
             f'y1="{T}" y2="{H - B}"/>')
    for pts, var, name, run in ((s1, "--s2", "gd-kl1 (from KnowLine)", k1), (s2, "--s1", "gd-kl2 (from gd-kl1)", k2)):
        P = [(x(a), y(c)) for a, c in pts]
        b.append(f'<path d="{path(P)}" fill="none" stroke="var({var})" stroke-opacity="0.28" stroke-width="1"/>')
        sm = ema([c for _, c in pts])
        b.append(f'<path d="{path([(x(a), y(c)) for (a, _), c in zip(pts, sm)])}" fill="none" stroke="var({var})" '
                 f'stroke-width="2" stroke-linejoin="round"/>')
        for (a, c) in pts:
            b.append(f'<circle cx="{x(a):.1f}" cy="{y(c):.1f}" r="5" fill="transparent"><title>{name}: '
                     f'{a:,.0f}M tokens, CE {c}</title></circle>')
        lx, ly = P[0][0] + 6, y(sm[min(8, len(sm) - 1)]) - 26
        b.append(f'<line x1="{lx - 4}" x2="{lx + 10}" y1="{ly - 4}" y2="{ly - 4}" stroke="var({var})" stroke-width="2"/>'
                 f'<text class="lab" x="{lx + 14}" y="{ly}">{escape(name)}</text>')
    b.append(f'<text class="mut" x="{x(off / 1e6) + 6:.1f}" y="{T + 12}">continue on the targeted mix</text>')
    return svg(W, H, "".join(b), "Training loss over tokens for gd-kl1 and gd-kl2")


def dev_chart():
    W, H = 760, 330
    b = [f'<text class="t" x="40" y="26">Held-out dev accuracy during training</text>',
         f'<text class="st" x="40" y="46">Each run has its own dev set (1% of its mix, never trained on), so compare within a panel, '
         f'not across.</text>']
    panels = [("gd-kl1 · dev set of its mix", D["runs"]["gd-kl1"], "--s2", 40), ("gd-kl2 · dev set of its mix", D["runs"]["gd-kl2"], "--s1", 410)]
    for title, run, var, L in panels:
        Wp, T, B = 320, 80, 50
        dev = run["dev"]
        lo = min(d["acc"] for d in dev) * 100 - 1.5
        hi = max(d["acc"] for d in dev) * 100 + 1.5
        x = scale(0, run["steps"], L + 30, L + Wp)
        y = scale(lo, hi, H - B, T)
        b.append(f'<text class="lab" x="{L}" y="{T - 14}" font-weight="600">{escape(title)} (n={dev[0]["n"]:,})</text>')
        for v in range(int(lo) + 1, int(hi) + 1):
            if v % 2 == 0:
                b.append(f'<line class="grid" x1="{L + 30}" x2="{L + Wp}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                         f'<text class="ax" x="{L + 24}" y="{y(v) + 4:.1f}" text-anchor="end">{v}%</text>')
        b.append(f'<line class="base" x1="{L + 30}" x2="{L + Wp}" y1="{H - B}" y2="{H - B}"/>')
        P = [(x(d["step"]), y(d["acc"] * 100)) for d in dev]
        b.append(f'<path d="{path(P)}" fill="none" stroke="var({var})" stroke-width="2"/>')
        for d, (px, py) in zip(dev, P):
            b.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="var({var})" stroke="var(--surface)" stroke-width="2">'
                     f'<title>step {d["step"]}: accuracy {d["acc"] * 100:.1f}%, dev CE {d["ce"]}</title></circle>'
                     f'<text class="ax" x="{px:.1f}" y="{H - B + 16}" text-anchor="middle">{d["step"]}</text>')
        f, l = dev[0], dev[-1]
        b.append(f'<text class="lab" x="{P[0][0]:.1f}" y="{P[0][1] - 10:.1f}">{f["acc"] * 100:.1f}%</text>'
                 f'<text class="lab" x="{P[-1][0]:.1f}" y="{P[-1][1] - 10:.1f}" text-anchor="end">{l["acc"] * 100:.1f}%</text>')
        b.append(f'<text class="mut" x="{L + 30}" y="{H - 12}">step · dev CE {f["ce"]} → {l["ce"]}</text>')
    return svg(W, H, "".join(b), "Dev accuracy at each checkpoint for gd-kl1 and gd-kl2")


def blend_chart():
    W, H, L, R, T, B = 760, 360, 58, 150, 74, 50
    kl = D["panels"]["knowline-sgl-sample"]["index"]
    x = scale(0, 100, L, W - R)
    y = scale(68.0, 71.0, H - B, T)
    b = [f'<text class="t" x="{L}" y="26">Half fine-tune, half base scores best</text>',
         f'<text class="st" x="{L}" y="46">Decision Index dev sample (11,025 requests) for weight-space blends of each fine-tune with '
         f'KnowLine-31B-Gen1.5.</text>',
         f'<text class="st" x="{L}" y="61">0% = KnowLine alone ({kl}); 100% = the fine-tune alone.</text>']
    for v in (68, 69, 70, 71):
        b.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                 f'<text class="ax" x="{L - 8}" y="{y(v) + 4:.1f}" text-anchor="end">{v}</text>')
    for v in (0, 50, 70, 100):
        b.append(f'<text class="ax" x="{x(v):.1f}" y="{H - B + 18}" text-anchor="middle">{v}%</text>')
    b.append(f'<line class="base" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>'
             f'<text class="ax" x="{(L + W - R) / 2}" y="{H - 10}" text-anchor="middle">share of fine-tuned weights in the blend</text>')
    b.append(f'<line stroke="var(--ref)" stroke-dasharray="4 4" x1="{L}" x2="{W - R}" y1="{y(kl):.1f}" y2="{y(kl):.1f}"/>'
             f'<text class="mut" x="{L + 8}" y="{y(kl) + 16:.1f}">KnowLine alone {kl}</text>')
    for run, var, name in (("gd-kl1", "--s2", "gd-kl1 blends"), ("gd-kl2", "--s1", "gd-kl2 blends (decide-1 at 50%)")):
        bs = D["runs"][run]["blend_sample_index"]
        pts = [(0, kl)] + [(float(a) * 100, v) for a, v in sorted(bs.items())]
        P = [(x(a), y(v)) for a, v in pts]
        b.append(f'<path d="{path(P)}" fill="none" stroke="var({var})" stroke-width="2"/>')
        for (a, v), (px, py) in zip(pts[1:], P[1:]):
            b.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="var({var})" stroke="var(--surface)" stroke-width="2">'
                     f'<title>{run} at {a:.0f}%: {v}</title></circle>')
        b.append(f'<line x1="{W - R + 6}" x2="{W - R + 20}" y1="{P[-1][1]:.1f}" y2="{P[-1][1]:.1f}" stroke="var({var})" stroke-width="2"/>'
                 f'<text class="lab" x="{W - R + 24}" y="{P[-1][1] + 4:.1f}">{run} {pts[-1][1]}</text>')
        top = max(pts[1:], key=lambda p: p[1])
        dy = -10 if run == "gd-kl1" else 20
        b.append(f'<text class="lab" x="{x(top[0]):.1f}" y="{y(top[1]) + dy:.1f}" text-anchor="middle">{top[1]}</text>')
    return svg(W, H, "".join(b), "Dev-sample index against blend weight")


def panel_chart():
    rows = [r for r in D["per_benchmark_decide1_vs_knowline"] if r["name"] != "HLE"]
    rows = sorted(rows, key=lambda r: r["delta_pts"], reverse=True)
    # Benchmarks whose official train split is in gd-kl1's or gd-kl2's mix (data manifests, split/* sources).
    trained = {"BANKING77", "Amazon ESCI", "New Yorker caption matching", "CLINC150+OOS", "HoVer claim verification",
               "HellaSwag", "WinoGrande", "GSM8K", "ChessBench", "API-Bank", "When2Call MCQ"}
    short = {"RAGTruth response-level hallucination": "RAGTruth hallucination", "PhishNChips phishing decisions": "PhishNChips",
             "New Yorker caption matching": "New Yorker captions", "HoVer claim verification": "HoVer"}
    rh, T, B, L, W = 17, 84, 40, 250, 760
    H = T + rh * len(rows) + B
    lim = max(abs(r["delta_pts"]) for r in rows)
    lim = (int(lim) + 1)
    x = scale(-lim, lim, L, W - 60)
    d1, kl = D["panels"]["gd-kl2-s1000-a0.5-panel"]["index"], D["panels"]["knowline-sgl-panel"]["index"]
    b = [f'<text class="t" x="24" y="26">decide-1 against KnowLine-31B-Gen1.5, per benchmark</text>',
         f'<text class="st" x="24" y="46">Decision Index 0.3 public panel, skill points (same harness, same rows). Index {kl} → {d1}. '
         f'HLE (gated, 0 for both) omitted.</text>',
         f'<text class="st" x="24" y="61">* = its train split is in the training mix. Small benchmarks move a few points from noise alone; '
         f'read the pattern, not single bars.</text>']
    for v in range(-lim, lim + 1):
        if v % 2 == 0:
            b.append(f'<line class="grid" x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T - 4}" y2="{H - B}"/>'
                     f'<text class="ax" x="{x(v):.1f}" y="{H - B + 16}" text-anchor="middle">{v:+d}</text>')
    b.append(f'<line class="base" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="{T - 4}" y2="{H - B}"/>')
    for i, r in enumerate(rows):
        cy = T + i * rh
        d = r["delta_pts"]
        x0, x1 = sorted((x(0), x(d)))
        col = "var(--pos)" if d >= 0 else "var(--neg)"
        b.append(f'<text class="lab" x="{L - 10}" y="{cy + 12}" text-anchor="end">{escape(short.get(r["name"], r["name"]))}{" *" if r["name"] in trained else ""}</text>')
        b.append(f'<rect x="{x0:.1f}" y="{cy + 3}" width="{max(1.0, x1 - x0):.1f}" height="{rh - 5}" rx="2" fill="{col}">'
                 f'<title>{escape(r["name"])}: KnowLine {r["knowline"] * 100:.1f}, decide-1 {r["decide1"] * 100:.1f} ({d:+.2f})</title></rect>')
        tx = x(d) + (5 if d >= 0 else -5)
        b.append(f'<text class="ax" x="{tx:.1f}" y="{cy + 12}" text-anchor="{"start" if d >= 0 else "end"}">{d:+.1f}</text>')
    return svg(W, H, "".join(b), "Per-benchmark change of decide-1 against KnowLine")


for name, fn in (("loss", loss_chart), ("dev", dev_chart), ("blend", blend_chart), ("panel", panel_chart)):
    (HERE / f"{name}.svg").write_text(fn())
    print("wrote", HERE / f"{name}.svg")
