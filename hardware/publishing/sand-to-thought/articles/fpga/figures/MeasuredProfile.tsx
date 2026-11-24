import { useId, type ReactNode } from "react";
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
  { key: "efficiency", label: "Energy efficiency", start: 1, end: 10_000, before: 1 / original.joulesPerToken, after: 1 / final.joulesPerToken, format: (v: number) => num(v, v < 100 ? 1 : 0) + " tokens/J" },
  { key: "bandwidth", label: "Memory bandwidth", ...hardwareScales.bandwidth, before: 19.2, after: 19.2, format: (v: number) => num(v, 1) + " GB/s peak" },
  { key: "capacity", label: "Weight capacity", ...hardwareScales.capacity, before: 2e9, after: 2e9, format: (v: number) => "≈" + num(v / 1e9) + "B in DDR4" },
] as const;

function point(index: number, fraction: number, radius = 97) {
  const angle = index * 2 * Math.PI / axes.length - Math.PI / 2;
  return [
    210 + radius * fraction * Math.cos(angle),
    154 + radius * fraction * Math.sin(angle),
  ];
}

function outline(series: "before" | "after", radius: number) {
  return axes.map((axis, index) => {
    const fraction = profileFraction(axis[series], axis);
    return point(index, fraction, radius).join(",");
  }).join(" ");
}

const labels = [[210, 16], [357, 111], [302, 261], [118, 261], [65, 111]];
const openingLabels = [
  [210, 15], [352, 88], [293, 269], [127, 269], [68, 88],
];
const comparisonLabels = [
  [210, -1], [352, 76], [293, 269], [127, 269], [68, 76],
];

const profileValue = (value: string) => {
  const [number, ...unit] = value.split(" ");
  return (
    <>
      {number}
      <tspan className="kv-profile-unit">{" "}{unit.join(" ")}</tspan>
    </>
  );
};

const money = (joulesPerToken: number) => num(joulesPerDollar / joulesPerToken / 1e9, 2);

export type ProfileSpecs = { weightCount: number; bandwidth: number; latency: number; speed: number; efficiency: number };

export function ProfilePlot({
  title,
  comparison = false,
  compact = false,
  opening = false,
  specs,
}: {
  title: string;
  comparison?: boolean;
  compact?: boolean;
  opening?: boolean;
  specs?: ProfileSpecs;
}) {
  const id = useId();
  const measured = opening || comparison;
  const radius = measured ? 108 : 97;
  const labelPositions = comparison ? comparisonLabels : opening ? openingLabels : labels;
  const fullViewBox = comparison ? "0 -21 420 334" : opening ? "0 -4 420 301" : "0 0 420 312";
  const readings = axes.map(axis => {
    if (!specs) return axis.after;
    switch (axis.key) {
      case "capacity": return specs.weightCount;
      case "bandwidth": return specs.bandwidth;
      case "latency": case "speed": case "efficiency": return specs[axis.key];
    }
  });
  const vertices = readings.map((value, i) =>
    point(i, profileFraction(value, axes[i]), radius),
  );
  const points = vertices.map((vertex) => vertex.join(",")).join(" ");
  const values = readings.map((value, i) => {
    const axis = axes[i];
    if (specs && (axis.key === "latency" || axis.key === "speed" || axis.key === "efficiency")) {
      return "≈" + axis.format(Number(value.toPrecision(2)));
    }
    if (specs && axis.key === "capacity") return "≈" + num(value / 1e9, 1) + "B weights";
    return axis.format(value);
  });
  return (
    <svg viewBox={compact ? "105 40 210 210" : fullViewBox} role="img" aria-label={compact ? title : undefined} aria-labelledby={compact ? undefined : id + "-title"} aria-describedby={id + "-values"}>
      {!compact && <title id={id + "-title"}>{title}</title>}
      <desc id={id + "-values"}>{axes.map((axis, i) =>
        axis.label + " " + (comparison && axis.before !== axis.after ? axis.format(axis.before) + " to " : "") + values[i]
      ).join(". ")}</desc>
      <g className="kv-profile-grid">
        {[0.25, 0.5, 0.75, 1].map((fraction) => (
          <polygon key={fraction} points={axes.map((_, i) =>
            point(i, fraction, radius).join(","),
          ).join(" ")} />
        ))}
        {axes.map((axis, i) => {
          const [x, y] = point(i, 1, radius + (measured ? 9 : 0));
          return <line key={axis.label} x1="210" y1="154" x2={x} y2={y} />;
        })}
      </g>
      {specs ? <g className="kv-profile-estimate">
        <polygon points={points} />
        {vertices.map(([x, y], i) => (
          <circle key={axes[i].label} cx={x} cy={y} r="3" />
        ))}
      </g> : <polygon className="kv-profile-after" points={points} />}
      {comparison && (
        <polygon className="kv-profile-before" points={outline("before", radius)} />
      )}
      {!compact && axes.map((axis, i) => {
        const [x, y] = labelPositions[i];
        const value = comparison ? axis.format(axis.before) : values[i];
        return (
          <text key={axis.label} x={x} y={y} textAnchor="middle">
            {axis.label}
            <tspan className="kv-profile-value" x={x} dy="17">
              {measured ? profileValue(value) : value}
            </tspan>
            {comparison && axis.before !== axis.after && (
              <tspan className="kv-profile-new-value" x={x} dy="16">
                {profileValue(values[i])}
              </tspan>
            )}
          </text>
        );
      })}
    </svg>
  );
}

export function MeasuredProfile({
  summary,
  readingGuide,
}: {
  summary?: ReactNode;
  readingGuide?: ReactNode;
}) {
  const id = useId();

  if (summary === undefined) {
    return (
      <section className="kv-profile kv-profile-opening" id="fpga-inference-profile" aria-labelledby={id}>
        <figure className="kv-profile-plot">
          <ProfilePlot opening title="Experiment 24 on the Kria KV260 running our tiny transformer" />
          <figcaption>
            <h2 id={id}>Our tiny transformer on the Kria KV260</h2>
          </figcaption>
        </figure>
      </section>
    );
  }

  return (
    <section className="kv-profile kv-profile-final fpga-columns" id="fpga-final-profile" aria-label="KV260 experiment comparison">
      <figure className="kv-profile-plot">
        <ProfilePlot comparison title="Baseline experiment and experiment 24" />
      </figure>
      <div className="kv-profile-copy">
        {summary}
        <div className="kv-profile-key"><span>Baseline experiment</span><span>Experiment 24</span></div>
        <p className="kv-profile-cost">{money(original.joulesPerToken)} billion → {money(final.joulesPerToken)} billion output tokens per US dollar of module electricity.</p>
        {readingGuide}
      </div>
    </section>
  );
}
