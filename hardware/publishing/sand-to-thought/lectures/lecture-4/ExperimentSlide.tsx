import { useId, useSyncExternalStore } from "react";
import type { CSSProperties } from "react";
import { ChipMap } from "../../articles/fpga/figures/ChipMap";
import {
  ClockDistribution,
  bramBlock,
  dspBlock,
} from "../../articles/fpga/figures/ChipContinuation";
import { FabricUsageChart } from "../../articles/fpga/figures/MeasurementMechanism";
import { MeasurementChart } from "../../articles/fpga/figures/MeasurementChart";
import { measurements } from "../../articles/fpga/figures/measurementData";
import {
  laterComparisons,
  type ComparisonScene,
} from "../../articles/fpga/figures/laterComparisons";
import {
  measurementScenes,
  measurementStepFor,
} from "../../articles/fpga/figures/scenes";
import { stories, type Story, type Transfer } from "./experimentStories";
import { Multipliers, ScoringRows } from "./LectureCloseup";
import { ExperimentComparison } from "./ExperimentComparison";
import { ExperimentGroups } from "./ExperimentGroups";
import "./experimentSlides.css";

type Site = Transfer[0];

function port(site: Site, other: Site) {
  if (site === "outside") return { x: 340, y: 26, track: 340 };
  if (site === "bram" || site === "dsp") {
    const block = site === "bram" ? bramBlock : dspBlock;
    return { x: block.x, y: block.y + block.h / 2, track: block.x - 32 };
  }
  const x = 196 + 120 * ((site - 1) % 3);
  // Enter neighbouring CLBs from the facing edge so paths stay out of tile labels.
  const faceLeft =
    typeof other === "number" && (other - 1) % 3 < (site - 1) % 3;
  const edge = faceLeft ? x - 72 : x;
  return {
    x: edge,
    y: 160 + 120 * Math.floor((site - 1) / 3),
    track: faceLeft ? edge - 24 : edge + 24,
  };
}

// Use the channels between tiles. The first and last points sit on block edges.
function route(from: Site, to: Site) {
  const a = port(from, to),
    b = port(to, from);
  const row =
    from === "outside" || to === "outside" ? 100 : Math.min(a.y, b.y) + 60;
  if (a.track === b.track) return `M${a.x} ${a.y}H${a.track}V${b.y}H${b.x}`;
  if (a.y === b.y && Math.abs(a.x - b.x) <= 72) return `M${a.x} ${a.y}H${b.x}`;
  const start =
    from === "outside" ? `M${a.x} ${a.y}` : `M${a.x} ${a.y}H${a.track}`;
  return to === "outside"
    ? `${start}V${row}H${b.track}V${b.y}`
    : `${start}V${row}H${b.track}V${b.y}H${b.x}`;
}

function BlockLabel({ x, y, label }: { x: number; y: number; label: string }) {
  const lines = label.split("|");
  return (
    <text x={x} y={y} className="lecture-chip-label">
      {lines.map((line, i) => (
        <tspan key={line} x={x} dy={i === 0 ? -(lines.length - 1) * 9 : 18}>
          {line}
        </tspan>
      ))}
    </text>
  );
}

function HardwareBlock({
  x,
  y,
  w,
  h,
  name,
  detail,
  lanes,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  name: string;
  detail?: string;
  lanes?: number;
}) {
  return (
    <g className="lecture-chip-block" data-active={Boolean(detail)}>
      <rect x={x} y={y} width={w} height={h} rx="5" />
      <BlockLabel
        x={x + w / 2}
        y={y + h / 2 - (detail ? 11 : 0)}
        label={name}
      />
      {detail && (
        <text className="lecture-chip-sub" x={x + w / 2} y={y + h / 2 + 11}>
          {detail}
        </text>
      )}
      {lanes &&
        Array.from({ length: lanes }, (_, i) => (
          <rect
            key={i}
            className="lecture-chip-lane"
            x={x + 8 + (i * (w - 16)) / lanes}
            y={y + h - 12}
            width={(w - 16) / lanes - 3}
            height="5"
            rx="1"
          />
        ))}
    </g>
  );
}

