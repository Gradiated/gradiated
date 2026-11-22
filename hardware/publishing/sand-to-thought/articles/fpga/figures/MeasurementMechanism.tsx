import { useId, type ReactNode } from "react";
import { ChipMap } from "./ChipMap";
import { fabricCapacity, measurements, type FabricUsage } from "./measurementData";
import "./measurement-mechanism.css";

type Stage = "input" | "norm" | "attention" | "feedForward" | "logits" | "control" | "cache";
type Resource = "Logic" | "DSP" | "BRAM" | "LUTs" | "CLBs + DSPs";

type ExperimentMechanism = {
  stages: readonly Stage[];
  resource: Resource;
  title: string;
  description: string;
};

const experiments = [
  {
    stages: [],
    resource: "Logic",
    title: "CPU chooses each token",
    description: "The FPGA sends its next-token scores to the CPU, which picks the next token and sends it back.",
  },
  {
    stages: ["control"],
    resource: "Logic",
    title: "FPGA chooses each token",
    description: "The FPGA reads the prompt, picks the token with the highest score and feeds it back until the reply is complete.",
  },
  {
    stages: ["input", "logits"],
    resource: "Logic",
    title: "Skip unused scores",
    description: "The FPGA processes every input token. It only calculates next-token scores at the end of the prompt.",
  },
  {
    stages: ["norm", "attention", "feedForward"],
    resource: "CLBs + DSPs",
    title: "Multiply four bits at once",
    description: "For 64-bit multiplication, the original circuit processed one bit per clock and needed 64 calculation steps. The new circuit processes four bits per clock and needs 16 calculation steps, using CLB logic and DSP blocks.",
  },
  {
    stages: ["norm", "attention", "feedForward"],
    resource: "Logic",
    title: "Divide two bits at once",
    description: "For 64-bit division, the original circuit found one answer bit per clock and needed 64 calculation steps. The new circuit finds two answer bits per clock and needs 32 calculation steps, using CLB logic. It then takes one final cycle to finish.",
  },
  {
    stages: ["logits"],
    resource: "CLBs + DSPs",
    title: "Read while calculating",
    description: "Before, calculating with the current pair and reading the next pair happened in separate clock cycles. After, the CLB controller overlaps reading the next input and weight with DSP circuitry multiplying the current input and weight and adding the product to the running total, during the same clock cycle.",
  },
  {
    stages: ["logits"],
    resource: "DSP",
    title: "Two scores at once",
    description: "Two lanes calculate next-token scores side by side. Each keeps its own running total.",
  },
  {
    stages: ["logits"],
    resource: "DSP",
    title: "Four scores at once",
    description: "Four lanes calculate next-token scores side by side. Each keeps its own running total.",
  },
  {
    stages: ["logits"],
    resource: "DSP",
    title: "Eight scores at once",
    description: "Eight lanes calculate next-token scores side by side. Each keeps its own running total.",
  },
  {
    stages: ["feedForward"],
    resource: "Logic",
    title: "Shorten feed-forward division",
    description: "When the feed-forward stage divides by 45,426, it can skip steps that would put zeros at the start of the answer.",
  },
  {
    stages: ["feedForward"],
    resource: "DSP",
    title: "Read ahead in feed-forward",
    description: "The feed-forward stage reads the next pair of numbers while adding the current product to its running total.",
  },
  {
    stages: ["attention", "cache"],
    resource: "BRAM",
    title: "Read ahead in the KV cache",
    description: "The FPGA requests the next key or value from the KV cache while adding the current product to its running total. It requests one entry at a time.",
  },
  {
    stages: ["attention"],
    resource: "Logic",
    title: "Shorten division in attention",
    description: "Attention uses the same shortcut as the feed-forward stage when dividing by 45,426.",
  },
  {
    stages: ["attention"],
    resource: "LUTs",
    title: "Move one set of weights",
    description: "The earlier build stored the weights that combine the attention heads’ outputs in BRAM. The new build stores the same weights in LUTs inside the CLBs. Each read takes the same number of clock cycles.",
  },
  {
    stages: ["attention"],
    resource: "Logic",
    title: "Two attention scores at once",
    description: "Within one attention head, two circuits calculate the exponentials for neighbouring scores at the same time. The results come out in the same order as before.",
  },
] as const satisfies readonly ExperimentMechanism[];

