import { useId } from "react";
import type { ReactNode } from "react";
import "./inference-profile.css";

export const inferenceProfileAxes = [
  { key: "cost", label: "Tokens per dollar", lines: ["Tokens per dollar"] },
  {
    key: "throughput",
    label: "Tokens per second",
    lines: ["Tokens per", "second"],
  },
  {
    key: "latency",
    label: "Time to first token",
    lines: ["Time to", "first token"],
  },
  { key: "capacity", label: "Model size", lines: ["Model size"] },
  {
    key: "bandwidth",
    label: "Memory bandwidth",
    lines: ["Memory", "bandwidth"],
  },
  { key: "energy", label: "Tokens per joule", lines: ["Tokens per", "joule"] },
] as const;

type ProfileScores = Record<
  (typeof inferenceProfileAxes)[number]["key"],
  number
>;

const centre = { x: 300, y: 240 };
const radius = 176;
const labels = [
  { x: 300, y: 28, anchor: "middle" },
  { x: 504, y: 139, anchor: "middle" },
  { x: 504, y: 341, anchor: "middle" },
  { x: 300, y: 450, anchor: "middle" },
  { x: 96, y: 341, anchor: "middle" },
  { x: 96, y: 139, anchor: "middle" },
] as const;
const point = (index: number, distance: number) => {
  const angle =
    (index * Math.PI * 2) / inferenceProfileAxes.length - Math.PI / 2;

  return {
    x: centre.x + Math.cos(angle) * distance,
    y: centre.y + Math.sin(angle) * distance,
  };
};
const polygon = (distances: readonly number[]) =>
  distances
    .map((distance, index) => {
      const { x, y } = point(index, distance);

      return `${x},${y}`;
    })
    .join(" ");

export const InferenceProfileChart = ({
  device,
  illustrativeScores,
  compact = false,
}: {
  device: string;
  illustrativeScores: ProfileScores;
  compact?: boolean;
}) => {
  const id = useId();
  const distances = inferenceProfileAxes.map(
    ({ key }) => illustrativeScores[key] * radius,
  );

  return (
    <figure className="inference-profile-chart">
      <svg
        viewBox={compact ? "110 50 380 380" : "0 0 600 480"}
        role="img"
        aria-labelledby={`${id}-title ${id}-description`}
      >
        <title id={`${id}-title`}>
          {`${device}: illustrative inference profile`}
        </title>
        <desc id={`${id}-description`}>
          Clockwise from the top:{" "}
          {inferenceProfileAxes.map(({ label }) => label).join(", ")}. Further
          out means better, including shorter time to first token. The outline
          uses placeholder scores, not measured performance or verified
          rankings.
        </desc>
        <g className="inference-profile-grid">
          {[0.25, 0.5, 0.75, 1].map((fraction) => (
            <polygon
              key={fraction}
              className={
                fraction === 1 ? "inference-profile-boundary" : undefined
              }
              points={polygon(
                inferenceProfileAxes.map(() => radius * fraction),
              )}
            />
          ))}
          {inferenceProfileAxes.map(({ key }, index) => {
            const end = point(index, radius);

            return (
              <line
                key={key}
                x1={centre.x}
                y1={centre.y}
                x2={end.x}
                y2={end.y}
              />
            );
          })}
        </g>
        <polygon
          className="inference-profile-shape"
          points={polygon(distances)}
        />
        {inferenceProfileAxes.map(({ key, lines }, index) => {
          const vertex = point(index, distances[index]);
          const label = labels[index];

          return (
            <g key={key}>
              <circle
                className="inference-profile-vertex"
                cx={vertex.x}
                cy={vertex.y}
                r={3}
              />
              {!compact && (
                <text
                  x={label.x}
                  y={label.y}
                  textAnchor={label.anchor}
                  dominantBaseline="middle"
                >
                  {lines.map((line, lineIndex) => (
                    <tspan
                      key={line}
                      x={label.x}
                      dy={
                        lineIndex === 0
                          ? lines.length === 1
                            ? 0
                            : "-0.575em"
                          : "1.15em"
                      }
                    >
                      {line}
                    </tspan>
                  ))}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </figure>
  );
};

export const InferenceProfile = ({
  anchor,
  device,
  illustrativeScores,
  specifications,
}: {
  anchor?: string;
  device: string;
  illustrativeScores: ProfileScores;
  specifications: readonly { label: string; value: ReactNode }[];
}) => {
  const id = useId();
  return (
    <section
      className="inference-profile"
      id={anchor}
      aria-labelledby={`${id}-heading`}
    >
      <InferenceProfileChart
        device={device}
        illustrativeScores={illustrativeScores}
      />
      <div className="inference-profile-copy">
        <h2 id={`${id}-heading`}>{device}</h2>
        <p className="inference-profile-placeholder">
          Placeholder until we measure
        </p>
        <dl>
          {specifications.map(({ label, value }) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
};
