import { useId, useState } from "react";
import type { ReactElement } from "react";

/* Timings here are proportions for a drawing, not measurements. */
const L = 1.4;
const F = 4;
const O = 1.4;

type Lane = { x0: number; x1: number; label: string; tone?: "idle" | "opt" };
type Hop = { from: number; to: number; up: boolean; label?: string };

const SCHEDULES: Record<
  "pipelined" | "sequential",
  { gpu: Lane[]; hops: Hop[]; end: number; caption: string }
> = {
  sequential: {
    gpu: [
      { x0: L, x1: L + F, label: "forward + backward" },
      { x0: L + F, x1: 3 * L + F, label: "idle", tone: "idle" },
      { x0: 3 * L + F, x1: 3 * L + F + O, label: "optim", tone: "opt" },
    ],
    hops: [
      { from: 0, to: L, up: false, label: "forward_backward()" },
      { from: L + F, to: 2 * L + F, up: true, label: ".result()" },
      { from: 2 * L + F, to: 3 * L + F, up: false, label: "optim_step()" },
      { from: 3 * L + F + O, to: 4 * L + F + O, up: true },
    ],
    end: 4 * L + F + O,
    caption:
      "Reading the forward_backward() result before sending optim_step() leaves the GPU idle for a full network round trip on every step.",
  },
  pipelined: {
    gpu: [
      { x0: L, x1: L + F, label: "forward + backward" },
      { x0: L + F, x1: L + F + O, label: "optim", tone: "opt" },
    ],
    hops: [
      { from: 0, to: L, up: false, label: "forward_backward()" },
      { from: 0.35, to: L + 0.35, up: false, label: "optim_step()" },
      { from: L + F, to: 2 * L + F, up: true },
      { from: L + F + O, to: 2 * L + F + O, up: true, label: ".result()" },
    ],
    end: 4 * L + F + O,
    caption:
      "Both calls are queued before either result is read, so the server runs forward, backward and the update back to back. The client waits once.",
  },
};