const modelStages = [
  { stage: "input", label: "Embedding", y: 8, expandedY: 8, height: 18 },
  { stage: "norm", label: "Normalise", y: 39, expandedY: 32, height: 14 },
  { stage: "attention", label: "Attention", y: 66, expandedY: 55, height: 18 },
  { stage: "feedForward", label: "Feed-forward", y: 97, expandedY: 104, height: 18 },
  { stage: "norm", label: "Final normalise", y: 128, expandedY: 132, height: 14 },
  { stage: "logits", label: "Scoring layer", y: 155, expandedY: 155, height: 18 },
] as const;

const resources = {
  Logic: { x: 280, y: 160 },
  DSP: { x: 484, y: 343 },
  "BRAM": { x: 484, y: 195 },
  LUTs: { x: 280, y: 280 },
} as const;

const fabricMapScale = 0.148;
const fabricMapOffsetX = 196 / 2 - 280 * fabricMapScale;

function ResourceCallout({ resource, earlierBuild = false }: { resource: Resource; earlierBuild?: boolean }) {
  const combined = resource === "CLBs + DSPs";
  const { x, y } = resources[combined ? "DSP" : resource];
  const radius = 42 * fabricMapScale;
  const label = resource === "Logic" ? "CLB Logic" : resource === "LUTs" ? "CLB" : resource;
  const labelX = combined ? 15 : 34;
  const labelLines = combined ? ["CLBs +", "DSPs"] : resource === "Logic" ? ["CLB", "Logic"] : null;
  return (
    <g className="fpga-measurement-callout" style={{ transform: `translate(${x}px, ${y}px)` }}>
      <g transform={`scale(${1 / fabricMapScale})`}>
        <circle className="fpga-measurement-map-focus" r={radius} />
        <path className="fpga-measurement-guide" d={combined ? `M${radius} 0H11` : `M${radius} 0H14L21 ${earlierBuild ? -6 : 0}H31`} />
        <text x={labelX} y={labelLines || earlierBuild ? -6 : 0}>
          {labelLines ? labelLines.map((line, index) => (
            <tspan key={line} x={labelX} dy={index === 0 ? 0 : 13}>{line}</tspan>
          )) : label}
        </text>
      </g>
    </g>
  );
}

function FabricMap({ resource }: { resource?: Resource | "Clock" }) {
  return (
    <g className="fpga-measurement-map">
      <ChipMap miniature highlight={resource === undefined ? "blank" : undefined} selectedBlocks={[]} />
      <g className="fpga-block fpga-block--memory">
        <rect x="468" y="124" width="32" height="142" rx="5" />
      </g>
      <g className="fpga-block fpga-block--arithmetic">
        <rect x="468" y="290" width="32" height="106" rx="5" />
      </g>
      {resource === "LUTs" && (
        <g className="fpga-measurement-previous-store">
          <ResourceCallout resource="BRAM" earlierBuild />
          <path d="M442 212L323 262l9-15m-9 15 17 3" />
        </g>
      )}
      <circle
        className="fpga-measurement-map-focus fpga-measurement-map-focus--logic"
        data-active={resource === "CLBs + DSPs"}
        cx={resources.Logic.x}
        cy={resources.Logic.y}
        r="42"
      />
      {resource && resource !== "Clock" && <ResourceCallout resource={resource} />}
    </g>
  );
}

