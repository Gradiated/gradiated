import { useId } from "react";
import { laterComparisons } from "./laterComparisons";
import { hardwareScales, profileFraction } from "./profileScales";
import { measurements } from "./measurementData";
import "./measured-profile.css";

const original = measurements[0].value;
const final = laterComparisons["measure-clock-rate"].value;
const joulesPerDollar = 3_600_000 / (0.2451 * 1.3431);
const num = (n: number, places = 0) =>
  n.toLocaleString("en-GB", { maximumFractionDigits: places });

const axes = [
  { key: "latency", label: "First token", start: 1000, end: 0.1, before: original.ttftMs, after: final.ttftMs, format: (v: number) => num(v, 1) + " ms" },
  { key: "speed", label: "Decode speed", start: 1, end: 20_000, before: original.decodeTps, after: final.decodeTps, format: (v: number) => num(v) + " tokens/s" },
  { key: "efficiency", label: "Module efficiency", start: 1, end: 10_000, before: 1 / original.joulesPerToken, after: 1 / final.joulesPerToken, format: (v: number) => num(v, v < 100 ? 1 : 0) + " tokens/J" },
  { key: "bandwidth", label: "Memory bandwidth", ...hardwareScales.bandwidth, before: 19.2, after: 19.2, format: (v: number) => num(v, 1) + " GB/s peak" },
  { key: "capacity", label: "Weight capacity", ...hardwareScales.capacity, before: 2e9, after: 2e9, format: (v: number) => "≈" + num(v / 1e9) + "B in DDR4" },
] as const;

function point(index: number, fraction: number) {
  const angle = index * 2 * Math.PI / axes.length - Math.PI / 2;
  return [210 + 97 * fraction * Math.cos(angle), 154 + 97 * fraction * Math.sin(angle)];
}

function outline(series: "before" | "after") {
  return axes.map((axis, index) => {
    const fraction = profileFraction(axis[series], axis);
    return point(index, fraction).join(",");
  }).join(" ");
}

const labels = [[210, 16], [357, 111], [302, 261], [118, 261], [65, 111]];
const money = (joulesPerToken: number) => num(joulesPerDollar / joulesPerToken / 1e9, 2);

export type ProfileSpecs = { weightCount: number; bandwidth: number; latency: number; speed: number; efficiency: number };

export function ProfilePlot({ title, comparison = false, compact = false, specs }: {
  title: string;
  comparison?: boolean;
  compact?: boolean;
  specs?: ProfileSpecs;
}) {
  const id = useId();
  const readings = axes.map(axis => {
    if (!specs) return axis.after;
    switch (axis.key) {
      case "capacity": return specs.weightCount;
      case "bandwidth": return specs.bandwidth;
      case "latency": case "speed": case "efficiency": return specs[axis.key];
    }
  });
  const points = readings.map((value, i) => point(i, profileFraction(value, axes[i])).join(","));
  const values = readings.map((value, i) => {
    const axis = axes[i];
    if (specs && (axis.key === "latency" || axis.key === "speed" || axis.key === "efficiency")) {
      return "≈" + axis.format(Number(value.toPrecision(2)));
    }
    if (specs && axis.key === "capacity") return "≈" + num(value / 1e9, 1) + "B weights";
    return axis.format(value);
  });
  return (
    <svg viewBox={compact ? "105 40 210 210" : "0 0 420 312"} role="img" aria-label={compact ? title : undefined} aria-labelledby={compact ? undefined : id + "-title"} aria-describedby={id + "-values"}>
      {!compact && <title id={id + "-title"}>{title}</title>}
      <desc id={id + "-values"}>{axes.map((axis, i) =>
        axis.label + " " + (comparison && axis.before !== axis.after ? axis.format(axis.before) + " to " : "") + values[i]
      ).join(". ")}</desc>
      <g className="kv-profile-grid">
        {[0.25, 0.5, 0.75, 1].map(fraction => <polygon key={fraction}
          points={axes.map((_, index) => point(index, fraction).join(",")).join(" ")} />)}
        {axes.map((axis, i) => { const [x,y] = point(i,1); return <line key={axis.label} x1="210" y1="154" x2={x} y2={y} />; })}
      </g>
      {specs ? <g className="kv-profile-estimate">
        <polygon points={points.join(" ")} />
        {readings.map((value, i) => {
          const [x, y] = point(i, profileFraction(value, axes[i]));
          return <circle key={axes[i].label} cx={x} cy={y} r="3" />;
        })}
      </g> : <polygon className="kv-profile-after" points={points.join(" ")} />}
      {comparison && <polygon className="kv-profile-before" points={outline("before")} />}
      {!compact && axes.map((axis, i) => {
        const [x, y] = labels[i];
        return <text key={axis.label} x={x} y={y} textAnchor="middle">
          {axis.label}
          <tspan className="kv-profile-value" x={x} dy="17">{comparison ? axis.format(axis.before) : values[i]}</tspan>
          {comparison && axis.before !== axis.after &&
            <tspan className="kv-profile-new-value" x={x} dy="16">{values[i]}</tspan>}
        </text>;
      })}
    </svg>
  );
}
 
export function MeasuredProfile({ comparison = false }: { comparison?: boolean }) {
  const id = useId();
  return (
    <section className={`kv-profile ${comparison ? "kv-profile-final fpga-columns" : ""}`}
      id={comparison ? "fpga-final-profile" : "fpga-inference-profile"} aria-labelledby={id}>
      <figure className="kv-profile-plot">
        <ProfilePlot comparison={comparison}
          title={comparison ? "Baseline experiment and experiment 24" : "Experiment 24 on the KV260"} />
      </figure>
      <div className="kv-profile-copy">
        <h2 id={id}>{comparison ? "The same FPGA, after 24 experiments" : "Our tiny transformer on the Kria KV260"}</h2>
        <p>{comparison
          ? "The same board now generates nearly six times as many tokens each second. Each joule now buys about six times as many output tokens. The board has the same memory and the same reconfigurable logic."
          : "Our fastest circuit generated 1,222 tokens per second with the FPGA running at 52.63 MHz."}</p>
        {comparison && (
          <>
            <div className="kv-profile-key"><span>Baseline experiment</span><span>Experiment 24</span></div>
            <p className="kv-profile-cost">{money(original.joulesPerToken)} billion → {money(final.joulesPerToken)} billion output tokens per US dollar of module electricity.</p>
            <details>
              <summary>How to read this chart</summary>
              <p>Further out means better on each axis, including a shorter wait for the first token. Each step between rings changes the value by the same factor on that axis.</p>
              <p>Memory bandwidth is the DDR4 interface’s peak rate. Weight capacity assumes all 4 GB of DDR4 are used for 16-bit weights.</p>
              <p>The electricity estimate covers the K26 module during the tests. We used the April–June 2026 averages of 24.51p per kWh for UK businesses and US$1.3431 per pound. At those rates, US$1 buys about 10.94 million joules. Divide that by the energy used per output token to get the figures above.</p>
              <a href="#fpga-measuring-inference">Measurement method and sources</a>
            </details>
          </>
        )}
      </div>
    </section>
  );
}
