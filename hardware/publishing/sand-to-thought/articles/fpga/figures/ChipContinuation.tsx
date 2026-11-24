import { useId, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { Block, Label, SramFeedback, Wire } from "./drawing";
import { ResourceColumnHardBlocks } from "./ResourceColumns";

type Bounds = readonly [number, number, number, number];
type Focus = "chip" | "memory" | "arithmetic" | "circuit" | "system";
type Continuation = {
  focus: Focus;
  detail: boolean;
  expanded: boolean;
  dsp: boolean;
  columns: boolean;
  location?: string;
  title: string;
  externalCpu: boolean;
  world?: boolean;
  camera?: readonly [number, number, number];
};

export const configurationScenes = [
  "configuration-map",
  "configuration-source",
  "configuration-distribute",
  "configuration-luts",
] as const;

export const laterSceneKeys = [
  "network-layers",
  "network-sum",
  "network-products",
  "neuron-hardware",
  "neuron-next",
  "neuron",
  "pins",
  "memory-roles",
  "our-board",
  "board-request",
  "pulse-generator",
  "hardware-description",
  "simulate",
  "synthesis",
  "map-and-route",
  "timing-window",
  "timing-check",
  "configure",
  "running-parameters",
  "token-journey",
  "transformer-cache-map",
  "transformer-cache",
  "chip-choices",
  "built-in-timers",
  "cpu-and-fpga",
] as const;
export const isLaterScene = (scene: string) =>
  (laterSceneKeys as readonly string[]).includes(scene);

export const networkChipCamera = [20, 504, 0.115] as const;
export const bramBlock = { x: 508, y: 124, w: 136, h: 72 };
export const dspBlock = { x: 508, y: 244, w: 136, h: 72 };
const configurationBlock = { x: 508, y: 364, w: 136, h: 72 };
const [chipCentreX, chipCentreY] = [382, 280] as const;
const boardChipCamera = [390, 280, 0.22] as const;
const [boardChipX, boardChipY, boardChipScale] = boardChipCamera;

export const boardConfigurationInput = {
  x: boardChipX +
    (configurationBlock.x + configurationBlock.w / 2 - chipCentreX) * boardChipScale,
  y: boardChipY +
    (configurationBlock.y + configurationBlock.h - chipCentreY) * boardChipScale,
};

export const hasNeuronReference = (scene: string) =>
  scene === "neuron-hardware" || scene === "neuron" || scene === "neuron-next";

const neuronDspScale = 3.3;
const neuronDspCamera = [
  280 - (dspBlock.x + dspBlock.w / 2 - 382) * neuronDspScale,
  352,
  neuronDspScale,
] as const;

const neuronCameras: Record<string, readonly [number, number, number]> = {
  "neuron-hardware": [280, 352, 0.6],
  neuron: neuronDspCamera,
  "neuron-next": neuronDspCamera,
};

const worldCameras: Record<string, readonly [number, number, number]> = {
  "neuron-map": networkChipCamera,
  "network-layers": networkChipCamera,
  "network-sum": networkChipCamera,
  "network-products": networkChipCamera,
  "our-board": boardChipCamera,
  "board-request": boardChipCamera,
  simulate: [280, 190, 0.52],
  "token-journey": [410, 267, 0.34],
  "built-in-timers": [408, 260, 0.34],
};

const details: Record<string, Focus> = {
  "block-ram": "memory",
  "arithmetic-blocks": "arithmetic",
  "arithmetic-accumulate": "arithmetic",
  "arithmetic-save": "arithmetic",
  "arithmetic-next": "arithmetic",
  neuron: "arithmetic",
  "neuron-next": "arithmetic",
  "pulse-generator": "circuit",
  "hardware-description": "circuit",
  synthesis: "circuit",
  "timing-check": "circuit",
  "timing-window": "circuit",
  "transformer-cache": "memory",
};
const overviews: Record<string, string> = {
  "configuration-map":
    "Return to the original nine-CLB chip before revealing more circuitry. The lower source still connects to the centre CLB.",
  "configuration-source":
    "The same chip drawing widens to reveal more built-in circuitry. A configuration block appears, followed by external flash holding a bitstream.",
  "configuration-distribute":
    "A red 0 is loaded into the routing MUX’s SRAM cell, selecting the upper incoming wire. The solid gold path carries data through that connection.",
  "configuration-luts":
    "CLB 1 expands to reveal four simplified LUTs, each containing four SRAM answer bits. They load one bit at a time to implement AND, OR, NOR and NAND. The routing setting remains 0 and its upper data path stays selected.",
  "clock-network":
    "One clock distribution block sends clock edges along curved dotted paths to the flip-flops in all nine CLBs. These paths represent a dedicated on-chip clock network, separate from data routing.",
  "resources-map":
    "The same chip map expands to reveal a dedicated BRAM resource.",
  "arithmetic-map":
    "Return to the map and reveal dedicated DSP arithmetic alongside BRAM.",
  "resources-together":
    "Return from the DSP close-up to the familiar three-by-three CLB map, with BRAM, DSP and configuration circuitry in their established positions.",
  "resource-columns":
    "The same chip expands to reveal repeated columns of CLBs, BRAM and DSP resources. This is a schematic resource pattern, not the exact floor plan or resource count of our KV260. Different resource types have different heights.",
  "neuron-map":
    "Our tiny transformer repeatedly predicts a token. The same FPGA remains in the corner while we explore the model.",
  "network-layers":
    "The main stages of our one-block transformer, with the chosen token fed back to the input.",
  "network-sum":
    "Zoom into one learned weighted sum before mapping its arithmetic onto FPGA resources.",
  "neuron-hardware":
    "BRAM supplies input numbers and weights. CLB control selects each pair for a shared DSP to multiply and accumulate.",
  pins: "An input pin signals a CLB to request numbers from BRAM. The numbers travel from BRAM to the DSP, which updates the running total and sends the result to an output pin.",
  "memory-roles":
    "Configuration settings, working state and BRAM data have different jobs.",
  "map-and-route":
    "The pulse circuit is assigned to CLBs and connected using existing tracks.",
  configure:
    "Configuration circuitry loads settings distributed through the FPGA.",
  "running-parameters":
    "Changing a working width value leaves the configured circuit in place.",
  "transformer-cache-map":
    "Return from the DSP to the FPGA map, with the BRAM that holds our KV cache highlighted.",
  "cpu-and-fpga":
    "CPU software exchanges parameters and results with the same configured FPGA.",
};
const locations: Record<Focus, string> = {
  chip: "Whole FPGA",
  system: "FPGA › Circuit using BRAM, DSP and logic",
  memory: "FPGA › BRAM",
  arithmetic: "FPGA › DSP arithmetic",
  circuit: "FPGA › Circuit using logic and registers",
};
export const continuationBounds: Record<Exclude<Focus, "chip">, Bounds> = {
  memory: [506, 110, 140, 100],
  arithmetic: [506, 230, 140, 100],
  circuit: [112, 112, 336, 240],
  system: [112, 112, 568, (568 * 400) / 560],
};

export const continuationFor = (scene: string): Continuation | undefined => {
  const world = Boolean(worldCameras[scene]);
  const camera = worldCameras[scene] ?? neuronCameras[scene];
  const focus =
    details[scene] ?? (overviews[scene] || world ? "chip" : undefined);
  if (!focus) return undefined;

  return {
    focus,
    ...(world ? { world: true } : {}),
    camera,
    externalCpu: scene === "cpu-and-fpga",
    detail: focus !== "chip",
    expanded: scene !== "configuration-map",
    columns: scene === "resource-columns",
    dsp: ![
      ...configurationScenes,
      "clock-network",
      "resources-map",
      "block-ram",
    ].includes(scene),
    location:
      scene === "neuron-map" ||
      (isLaterScene(scene) && scene !== "pins" && scene !== "memory-roles")
        ? undefined
        : locations[focus],
    title:
      overviews[scene] ?? `${locations[focus]}: enlarged circuit illustration.`,
  };
};

export const continuationTransform = (view: Continuation) => {
  if (view.columns) return "matrix(0.34, 0, 0, 0.34, 41.32, 123.6)";

  if (view.camera) {
    const [x, y, scale] = view.camera;
    return `matrix(${scale}, 0, 0, ${scale}, ${x - scale * chipCentreX}, ${y - scale * chipCentreY})`;
  }

  const bounds =
    view.focus === "chip" ? undefined : continuationBounds[view.focus];
  const x = view.externalCpu
    ? 260
    : bounds
      ? bounds[0] + bounds[2] / 2
      : view.expanded
        ? 382
        : 280;
  const y = bounds ? bounds[1] + bounds[3] / 2 : 280;
  const scale = bounds
    ? 540 / bounds[2]
    : view.externalCpu
      ? 0.65
      : view.expanded
        ? 0.76
        : 1;

  return `matrix(${scale}, 0, 0, ${scale}, ${280 - scale * x}, ${280 - scale * y})`;
};

export const useContinuation = (scene: string) => {
  const [memoryPower, setMemoryPower] = useState(true);
  const [configuration, setConfiguration] = useState({
    power: true,
    loaded: false,
  });
  const [width, setWidth] = useState(4);
  const roles = scene === "memory-roles";
  const loading = scene === "configure";
  const powered = roles ? memoryPower : loading ? configuration.power : true;
  const configured = loading ? powered && configuration.loaded : powered;
  const setPower = (power: boolean) =>
    roles ? setMemoryPower(power) : setConfiguration({ power, loaded: false });
  const setLoaded = (loaded: boolean) =>
    setConfiguration((previous) => ({ ...previous, loaded }));

  return { powered, configured, width, setWidth, setLoaded, setPower };
};
type State = ReturnType<typeof useContinuation>;

const ConfigurationBlock = ({
  active = false,
  columns = false,
}: {
  active?: boolean;
  columns?: boolean;
}) => (
  <g
    className="fpga-configuration-block fpga-column-resource"
    style={{
      transform: `translate(${columns ? 640 : 0}px, ${columns ? 660 : 0}px)`,
    }}
  >
    <Block
      {...configurationBlock}
      label="Configuration"
      kind="config"
      active={active}
    />
  </g>
);

const routingLoadPath = "M508 408Q460 100 240 256";
const lutLoadPath = "M508 392C510 220 496 80 456 80";
const configurationLuts = [
  { rule: "AND", answers: [0, 0, 0, 1] },
  { rule: "OR", answers: [0, 1, 1, 1] },
  { rule: "NOR", answers: [1, 0, 0, 0] },
  { rule: "NAND", answers: [1, 1, 1, 0] },
] as const;

const ConfigurationCell = ({
  x,
  y,
  bit,
  delay = 0,
}: {
  x: number;
  y: number;
  bit: 0 | 1;
  delay?: number;
}) => (
  <g
    transform={`translate(${x} ${y})`}
    className="fpga-loading-cell"
    data-bit={bit}
    style={{ "--fpga-cell-delay": `${delay}ms` } as CSSProperties}
  >
    <rect x={-20} y={-14} width={40} height={28} rx={4} />
    <g transform="translate(-6 0) scale(0.23)">
      <SramFeedback />
    </g>
    {bit === 1 && (
      <Label x={12} y={5} small value className="fpga-loading-initial-value">
        0
      </Label>
    )}
    <Label x={12} y={5} small value className="fpga-loading-value">
      {bit}
    </Label>
  </g>
);

const ConfigurationLutArray = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-configuration-lut-array"
    data-visible={visible}
    aria-hidden={!visible}
  >
    <g className="fpga-configuration-lut-loading">
      <path d={lutLoadPath} className="fpga-distribution-halo" />
      <path d={lutLoadPath} className="fpga-configuration-arc" />
      {configurationLuts.flatMap(({ rule, answers }, column) =>
        answers.map((bit, row) => (
          <g
            key={`${rule}-${row}`}
            className="fpga-loading-target"
            data-bit={bit}
          >
            <circle
              r={4}
              className="fpga-loading-packet fpga-loading-lut-packet"
              style={
                {
                  offsetPath: `path("${lutLoadPath}")`,
                  "--fpga-packet-delay": `${650 + (column * 4 + row) * 110}ms`,
                } as CSSProperties
              }
            />
          </g>
        )),
      )}
    </g>
    <g
      className="fpga-configuration-lut-block"
      style={{
        transform: visible
          ? "matrix(1, 0, 0, 1, 0, 0)"
          : `matrix(${72 / 476}, 0, 0, ${72 / 245}, ${124 + (20 * 72) / 476}, ${124 + (49 * 72) / 245})`,
      }}
    >
      <rect
        x={-20}
        y={-49}
        width={476}
        height={245}
        rx={4}
        className="fpga-lut-array-frame"
      />
      <Label x={218} y={-20} className="fpga-configuration-clb-label">
        CLB 1
      </Label>
      <g className="fpga-configuration-lut-contents">
        {configurationLuts.map(({ rule, answers }, column) => (
          <g key={rule} data-rule={rule}>
            <rect
              x={4 + column * 112}
              y={2}
              width={92}
              height={188}
              rx={4}
              className="fpga-configured-lut"
            />
            <Label x={50 + column * 112} y={24} small>
              LUT
            </Label>
            <Label x={50 + column * 112} y={51} small>
              {rule}
            </Label>
            {answers.map((bit, row) => (
              <ConfigurationCell
                key={row}
                x={50 + column * 112}
                y={80 + row * 30}
                bit={bit}
                delay={1150 + (column * 4 + row) * 110}
              />
            ))}
          </g>
        ))}
      </g>
    </g>
  </g>
);