export const ModelDiagram = ({ stages, step }: { stages: readonly Stage[]; step?: number }) => {
  const active = (stage: Stage) => stages.includes(stage);
  const headSelected = step === 14;
  const tokenPicker = step === 0 ? "CPU" : "FPGA";
  const rows = modelStages.map((row) => ({
    ...row,
    y: headSelected ? row.expandedY : row.y,
    height: headSelected && row.stage === "attention" ? 40 : row.height,
  }));

  return (
    <svg
      className="fpga-measurement-token-flow"
      viewBox="0 0 205 177"
      role="img"
      aria-label={`Generating a token: embedding, normalisation, attention, feed-forward, final normalisation and scoring. The ${tokenPicker} chooses the next token from the scores and returns it to embedding.${headSelected ? " Attention is expanded into two heads, with Head 1 highlighted." : ""}`}
    >
      {rows.slice(1).map((row, index) => {
        const from = rows[index].y + rows[index].height;

        return (
          <g key={row.label}>
            <path
              className="fpga-measurement-guide fpga-measurement-token-motion"
              d="M0 0V1"
              vectorEffect="non-scaling-stroke"
              style={{ transform: `translate(65px, ${from}px) scale(1, ${row.y - from})` }}
            />
            <path
              className="fpga-measurement-arrow fpga-measurement-token-motion"
              d="m-2.5-3.5 2.5 3.5 2.5-3.5"
              style={{ transform: `translate(65px, ${row.y}px)` }}
            />
          </g>
        );
      })}
      <path className="fpga-measurement-guide" d="M114 75H133" />
      <path
        className="fpga-measurement-guide"
        data-active={step === 0 || step === 1}
        d="M114 164H160V140M187 125H199V17H114"
      />
      <path
        className="fpga-measurement-arrow"
        data-active={step === 0 || step === 1}
        d="M157 144l3-4 3 4M119 13l-5 4 5 4"
      />
      <text className="fpga-measurement-small" x="160" y="7">Next token</text>
      <text className="fpga-measurement-small" x="179" y="155">Scores</text>
      {rows.map(({ stage, label, y, height }) => (
        <g
          key={label}
          className="fpga-measurement-node fpga-measurement-token-row fpga-measurement-token-motion"
          data-active={active(stage) && !(headSelected && stage === "attention")}
          style={{ transform: `translate(16px, ${y}px)` }}
        >
          <rect width="98" height={height} rx="3" />
          <text x="49" y={headSelected && stage === "attention" ? 10 : height / 2}>{label}</text>
          {stage === "attention" && (
            <g className="fpga-measurement-heads" data-visible={headSelected}>
              <path className="fpga-measurement-guide" d="M49 17V22H25M49 22H73" />
              {[5, 53].map((x, index) => (
                <g key={x} className="fpga-measurement-node" data-active={headSelected && index === 0}>
                  <rect x={x} y="22" width="40" height="13" rx="2" />
                  <text className="fpga-measurement-small" x={x + 20} y="28.5">Head {index + 1}</text>
                </g>
              ))}
            </g>
          )}
        </g>
      ))}
      <g className="fpga-measurement-node" data-active={active("cache")}>
        <rect x="133" y="65" width="54" height="20" rx="3" />
        <text x="160" y="75">KV cache</text>
      </g>
      <g className="fpga-measurement-node" data-active={step === 0 || step === 1}>
        <rect x="133" y="110" width="54" height="30" rx="3" />
        <text x="160" y="118.5">Pick token</text>
        <text className="fpga-measurement-small" x="160" y="132.5">{tokenPicker}</text>
      </g>
    </svg>
  );
};

type DetailNode = { x: number; y: number; label: string; width?: number; active?: boolean };

function DetailNodes({ nodes }: { nodes: readonly DetailNode[] }) {
  return nodes.map(({ x, y, label, width = 57, active = true }) => (
    <g key={label + x + y} className="fpga-measurement-node" data-active={active}>
      <rect x={x} y={y} width={width} height="21" rx="3" />
      <text x={x + width / 2} y={y + 10.5}>{label}</text>
    </g>
  ));
}

// Keep the same drawing scale across experiments. Each detail supplies the
// centre of its artwork, including its caption, in its own SVG coordinates.
function DetailView({ cx, cy, children }: { cx: number; cy: number; children: ReactNode }) {
  return (
    <svg x="4" y="80" width="188" height="94" viewBox={`${cx - 100} ${cy - 50} 200 100`}>
      {children}
    </svg>
  );
}