function ClockTraces({ periods }: { periods: readonly [number, number] }) {
  const start = 79;
  const scale = 3.4;
  const cycles = 4;
  const axis = 108;
  return (
    <svg
      className="lecture-clock-traces lecture-detail"
      viewBox="0 0 400 145"
      role="img"
      aria-label="Four cycles take 80 nanoseconds at 50 MHz and 76 at 52.63 MHz, on the same time axis."
    >
      <text x="200" y="15">
        Four clock cycles
      </text>
      <path className="detail-guide" d={`M${start} 30V${axis}H368`} />
      <text x={start} y="126">
        0 ns
      </text>
      {periods.map((period, i) => {
        const y = 53 + i * 37,
          half = (period * scale) / 2,
          end = start + cycles * period * scale;
        return (
          <g key={period}>
            <text x={start - 6} y={y - 6} textAnchor="end">
              <tspan x={start - 6} dy="-7">{i === 0 ? "Before" : "After"}</tspan>
              <tspan x={start - 6} dy="15">{Number((1000 / period).toFixed(2))} MHz</tspan>
            </text>
            <path
              className="detail-wire"
              d={`M${start} ${y} ${`v-15h${half}v15h${half}`.repeat(cycles)}`}
            />
            <path
              className="detail-guide"
              strokeDasharray="3 3"
              d={`M${end} ${y}V${axis + 4}`}
            />
            <text
              x={end + (i === 0 ? 1 : -1)}
              y="126"
              textAnchor={i === 0 ? "start" : "end"}
            >
              {period * cycles} ns
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const phoneQuery =
  "(orientation: portrait), (max-height: 530px) and (max-width: 960px)";
function subscribePhone(onChange: () => void) {
  const media = window.matchMedia(phoneQuery);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

// Frame the active resources and leave room for the wires in adjoining channels.
function activeViewBox(story: Story) {
  const boxes = Object.keys(story.labels).map((site) => {
    if (site === "outside") return { x: 271, y: -6, w: 138, h: 32 };
    if (site === "bram") return bramBlock;
    if (site === "dsp") return dspBlock;
    const i = Number(site) - 1;
    return {
      x: 124 + 120 * (i % 3),
      y: 124 + 120 * Math.floor(i / 3),
      w: 72,
      h: 72,
    };
  });
  const left = Math.min(...boxes.map((b) => b.x)) - 34;
  const top = Math.min(...boxes.map((b) => b.y)) - 20;
  return [
    left,
    top,
    Math.max(...boxes.map((b) => b.x + b.w)) + 34 - left,
    Math.max(...boxes.map((b) => b.y + b.h)) + 36 - top,
  ].join(" ");
}

function ChipExperiment({ story, scene }: { story: Story; scene: string }) {
  const id = useId();
  const phone = useSyncExternalStore(
    subscribePhone,
    () => window.matchMedia(phoneQuery).matches,
    () => false,
  );
  const steps = story.phases.length;
  const seconds = steps * 1.55;
  let closeup;
  if (story.multipliers)
    closeup = <Multipliers shared={story.multipliers === 1} />;
  else if (story.detail === "lanes" && story.lanes)
    closeup = <ScoringRows count={story.lanes} />;
  else if (story.clockPeriodsNs)
    closeup = <ClockTraces periods={story.clockPeriodsNs} />;
  return (
    <figure
      className="lecture-chip-experiment"
      data-steps={steps}
      data-closeup={Boolean(closeup)}
      style={{ "--period": `${seconds}s` } as CSSProperties}
    >
      <figcaption>{story.description}</figcaption>
      <svg
        className="lecture-chip-map"
        data-full-map={story.detail === "full-map"}
        viewBox={
          phone && !closeup && story.detail !== "full-map"
            ? activeViewBox(story)
            : story.labels.outside
              ? "14 -17 736 563"
              : "14 20 736 526"
        }
        role="img"
        aria-label={`FPGA schematic. ${story.phases.join(". ")}. ${story.comparison}`}
      >
        <defs>
          <marker
            id={id}
            viewBox="0 0 8 8"
            refX="7.5"
            refY="4"
            markerWidth="3"
            markerHeight="3"
            orient="auto"
          >
            <path d="M0 0L8 4 0 8Z" fill="var(--lecture-signal)" />
          </marker>
        </defs>
        <g className="lecture-chip-base">
          <ChipMap miniature expanded highlight="blank" selectedBlocks={[]} />
        </g>
        {Array.from({ length: 9 }, (_, i) => {
          const site = (i + 1) as Site;
          const x = 124 + 120 * (i % 3),
            y = 124 + 120 * Math.floor(i / 3);
          const label = story.labels[site];
          return (
            <g
              key={i}
              className="lecture-chip-tile"
              data-active={Boolean(label)}
            >
              {label && <rect x={x} y={y} width="72" height="72" rx="4" />}
              <BlockLabel x={x + 36} y={y + 36} label={label ?? "CLB"} />
            </g>
          );
        })}
        <HardwareBlock
          {...bramBlock}
          name="BRAM"
          detail={story.labels.bram}
          lanes={story.lanes}
        />
        <HardwareBlock
          {...dspBlock}
          name="DSP"
          detail={story.labels.dsp}
          lanes={story.multipliers ?? story.lanes}
        />
        <HardwareBlock x={508} y={364} w={136} h={72} name="Configuration" />
        {story.clockPeriodsNs ? (
          <ClockDistribution>
            <HardwareBlock
              x={528}
              y={468}
              w={116}
              h={52}
              name="Clock"
              detail="52.63 MHz"
            />
          </ClockDistribution>
        ) : (
          <HardwareBlock x={528} y={480} w={96} h={28} name="Clock" />
        )}
        {story.labels.outside && (
          <g className="lecture-chip-block" data-active="true">
            <rect x="271" y="-6" width="138" height="32" rx="4" />
            <BlockLabel x={340} y={10} label={story.labels.outside} />
          </g>
        )}
        {!closeup &&
          story.transfers.map(([from, to, phase], i) => {
            const d = route(from, to);
            return (
              <g
                key={i}
                className="lecture-chip-phase"
                style={{ "--delay": `${phase * 1.55}s` } as CSSProperties}
              >
                <path
                  className="lecture-chip-route"
                  d={d}
                  markerEnd={`url(#${id})`}
                />
                <circle r="5.5" className="lecture-chip-packet" opacity="0">
                  <animateMotion
                    path={d}
                    dur={`${seconds}s`}
                    repeatCount="indefinite"
                    calcMode="linear"
                    keyTimes={`0;${(phase + 0.05) / steps};${(phase + 0.94) / steps};1`}
                    keyPoints="0;0;1;1"
                  />
                  <animate
                    attributeName="opacity"
                    dur={`${seconds}s`}
                    repeatCount="indefinite"
                    calcMode="discrete"
                    keyTimes={`0;${(phase + 0.05) / steps};${(phase + 0.94) / steps};1`}
                    values="0;1;0;0"
                  />
                </circle>
              </g>
            );
          })}
      </svg>
      <div className="lecture-build-detail">
        <ExperimentComparison scene={scene} closeup={closeup} />
      </div>
      {!(["measure-multiply", "measure-divide", "measure-lutram", "measure-probability-div", "measure-feedforward-multiply"].includes(scene)) && <p>{story.comparison}</p>}
    </figure>
  );
}

function TokenFlow({
  stages,
  scene,
}: {
  stages: Story["stages"];
  scene: string;
}) {
  const id = useId();
  const baseline = scene === "measuring-inference";
  const picker = baseline ? "CPU" : "FPGA";
  const paired = scene === "measure-exp-pair";
  const nodes = [
    { x: 6, y: 5, lines: ["Embedding"], active: stages.includes("input") },
    { x: 116, y: 5, lines: ["Normalise"], active: stages.includes("norm") },
    {
      x: 226,
      y: 5,
      lines: paired ? ["Attention", "Head 1 of 2"] : ["Attention"],
      active: stages.includes("attention"),
    },
    { x: 336, y: 5, lines: ["KV cache"], active: stages.includes("cache") },
    {
      x: 336,
      y: 61,
      lines: ["Normalise", "Feed-forward"],
      active: stages.includes("feedForward") || stages.includes("norm"),
    },
    {
      x: 226,
      y: 61,
      lines: ["Final normalise"],
      active: stages.includes("norm"),
    },
    {
      x: 116,
      y: 61,
      lines: ["Scoring layer"],
      active: stages.includes("logits"),
    },
    {
      x: 6,
      y: 61,
      lines: ["Pick token", picker],
      active: baseline || stages.includes("control"),
    },
  ];
  return (
    <svg
      className="lecture-token-flow"
      viewBox="0 0 436 100"
      role="img"
      aria-label={`Embedding, normalisation, attention with its KV cache, normalisation, feed-forward, final normalisation and scoring. The ${picker} picks the next token and returns it to embedding.${paired ? " Two scores in attention head 1 are processed together." : ""}`}
    >
      <defs>
        <marker
          id={id}
          viewBox="0 0 6 6"
          refX="5.5"
          refY="3"
          markerWidth="4"
          markerHeight="4"
          orient="auto"
        >
          <path d="M0 0L6 3L0 6Z" fill="var(--measurement-line)" />
        </marker>
      </defs>
      {[
        "M100 22H116",
        "M210 22H226",
        "M273 39V50H383V61",
        "M336 78H320",
        "M226 78H210",
        "M116 78H100",
        "M53 61V39",
      ].map((d) => (
        <path
          key={d}
          d={d}
          className="fpga-measurement-guide"
          markerEnd={`url(#${id})`}
        />
      ))}
      <path
        d="M320 22H336"
        className="fpga-measurement-guide"
        strokeDasharray="3 2"
      />
      {nodes.map(({ x, y, lines, active }) => (
        <g
          key={x + "-" + y}
          className="fpga-measurement-node"
          data-active={active}
        >
          <rect x={x} y={y} width="94" height="34" rx="4" />
          {lines.map((line, i) => (
            <text
              key={line}
              x={x + 47}
              y={y + 17 + (i - (lines.length - 1) / 2) * 14}
            >
              {line}
            </text>
          ))}
        </g>
      ))}
    </svg>
  );
}

export function ExperimentSlide({ scene }: { scene: string }) {
  const story = stories[scene];
  const early = measurementStepFor(scene);
  const late = laterComparisons[scene as ComparisonScene];
  const step =
    early >= 0
      ? early
      : measurementScenes.length + Object.keys(laterComparisons).indexOf(scene);
  return (
    <div className="lecture-results-grid" key={scene}>
      <div className="lecture-results-context fpga-measurement-mechanisms">
        <div className="fpga-measurement-panel">
          <div className="fpga-measurement-panel-title">Generating a token</div>
          <TokenFlow scene={scene} stages={story.stages} />
        </div>
        <FabricUsageChart
          usage={early >= 0 ? measurements[early].resources : late.resources}
          ddr4WeightsKiB={late?.ddr4WeightsKiB}
        />
        <div className="lecture-results-chart">
          <MeasurementChart step={step} />
          <ExperimentGroups step={step} />
        </div>
      </div>
      <ChipExperiment key={scene} story={story} scene={scene} />
    </div>
  );
}