const ConfigurationLoading = ({
  visible,
  scene,
}: {
  visible: boolean;
  scene: string;
}) => {
  const routing = scene === "configuration-distribute";
  const luts = scene === "configuration-luts";
  const incomingPackets = scene === "configuration-source" ? 6 : 3;

  return (
    <g
      className="fpga-tour-layer fpga-configuration-loading"
      data-visible={visible}
      aria-hidden={!visible}
      data-phase={
        visible ? (routing ? "routing" : luts ? "luts" : "source") : "hidden"
      }
    >
      <Block
        x={490}
        y={-49}
        w={172}
        h={64}
        label="Flash memory"
        detail="Bitstream"
        kind="config"
      />
      <Wire d="M576 15V32H752V400H644" control />
      {Array.from({ length: incomingPackets }, (_, packet) => (
        <circle
          key={packet}
          r={4}
          className="fpga-loading-packet fpga-loading-incoming"
          style={
            {
              offsetPath: 'path("M576 15V32H752V400H644")',
              "--fpga-packet-delay": `${packet * 180}ms`,
            } as CSSProperties
          }
        />
      ))}
      <g
        className="fpga-tour-layer fpga-loading-settings"
        data-visible={routing || luts}
        aria-hidden={!routing && !luts}
      >
        <g className="fpga-loading-routing">
          <g className="fpga-loading-wires">
            <g className="fpga-loading-target" data-bit={0}>
              <path d={routingLoadPath} className="fpga-distribution-halo" />
              <path d={routingLoadPath} className="fpga-configuration-arc" />
              {routing && (
                <circle
                  r={4}
                  className="fpga-loading-packet fpga-loading-write"
                  style={
                    {
                      offsetPath: `path("${routingLoadPath}")`,
                    } as CSSProperties
                  }
                />
              )}
            </g>
          </g>
          <Wire d="M220 242V236" control />
          <ConfigurationCell x={220} y={256} bit={0} delay={950} />
        </g>
      </g>
    </g>
  );
};