function Handoff({ autonomous }: { autonomous: boolean }) {
  return (
    <DetailView cx={97} cy={59}>
      <rect className="fpga-measurement-weight-array" x="5" y="16" width={autonomous ? 184 : 84} height="71" rx="5" />
      <text x="47" y="29">FPGA</text>
      {!autonomous && <text x="146" y="29">CPU</text>}
      <path className="fpga-measurement-flow" d="M80 53H108M146 63V83H47V63" />
      <path className="fpga-measurement-arrow" data-active="true" d="m103 49 5 4-5 4m-60 11 4-5 4 5" />
      <DetailNodes nodes={[
        { x: 14, y: 42, width: 66, label: "320 scores" },
        { x: 109, y: 42, width: 74, label: "Pick token" },
      ]} />
      <text x="97" y="98">1 token</text>
    </DetailView>
  );
}

function SkipScores() {
  return (
    <DetailView cx={93} cy={66}>
      <path className="fpga-measurement-flow" d="M17 54H169" />
      {[42, 76, 110, 144].map((x, index) => (
        <g key={x} className="fpga-measurement-node" data-active={index === 3}>
          <path className="fpga-measurement-guide" d={`M${x} 60V75`} />
          <circle cx={x} cy="54" r="6" />
          {index === 3 ? <circle cx={x} cy="78" r="4" /> : (
            <path className="fpga-measurement-guide" d={`m${x - 4} 75 8 8m0-8-8 8`} />
          )}
        </g>
      ))}
      <text x="93" y="34">Prompt positions</text>
      <text x="93" y="98">Score only the last token onwards</text>
    </DetailView>
  );
}

const ArithmeticComparison = ({ bitsPerClock }: { bitsPerClock: 2 | 4 }) => (
  <DetailView cx={100} cy={50}>
    <g className="fpga-measurement-comparison">
      <text className="fpga-measurement-comparison-before" x="128" y="18">Before</text>
      <text x="181" y="18">After</text>
      {[
        { label: "Bits per clock", before: 1, after: bitsPerClock, y: 48 },
        { label: "Calculation steps", before: 64, after: 64 / bitsPerClock, y: 78 },
      ].map(({ label, before, after, y }) => (
        <g key={label}>
          <text className="fpga-measurement-comparison-label" x="4" y={y}>{label}</text>
          <text className="fpga-measurement-comparison-value fpga-measurement-comparison-before" x="128" y={y}>{before}</text>
          <text className="fpga-measurement-comparison-before" x="154.5" y={y}>→</text>
          <text className="fpga-measurement-comparison-value fpga-measurement-comparison-after" x="181" y={y}>{after}</text>
        </g>
      ))}
    </g>
  </DetailView>
);

const ReadAheadOverlap = () => (
  <DetailView cx={100} cy={50}>
    <g className="fpga-measurement-read-ahead">
      <text x="17" y="15.5">Before</text>
      <path className="fpga-measurement-guide" d="M114 15.5H121" />
      <path className="fpga-measurement-arrow" d="m118 12.5 3 3-3 3" />
      <text x="17" y="64.5">After</text>
      <DetailNodes nodes={[
        { x: 38, y: 5, width: 76, label: "Multiply + add", active: false },
        { x: 122, y: 5, width: 76, label: "Read next pair", active: false },
        { x: 38, y: 42, width: 76, label: "Multiply + add", active: false },
        { x: 38, y: 66, width: 76, label: "Read next pair", active: false },
      ]} />
      <text x="160" y="64.5">Same cycle</text>
    </g>
  </DetailView>
);

function Overlap() {
  return (
    <DetailView cx={96} cy={62}>
      <text x="84" y="22">One tick</text>
      <text x="153" y="22">Next tick</text>
      <path className="fpga-measurement-guide" d="M51 32V102M118 32V102M186 32V102" />
      <text x="25" y="47">Before</text>
      <text x="25" y="84">After</text>
      <DetailNodes nodes={[
        { x: 55, y: 36, label: "Add", active: false },
        { x: 124, y: 36, label: "Read next", active: false },
        { x: 55, y: 62, label: "Add" },
        { x: 55, y: 84, label: "Read next" },
      ]} />
    </DetailView>
  );
}