export const PipelineSchematic = (): ReactElement => {
  const [mode, setMode] = useState<"pipelined" | "sequential">("pipelined");
  const name = useId();
  const schedule = SCHEDULES[mode];
  const W = 640;
  const left = 112;
  const unit = (W - left - 16) / SCHEDULES.sequential.end;
  const x = (t: number) => left + t * unit;
  const yClient = 40;
  const yGpu = 132;

  return (
    <figure className="gr-dx gr-dx-pipe">
      <fieldset className="gr-dx-seg">
        <legend>Calls</legend>
        <div>
          {(["pipelined", "sequential"] as const).map((option) => (
            <label key={option}>
              <input
                checked={mode === option}
                name={name}
                onChange={() => setMode(option)}
                type="radio"
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <svg
        aria-label={schedule.caption}
        className="gr-dx-pipe-chart"
        role="img"
        viewBox={`0 0 ${W} 180`}
      >
        <text className="gr-dx-axis" x={0} y={yClient + 4}>
          your process
        </text>
        <text className="gr-dx-axis" x={0} y={yGpu + 4}>
          trainer GPU
        </text>
        <line
          className="gr-dx-grid"
          x1={left}
          x2={W - 16}
          y1={yClient}
          y2={yClient}
        />
        <line
          className="gr-dx-grid"
          x1={left}
          x2={W - 16}
          y1={yGpu}
          y2={yGpu}
        />

        {schedule.gpu.map((lane) => (
          <g key={`${lane.label}-${lane.x0}`}>
            <rect
              className={`gr-dx-pipe-bar${lane.tone ? ` gr-dx-pipe-bar--${lane.tone}` : ""}`}
              height={20}
              rx={3}
              width={Math.max(0, x(lane.x1) - x(lane.x0) - 2)}
              x={x(lane.x0) + 1}
              y={yGpu - 10}
            />
            <text
              className="gr-dx-pipe-label"
              textAnchor="middle"
              x={(x(lane.x0) + x(lane.x1)) / 2}
              y={yGpu + 30}
            >
              {lane.label}
            </text>
          </g>
        ))}

        {schedule.hops.map((hop, i) => {
          const [y0, y1] = hop.up
            ? [yGpu - 12, yClient + 4]
            : [yClient + 4, yGpu - 12];
          return (
            <g key={i}>
              <line
                className="gr-dx-pipe-hop"
                markerEnd="url(#gr-dx-arrow)"
                x1={x(hop.from)}
                x2={x(hop.to)}
                y1={y0}
                y2={y1}
              />
              {hop.label ? (
                <text
                  className="gr-dx-pipe-call"
                  textAnchor="start"
                  x={x(hop.up ? hop.to : hop.from) + (hop.up ? 4 : 0)}
                  y={
                    yClient -
                    10 -
                    (i > 0 &&
                    !hop.up &&
                    Math.abs(hop.from - schedule.hops[i - 1].from) < 1
                      ? 14
                      : 0)
                  }
                >
                  {hop.label}
                </text>
              ) : null}
            </g>
          );
        })}

        <defs>
          <marker
            id="gr-dx-arrow"
            markerHeight="6"
            markerWidth="6"
            orient="auto-start-reverse"
            refX="5"
            refY="3"
            viewBox="0 0 6 6"
          >
            <path className="gr-dx-pipe-head" d="M0,0 L6,3 L0,6 z" />
          </marker>
        </defs>
      </svg>
      <figcaption className="gr-dx-caption">
        {schedule.caption} A schematic: the widths are not to scale.
      </figcaption>
    </figure>
  );
};

type Token = {
  text: string;
  role: "user" | "assistant" | "tool";
  turn: number;
};

const TOKENS: Token[] = [
  { text: "Count", role: "user", turn: 0 },
  { text: "users", role: "user", turn: 0 },
  { text: "sql(", role: "assistant", turn: 0 },
  { text: "SELECT", role: "assistant", turn: 0 },
  { text: "COUNT", role: "assistant", turn: 0 },
  { text: ")", role: "assistant", turn: 0 },
  { text: "rows:", role: "tool", turn: 0 },
  { text: "42", role: "tool", turn: 0 },
  { text: "There", role: "assistant", turn: 1 },
  { text: "are", role: "assistant", turn: 1 },
  { text: "42.", role: "assistant", turn: 1 },
];

export const DatumAnatomy = (): ReactElement => (
  <figure className="gr-dx gr-dx-datum">
    <div className="gr-dx-datum-scroll">
      <table>
        <tbody>
          <tr>
            <th scope="row">i</th>
            {TOKENS.map((_, i) => (
              <td className="gr-dx-muted" key={i}>
                {i}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">token</th>
            {TOKENS.map((token, i) => (
              <td
                data-trained={token.role === "assistant" ? "true" : undefined}
                key={i}
              >
                <code>{token.text}</code>
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">from</th>
            {TOKENS.map((token, i) => (
              <td className="gr-dx-muted" key={i}>
                {token.role}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">loss_mask</th>
            {TOKENS.map((token, i) => (
              <td
                data-trained={token.role === "assistant" ? "true" : undefined}
                key={i}
              >
                {token.role === "assistant" ? "1.0" : "0.0"}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">turn_ids</th>
            {TOKENS.map((token, i) => (
              <td key={i}>{token.turn}</td>
            ))}
          </tr>
          <tr>
            <th scope="row">advantages</th>
            {TOKENS.map((token, i) => (
              <td key={i}>{token.role === "assistant" ? "A" : "0"}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
    <figcaption className="gr-dx-caption">
      One record, one index per token: every per-token array has the same
      length, so column <code>i</code> describes the same token in each. Model
      tokens carry <code>loss_mask = 1.0</code>; the prompt and the tool's
      output are context only. <code>A</code> stands for the record's advantage,
      repeated on each token it applies to.
    </figcaption>
  </figure>
);