export const ClockDistribution = ({ children }: { children?: ReactNode }) => {
  const id = useId();

  return (
    <g className="fpga-clock-distribution">
      <defs>
        <mask
          id={id}
          maskUnits="userSpaceOnUse"
          x={48}
          y={48}
          width={668}
          height={464}
        >
          <rect x={48} y={48} width={668} height={464} fill="white" />
          {[124, 244, 364].flatMap((y) =>
            [124, 244, 364].map((x) => (
              <rect
                key={`${x}-${y}`}
                x={x}
                y={y}
                width={72}
                height={72}
                rx={4}
                fill="black"
              />
            )),
          )}
          {[100, 220, 340, 460].map((x) => (
            <rect
              key={x}
              x={x - 12}
              y={476}
              width={24}
              height={24}
              rx={2}
              fill="black"
            />
          ))}
        </mask>
      </defs>
      <g mask={`url(#${id})`}>
        {[196, 316, 436].flatMap((y, row) =>
          [160, 280, 400].map((x, column) => {
            const d = `M528 494C${490 - column * 12} ${500 - row * 6} ${x} ${y + 100} ${x} ${y}`;

            return (
              <g key={`${x}-${y}`}>
                <path d={d} className="fpga-distribution-halo" />
                <path d={d} className="fpga-clock-arc" />
                <circle
                  r={3}
                  className="fpga-clock-packet"
                  style={{ offsetPath: `path("${d}")` } as CSSProperties}
                />
              </g>
            );
          }),
        )}
      </g>
      {[196, 316, 436].flatMap((y) =>
        [160, 280, 400].map((x) => (
          <path
            key={`${x}-${y}`}
            d={`M${x - 6} ${y}l6 -6 6 6`}
            className="fpga-clock-terminal"
          />
        )),
      )}
      {children ?? (
        <Block x={528} y={480} w={96} h={28} label="Clock" kind="config" />
      )}
      <circle cx={528} cy={494} r={3} className="fpga-clock-origin" />
    </g>
  );
};