function ParallelScores({ count }: { count: number }) {
  return (
    <DetailView cx={90} cy={66}>
      <text x="93" y={71 + (count - 1) * 5}>{count} lanes · {count} scores</text>
      {Array.from({ length: count }, (_, index) => {
        const y = 56 + (index - (count - 1) / 2) * 10;
        return (
          <g key={index} className="fpga-measurement-node" data-active="true">
            <path className="fpga-measurement-flow" d={`M20 56H33V${y}H72M115 ${y}H154`} />
            <rect x="72" y={y - 3.5} width="43" height="7" rx="2" />
            <circle cx="157" cy={y} r="2.5" />
          </g>
        );
      })}
    </DetailView>
  );
}

function FixedDivisor() {
  return (
    <DetailView cx={94} cy={57}>
      <text x="93.5" y="24">Divide by 45,426</text>
      <text className="fpga-measurement-small" x="49" y="46">Leading zeros</text>
      <text className="fpga-measurement-small" x="131" y="46">Remaining steps</text>
      {[23, 44, 65].map((x) => (
        <g key={x} className="fpga-measurement-node">
          <rect x={x} y="54" width="16" height="19" rx="2" />
          <text x={x + 8} y="64">0</text>
        </g>
      ))}
      <path className="fpga-measurement-guide" d="M21 64H83" />
      <path className="fpga-measurement-flow" d="M96 64H165" />
      {[102, 127, 152].map((x) => (
        <g key={x} className="fpga-measurement-node" data-active="true">
          <rect x={x} y="54" width="16" height="19" rx="2" />
        </g>
      ))}
      <text x="49" y="89">Skip</text>
      <text x="135" y="89">Divide as before</text>
    </DetailView>
  );
}

const storedWeights = [
  { column: 0, row: 0, marked: true },
  { column: 1, row: 0, marked: false },
  { column: 2, row: 0, marked: true },
  { column: 0, row: 1, marked: false },
  { column: 1, row: 1, marked: true },
  { column: 2, row: 1, marked: true },
];

function WeightPattern({ filled }: { filled: boolean }) {
  return storedWeights.map(({ column, row, marked }) => (
    <g key={column + 3 * row} className="fpga-measurement-node" data-active={filled && marked}>
      <rect x={17 + column * 16} y={49 + row * 13} width="13" height="10" rx="1.5" />
    </g>
  ));
}

function MemorySwitch() {
  return (
    <DetailView cx={98} cy={61}>
      <text x="40" y="21">New build</text>
      <text x="156" y="21">Earlier build</text>
      <rect className="fpga-measurement-weight-array" x="5" y="30" width="70" height="64" rx="4" />
      <text x="40" y="40">CLB</text>
      <WeightPattern filled={false} />
      <text className="fpga-measurement-small" x="40" y="83">LUTs</text>
      <g transform="translate(116 0)">
        <rect className="fpga-measurement-weight-array" x="5" y="30" width="70" height="49" rx="4" />
        <text x="40" y="40">BRAM</text>
        <WeightPattern filled />
      </g>
      <path className="fpga-measurement-arrow" data-active="true" d="M116 60H81l6-5m-6 5 6 5" />
      <g className="fpga-measurement-moving-weights"><WeightPattern filled /></g>
      <text className="fpga-measurement-small" x="98" y="101">Same weights, same read timing</text>
    </DetailView>
  );
}

function PairExponentials() {
  return (
    <DetailView cx={97} cy={62}>
      <text x="97" y="22">Within one attention head</text>
      <text x="34" y="49">Score 1</text>
      <text x="34" y="78">Score 2</text>
      <path className="fpga-measurement-flow" d="M57 49H74M57 78H74M150 49H163V78H150M163 63H179" />
      <path className="fpga-measurement-arrow" data-active="true" d="m175 59 4 4-4 4" />
      <DetailNodes nodes={[
        { x: 74, y: 38, width: 76, label: "Exponential" },
        { x: 74, y: 67, width: 76, label: "Exponential" },
      ]} />
      <text x="97" y="102">Results in score order</text>
    </DetailView>
  );
}

export function MechanismDetail({ step }: { step: number }) {
  switch (step) {
    case 0:
    case 1: return <Handoff autonomous={step === 1} />;
    case 2: return <SkipScores />;
    case 3: return <ArithmeticComparison bitsPerClock={4} />;
    case 4: return <ArithmeticComparison bitsPerClock={2} />;
    case 5: return <ReadAheadOverlap />;
    case 10:
    case 11: return <Overlap />;
    case 6:
    case 7:
    case 8: return <ParallelScores count={2 ** (step - 5)} />;
    case 9:
    case 12: return <FixedDivisor />;
    case 13: return <MemorySwitch />;
    case 14: return <PairExponentials />;
    default: return null;
  }
}