const pinSignalWires = [
  { d: "M32 220H60", delay: 650 },
  { d: "M84 220H100V160H124", delay: 920 },
  { d: "M196 160H220V100H452V152H508", delay: 1730 },
  { d: "M508 160H468V280H508", delay: 2540 },
  { d: "M508 280H644", delay: 3200 },
  { d: "M644 280H664V340H680", delay: 3840 },
  { d: "M704 340H732", delay: 4350 },
];

const PinSignalPath = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-tour-layer fpga-pin-route"
    data-visible={visible}
    aria-hidden={!visible}
  >
    {pinSignalWires.map(({ d, delay }) => (
      <g
        key={d}
        style={{ "--pin-signal-delay": `${delay}ms` } as CSSProperties}
      >
        <path d={d} pathLength={1} className="fpga-signal fpga-pin-signal" />
      </g>
    ))}
    {[
      { x: 124, y: 124, width: 72, delay: 1550 },
      { x: 508, y: 124, width: 136, delay: 2350 },
      { x: 508, y: 244, width: 136, delay: 3200 },
    ].map(({ x, y, width, delay }) => (
      <rect
        key={`${x}-${y}`}
        x={x}
        y={y}
        width={width}
        height={72}
        rx={4}
        className="fpga-pin-signal-block"
        style={{ "--pin-signal-delay": `${delay}ms` } as CSSProperties}
      />
    ))}
    <Label x={18} y={198}>
      Input
    </Label>
    <Label x={746} y={318}>
      Output
    </Label>
  </g>
);

export const ContinuationContents = ({
  scene,
  state,
}: {
  scene: string;
  state: State;
}) => {
  const view = continuationFor(scene);
  if (!view) return null;

  const roles = scene === "memory-roles";
  const loadingOverview = (configurationScenes as readonly string[]).includes(
    scene,
  );
  const configuration = scene === "configure";
  const memory = !loadingOverview && scene !== "clock-network";
  const showBramWires = !view.columns && scene !== "transformer-cache";
  const clock = scene === "clock-network";
  const cpu = scene === "cpu-and-fpga";
  const pulse = ["map-and-route", "running-parameters"].includes(scene);
  const selected = roles || configuration || pulse || cpu;

  return (
    <g
      className="fpga-continuation-map"
      data-powered={state.powered}
      data-columns={view.columns}
    >
      <g
        className="fpga-tour-layer"
        data-visible={memory}
        aria-hidden={!memory}
      >
        <g
          className="fpga-column-resource"
          style={{ transform: `translateY(${view.columns ? 60 : 0}px)` }}
        >
          <g
            className="fpga-tour-layer"
            data-visible={showBramWires}
            aria-hidden={!showBramWires}
          >
            {[-8, 0, 8].map((offset, index) => (
              <Wire
                key={offset}
                d={`M${452 + index * 8} ${160 + offset}H508M644 ${160 + offset}H674`}
                faint
              />
            ))}
          </g>
          <Block
            {...bramBlock}
            h={view.columns ? 260 : bramBlock.h}
            label="BRAM"
            kind="memory"
            detail={
              roles ? (state.powered ? "Working data" : "Lost") : undefined
            }
            active={
              view.focus === "memory" ||
              roles ||
              scene === "neuron-hardware" ||
              scene === "transformer-cache-map"
            }
          />
        </g>
        <g
          className="fpga-tour-layer"
          data-visible={view.dsp}
          aria-hidden={!view.dsp}
        >
          <g
            className="fpga-column-resource"
            style={{
              transform: `translate(${view.columns ? 192 : 0}px, ${view.columns ? 90 : 0}px)`,
            }}
          >
            <g
              className="fpga-tour-layer"
              data-visible={!view.columns}
              aria-hidden={view.columns}
            >
              <Wire d="M468 280H508M644 280H684" faint />
            </g>
            <Block
              {...dspBlock}
              h={view.columns ? 112 : dspBlock.h}
              label="DSP"
              detail="Multiply + add"
              kind="arithmetic"
              active={
                view.focus === "arithmetic" || scene === "neuron-hardware"
              }
            />
          </g>
        </g>
      </g>
      <g
        className="fpga-tour-layer fpga-configuration-reveal"
        data-visible={!view.detail && view.expanded}
        aria-hidden={view.detail || !view.expanded}
      >
        <ConfigurationBlock
          columns={view.columns}
          active={
            (loadingOverview || configuration || roles) && state.configured
          }
        />
      </g>
      <ResourceColumnHardBlocks visible={view.columns} />
      <ConfigurationLoading
        visible={loadingOverview && view.expanded}
        scene={scene}
      />
      <ConfigurationLutArray visible={scene === "configuration-luts"} />
      <g className="fpga-tour-layer" data-visible={clock} aria-hidden={!clock}>
        <ClockDistribution />
      </g>
      <g
        className="fpga-tour-layer fpga-chip-config-cells"
        data-visible={selected}
        aria-hidden={!selected}
      >
        {[124, 244, 364].flatMap((x) =>
          [124, 244, 364].map((y) => (
            <rect
              key={`${x}-${y}`}
              x={x + 8}
              y={y + 61}
              width={8}
              height={6}
              className={state.configured ? "is-loaded" : ""}
            />
          )),
        )}
      </g>
      <g className="fpga-tour-layer" data-visible={pulse} aria-hidden={!pulse}>
        <Wire
          d="M196 160H220V280H244M316 280H340V400H364M436 400H460V460H680M704 460H732"
          active
        />
        {scene === "running-parameters" && (
          <Label x={382} y={552} small>
            Width = {state.width}
          </Label>
        )}
      </g>
      <g
        className="fpga-tour-layer"
        data-visible={scene === "built-in-timers"}
        aria-hidden={scene !== "built-in-timers"}
      >
        <Wire
          d="M196 160H220V280H244M316 280H340V400H364M436 400H460V460H680M704 460H732"
          active
        />
      </g>
      <g
        className="fpga-tour-layer"
        data-visible={scene === "neuron-hardware"}
        aria-hidden={scene !== "neuron-hardware"}
      >
        <Wire d="M316 160H340V100H452V152H508" control active />
        <Wire d="M508 168H468V280H508" active bus={{ x: 468, y: 220 }} />
        <rect
          x={244}
          y={124}
          width={72}
          height={72}
          rx={4}
          className="fpga-token-resource"
        />
      </g>
      <PinSignalPath visible={scene === "pins"} />
      <g
        className="fpga-tour-layer"
        data-visible={roles || configuration}
        aria-hidden={!roles && !configuration}
      >
        <Block
          x={490}
          y={-49}
          w={172}
          h={64}
          label={roles ? "Board flash" : "Flash or host"}
          detail="Bitstream"
          kind="config"
        />
        <Wire d="M576 15V32H752V400H644" control active={state.configured} />
        <Wire
          d="M508 400H484V208H144M484 328H400"
          control
          active={state.configured}
        />
        <Label x={382} y={552} small>
          {roles
            ? state.powered
              ? "Settings: rule + route · flip-flops: state · BRAM: data"
              : "Power off · active settings and working state lost · flash retained"
            : state.configured
              ? "Settings loaded"
              : "Waiting for configuration"}
        </Label>
      </g>
      <g className="fpga-tour-layer" data-visible={cpu} aria-hidden={!cpu}>
        <Block x={-180} y={200} w={150} h={100} label="CPU" />
        <Wire d="M-30 235H8V220H60M60 340H8V275H-30" active />
        <Label x={-105} y={178} small>
          Scores / chosen token
        </Label>
        <Wire
          d="M84 220H108V160H124M196 160H220V280H244M244 300H220V340H84"
          active
        />
      </g>
    </g>
  );
};