export function FabricDiagram({ resource, externalMemory = false, children, description }: {
  resource?: Resource | "BRAM + DSP" | "Clock";
  externalMemory?: boolean;
  children: ReactNode;
  description?: string;
}) {
  return (
    <svg viewBox="0 0 196 177" role={description ? "img" : undefined} aria-label={description} aria-hidden={description ? undefined : true}>
      <g transform={`translate(${fabricMapOffsetX} -2) scale(${fabricMapScale})`}>
        <FabricMap resource={resource === "BRAM + DSP" ? "DSP" : resource} />
        {resource === "BRAM + DSP" && <ResourceCallout resource="BRAM" />}
      </g>
      {externalMemory && (
        <g className="fpga-measurement-node" data-active="true">
          <rect x="2" y="30" width="41" height="18" rx="3" />
          <text x="22.5" y="39">DDR4</text>
          <path className="fpga-measurement-flow" d="M43 39H61" />
          <path className="fpga-measurement-arrow" data-active="true" d="m57 36 4 3-4 3" />
        </g>
      )}
      {children}
    </svg>
  );
}

const resourceBars = [
  ["clbs", "CLBs"], ["luts", "LUTs"], ["registers", "Flip-flops"],
  ["dsps", "DSPs"], ["bram", "BRAM"], ["ddr4WeightsKiB", "DDR4"],
] as const;

export function FabricUsageChart({ usage, ddr4WeightsKiB = 0 }: { usage: FabricUsage; ddr4WeightsKiB?: number }) {
  const axisMax = 50;
  return (
    <figure className="fpga-fabric-usage">
      <figcaption>Resources used · DDR4 counts model weights</figcaption>
      <div className="fpga-fabric-usage-plot">
        <div className="fpga-fabric-usage-scale" aria-hidden="true">
          <span>{axisMax}%</span><span>0%</span>
        </div>
        {resourceBars.map(([key, label]) => {
          const external = key === "ddr4WeightsKiB";
          const used = external ? ddr4WeightsKiB : usage[key];
          const capacity = external ? 4 * 1024 ** 2 : fabricCapacity[key];
          const percent = 100 * used / capacity;
          const count = external ? `${used} KiB` : used.toLocaleString("en-GB");
          const reading = external
            ? `Model weights fetched from DDR4 during inference: ${count} of 4 GiB`
            : `${label}: ${count} of ${capacity.toLocaleString("en-GB")} (${percent.toFixed(2)}%)`;
          return (
            <div className="fpga-fabric-usage-column" key={key} title={reading}>
              <div className="fpga-fabric-usage-bar" style={{ height: `${percent / axisMax * 100}%` }} aria-hidden="true">
                <span>{count}</span>
              </div>
              <span className="fpga-fabric-usage-label" aria-hidden="true">{label}</span>
              <span className="fpga-measurement-sr">{reading}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

export function MeasurementMechanism({ step }: { step: number }) {
  const heading = useId();
  const description = useId();
  const activeStep = experiments[step] ? step : 0;
  const experiment = experiments[activeStep];

  return (
    <div className="fpga-measurement-mechanisms">
      <div className="fpga-measurement-panel">
        <div className="fpga-measurement-panel-title">Generating a token</div>
        <ModelDiagram stages={experiment.stages} step={activeStep} />
      </div>
      <div className="fpga-measurement-panel" role="group" aria-labelledby={heading} aria-describedby={description}>
        <div className="fpga-measurement-panel-title" id={heading}>FPGA · {experiment.title}</div>
        <FabricDiagram resource={activeStep === 0 ? undefined : experiment.resource}>
          <g key={activeStep} className="fpga-measurement-detail"><MechanismDetail step={activeStep} /></g>
        </FabricDiagram>
        <span className="fpga-measurement-sr" id={description}>{experiment.description}</span>
      </div>
      <FabricUsageChart usage={measurements[activeStep].resources} />
    </div>
  );
}