export const ContinuationControls = ({
  scene,
  state,
}: {
  scene: string;
  state: State;
}) => {
  if (!["memory-roles", "configure", "running-parameters"].includes(scene))
    return null;

  return (
    <div
      className="fpga-controls"
      role="group"
      aria-label="Configuration and working data"
    >
      {scene === "running-parameters" ? (
        [4, 12].map((width) => (
          <button
            type="button"
            key={width}
            aria-pressed={state.width === width}
            onClick={() => state.setWidth(width)}
          >
            Write width {width}
          </button>
        ))
      ) : (
        <>
          <button
            type="button"
            onClick={() => {
              state.setPower(!state.powered);
              state.setLoaded(false);
            }}
          >
            {state.powered ? "Power off" : "Power on"}
          </button>
          {scene === "configure" && (
            <button
              type="button"
              disabled={!state.powered || state.configured}
              onClick={() => state.setLoaded(true)}
            >
              Load bitstream
            </button>
          )}
        </>
      )}
      <span className="sr-only" role="status">
        {scene === "running-parameters"
          ? `Working width ${state.width}; configuration unchanged.`
          : state.powered
            ? state.configured
              ? "Configured."
              : "Awaiting configuration."
            : "Power off; flash retained."}
      </span>
    </div>
  );
};
