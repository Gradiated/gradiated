import { useContext, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import {
  bramBlock,
  dspBlock,
  hasNeuronReference,
  networkChipCamera,
} from "./ChipContinuation";
import { chipMapChannels, chipMapPositions } from "./ChipMap";
import { Label } from "./drawing";
import { FigureSlot } from "./FigureSlot";
import { useApplicationMotion } from "./ApplicationEnvironments";
import { WorldLayer } from "./WorldLayer";

const exampleOutput = [..."Chips taste so"];
const footerBaseline = 511;
const outputCharacterX = (index: number) => 202.2 + index * 14.4;
const phases = [
  "input",
  "project",
  "cache",
  "attention",
  "feed-forward",
  "scores",
  "output",
] as const;
type Phase = (typeof phases)[number] | "hold";
const predictionBeats = exampleOutput.length * phases.length;
const loopBeats = predictionBeats + 5;

export const networkIntroScenes = [
  "neuron-map",
  "network-layers",
  "network-sum",
  "network-products",
] as const;

const inputX = 144;
const inputs = [348, 369, 390, 411];
const exampleInputs = [348, 390];
const branchX = 266;
const branches = [350, 369, 397, 416];
const outputX = 397;
const outputs = [351, 379, 407];
const selectedY = 369;
const closeScale = 2.75;
const closeCamera = `matrix(${closeScale}, 0, 0, ${closeScale}, ${430 - branchX * closeScale}, ${255 - selectedY * closeScale})`;
const connection = (x: number, y: number, nextX: number, nextY: number) => {
  const length = Math.hypot(nextX - x, nextY - y);
  const dx = (nextX - x) / length;
  const dy = (nextY - y) / length;

  return `M${x + dx * 5.5} ${y + dy * 5.5}L${nextX - dx * 5.5} ${nextY - dy * 5.5}`;
};

const activityOrder = [0, 5, 7, 2, 4, 6, 1, 8, 3];
const LogicActivity = ({
  block,
  fromAbove,
}: {
  block: number;
  fromAbove: boolean;
}) => {
  const column = block % 3;
  const row = Math.floor(block / 3);
  const x = chipMapPositions[column];
  const y = chipMapPositions[row];
  const track = fromAbove ? chipMapChannels[row] : chipMapChannels[column];
  const route = fromAbove
    ? `M${chipMapChannels[column]} ${track}H${x + 36}V${y}`
    : `M${track} ${chipMapChannels[row + 1]}V${y + 36}H${x}`;

  return (
    <g data-resource="logic">
      <path d={route} />
      <rect x={x} y={y} width={72} height={72} rx={5} />
    </g>
  );
};

const ResourceActivity = ({
  resource,
  bounds: { x, y, w, h },
  wireStart,
}: {
  resource: "bram" | "dsp";
  bounds: typeof bramBlock;
  wireStart: number;
}) => (
  <g data-resource={resource}>
    <path d={`M${wireStart} ${y + h / 2}H${x}`} />
    <rect x={x} y={y} width={w} height={h} rx={4} />
  </g>
);

const ChipActivity = ({ beat, phase }: { beat: number; phase: Phase }) => {
  const fromAbove = beat % 2 === 0;
  const showBram = phase === "cache" || (phase === "feed-forward" && fromAbove);
  const showDsp = phase === "attention" || phase === "feed-forward";

  return (
    <g className="fpga-network-chip-activity" aria-hidden="true">
      <LogicActivity
        block={activityOrder[beat % activityOrder.length]}
        fromAbove={fromAbove}
      />
      {phase === "project" && (
        <LogicActivity
          block={activityOrder[(beat + 3) % activityOrder.length]}
          fromAbove={!fromAbove}
        />
      )}
      {showBram && (
        <ResourceActivity resource="bram" bounds={bramBlock} wireStart={460} />
      )}
      {showDsp && (
        <ResourceActivity resource="dsp" bounds={dspBlock} wireStart={468} />
      )}
    </g>
  );
};

const cacheLanes = [
  { label: "K", x: 363, path: "M338 135C338 168 363 177 363 228" },
  { label: "V", x: 414, path: "M361 135C361 168 414 177 414 228" },
] as const;

const Flow = ({
  d,
  active = false,
  dashed = false,
  arrow,
}: {
  d: string;
  active?: boolean;
  dashed?: boolean;
  arrow?: string;
}) => (
  <path
    d={d}
    className="fpga-network-flow"
    data-active={active}
    data-dashed={dashed}
    markerEnd={arrow ? `url(#${arrow})` : undefined}
  />
);

const CacheVector = ({ x = 0, y = 0 }: { x?: number; y?: number }) => (
  <g transform={`translate(${x} ${y})`}>
    <rect x={-13} y={-4} width={26} height={8} rx={2} />
    <path d="M-6 -2v4M0 -2v4M6 -2v4" />
  </g>
);

const Capsule = ({
  x,
  y,
  width,
  active = false,
  children,
  secondLine,
  textOffsetY = 0,
}: {
  x: number;
  y: number;
  width: number;
  active?: boolean;
  children: string;
  secondLine?: string;
  textOffsetY?: number;
}) => {
  const height = secondLine ? 44 : 24;
  const textY = y + textOffsetY;

  return (
    <g className="fpga-network-capsule" data-active={active}>
      <rect
        x={x - width / 2}
        y={y - height / 2}
        width={width}
        height={height}
        rx={height / 2}
      />
      <Label x={x} y={secondLine ? textY - 10 : textY}>
        {children}
      </Label>
      {secondLine && (
        <Label x={x} y={textY + 10}>
          {secondLine}
        </Label>
      )}
    </g>
  );
};

const Overview = ({
  phase,
  input,
  output,
  cacheCount,
  arrow,
  close,
}: {
  phase: Phase;
  input: string;
  output: string[];
  cacheCount: number;
  arrow: string;
  close: boolean;
}) => (
  <g className="fpga-network-overview" aria-hidden={close}>
    <Flow d="M65 118H107M119 118H174M269 118H282" active={phase === "input"} />
    <Flow d="M165 118V34H594V242H592" active={phase === "attention"} dashed />
    <Flow d="M375 31L379 34L375 37M591 127L594 131L597 127" active={phase === "attention"} />
    <Flow d="M575 118H581V231" active={phase === "attention"} />
    <Flow d="M581 253V284H0V379H10" active={phase === "feed-forward"} />
    <Flow d="M0 379V443H444V390" active={phase === "feed-forward"} dashed />
    <Flow
      d="M218 440L222 443L218 446M441 421L444 417L447 421"
      active={phase === "feed-forward"}
    />
    <Flow d="M105 379H118M423 379H433" active={phase === "feed-forward"} />
    <Flow d="M455 379H474M527 395V407" active={phase === "scores"} />
    <Flow d="M527 435V451" active={phase === "output"} />
    <Flow
      d="M457 465H109Q98 465 92 461T75 457H-25V118H4"
      active={phase === "output"}
      dashed
      arrow={arrow}
    />
    <g
      className="fpga-network-output-pointer"
      data-empty={output[0] === "…"}
      style={{
        transform: `translateX(${outputCharacterX(output.length - 1)}px)`,
      }}
    >
      <Flow d="M0 465V488" active={phase === "output"} dashed arrow={arrow} />
      <circle cy={465} r={2.5} className="fpga-network-junction" />
    </g>
    <circle cx={165} cy={118} r={2.5} className="fpga-network-junction" />
    <circle cy={379} r={2.5} className="fpga-network-junction" />

    <Capsule
      x={109}
      y={71}
      width={100}
      secondLine="Embedding"
      textOffsetY={-1.5}
      active={phase === "input"}
    >
      Input
    </Capsule>
    <g className="fpga-network-stage-node" data-active={phase === "input"}>
      <rect x={4} y={103} width={61} height={30} rx={5} />
      <Label x={34.5} y={118} small value>
        {input}
      </Label>
    </g>
    <g className="fpga-network-embedding" data-active={phase === "input"}>
      {[104, 118, 132].map((y) => (
        <circle key={y} cx={113} cy={y} r={5.5} />
      ))}
    </g>
    <Label x={113} y={156} value small>
      32
    </Label>
    <g className="fpga-network-stage-node" data-active={phase === "input"}>
      <rect x={174} y={102} width={95} height={32} rx={5} />
      <Label x={221.5} y={118}>
        Normalise
      </Label>
    </g>

    <rect
      className="fpga-network-frame"
      x={282}
      y={45}
      width={293}
      height={149}
      rx={7}
    />
    <Capsule x={428.5} y={63} width={91} active={phase === "attention"}>
      Attention
    </Capsule>
    <Flow d="M282 118H302" active={phase === "project"} />
    <Flow
      d="M375 118H391V94H410M391 118V142H410"
      active={phase === "attention"}
    />
    <Flow
      d="M493 94H511V118H525M493 142H511V118M564 118H575"
      active={phase === "attention"}
    />
    <circle cx={391} cy={118} r={2.5} className="fpga-network-junction" />
    <circle cx={511} cy={118} r={2.5} className="fpga-network-junction" />
    <g
      className="fpga-network-stage-node"
      data-active={phase === "project" || phase === "cache"}
    >
      <rect x={302} y={101} width={73} height={34} rx={5} />
      <Label x={338.5} y={118} value>
        Q K V
      </Label>
    </g>
    {[94, 142].map((y, index) => (
      <g
        key={y}
        className="fpga-network-stage-node"
        data-active={phase === "attention"}
      >
        <rect x={410} y={y - 15} width={83} height={30} rx={5} />
        <Label x={451.5} y={y}>
          Head {index + 1}
        </Label>
      </g>
    ))}
    <g className="fpga-network-stage-node" data-active={phase === "attention"}>
      <rect x={525} y={103} width={39} height={30} rx={5} />
      <Label x={544.5} y={118} value>
        Wₒ
      </Label>
    </g>
    <g className="fpga-network-stage-node" data-active={phase === "attention"}>
      <circle cx={581} cy={242} r={11} />
      <Label x={581} y={242} value>
        +
      </Label>
    </g>

    <rect
      className="fpga-network-frame"
      x={240}
      y={204}
      width={200}
      height={61}
      rx={6}
    />
    <Flow
      d="M440 237C474 237 493 211 493 194"
      active={phase === "attention"}
      dashed
      arrow={arrow}
    />
    <Capsule x={287} y={223} width={79} active={phase === "cache"}>
      KV cache
    </Capsule>
    <Label x={251} y={251} small anchor="start">
      {cacheCount} {cacheCount === 1 ? "token" : "tokens"}
    </Label>
    {cacheLanes.map(({ label, x, path }) => (
      <g key={label}>
        <Flow d={path} active={phase === "cache"} />
        <Label x={x - 24} y={248} small value>
          {label}
        </Label>
        {[228, 240, 252].map((y, index) => (
          <g
            key={y}
            className="fpga-network-cache-vector"
            data-stored={index < cacheCount}
            data-latest={index === 0 && phase === "attention"}
          >
            <CacheVector x={x} y={y} />
          </g>
        ))}
        {phase === "cache" && !close && (
          <g
            className="fpga-network-cache-vector fpga-network-cache-flight"
            style={{ offsetPath: `path("${path}")` }}
          >
            <CacheVector />
          </g>
        )}
      </g>
    ))}

    <g
      className="fpga-network-stage-node"
      data-active={phase === "feed-forward"}
    >
      <rect x={10} y={363} width={95} height={32} rx={5} />
      <Label x={57.5} y={379}>
        Normalise
      </Label>
    </g>
    <rect
      className="fpga-network-frame"
      x={118}
      y={306}
      width={305}
      height={129}
      rx={7}
    />
    <Capsule x={270.5} y={326} width={126} active={phase === "feed-forward"}>
      Feed-forward
    </Capsule>
    <Flow
      d="M118 379H129V369H138.5M402.5 379H423"
      active={phase === "feed-forward"}
    />
    <g
      className="fpga-network-embedding"
      data-active={phase === "feed-forward"}
    >
      {outputs.map((y) => (
        <circle key={y} cx={outputX} cy={y} r={5.5} />
      ))}
    </g>
    <g
      className="fpga-network-stage-node"
      data-active={phase === "feed-forward"}
    >
      <circle cx={444} cy={379} r={11} />
      <Label x={444} y={379} value>
        +
      </Label>
    </g>

    <g className="fpga-network-stage-node" data-active={phase === "scores"}>
      <rect x={474} y={363} width={106} height={32} rx={5} />
      <Label x={527} y={379}>
        Normalise
      </Label>
    </g>
    <g className="fpga-network-stage-node" data-active={phase === "scores"}>
      <rect x={468} y={407} width={118} height={28} rx={5} />
      <Label x={527} y={421}>
        320 scores
      </Label>
    </g>
    <g className="fpga-network-stage-node" data-active={phase === "output"}>
      <rect x={457} y={451} width={140} height={28} rx={5} />
      <Label x={527} y={465}>
        Pick next token
      </Label>
    </g>
    <Capsule x={141} y={504} width={70} active={phase === "output"}>
      Output
    </Capsule>
    <Label
      x={outputCharacterX(0)}
      y={footerBaseline}
      value
      className="fpga-network-output"
    >
      {output.map((character, index) => {
        const x = outputCharacterX(index);
        return (
          <tspan key={x} x={x}>
            {character}
          </tspan>
        );
      })}
    </Label>
  </g>
);

export const NetworkIntro = ({ scene }: { scene: string }) => {
  const arrow = useId();
  const clip = useId();
  const compact = hasNeuronReference(scene);
  const products = scene === "network-products" || compact;
  const close = scene === "network-sum" || products;
  const activeInput =
    scene === "neuron"
      ? exampleInputs[0]
      : scene === "neuron-next"
        ? exampleInputs[1]
        : undefined;
  const slot = useContext(FigureSlot);
  const active = slot?.active !== false;
  const motion = useApplicationMotion();
  const [beat, setBeat] = useState(0);
  const complete = beat >= predictionBeats;
  const phaseIndex = beat % phases.length;
  const phase = complete ? "hold" : phases[phaseIndex];

  useEffect(() => {
    if (!active || close) return;

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    const start = () => {
      window.clearInterval(timer);
      if (media.matches) {
        setBeat(predictionBeats);
      } else if (motion.running) {
        timer = window.setInterval(
          () => setBeat((value) => (value + 1) % loopBeats),
          420,
        );
      }
    };

    start();
    media.addEventListener("change", start);
    return () => {
      window.clearInterval(timer);
      media.removeEventListener("change", start);
    };
  }, [active, close, motion.running]);
  const prediction = Math.min(
    exampleOutput.length - 1,
    Math.floor(beat / phases.length),
  );
  const count = complete
    ? exampleOutput.length
    : prediction + Number(phase === "output");
  const input =
    prediction === 0
      ? "Start"
      : exampleOutput[prediction - 1].replace(" ", "␣");
  const output = count ? exampleOutput.slice(0, count) : ["…"];
  const cacheCount = complete
    ? exampleOutput.length
    : prediction + Number(phaseIndex > phases.indexOf("cache"));

  return (
    <>
      <div ref={motion.host} />
      {slot?.chipTarget &&
        active &&
        !close &&
        !complete &&
        motion.running &&
        createPortal(
          <ChipActivity key={beat} beat={beat} phase={phase} />,
          slot.chipTarget,
        )}
      <WorldLayer
        className="fpga-network-world"
        title={
          close
            ? "Two-input teaching example of a weighted sum. Inputs 3 and 2 have weights 2 and minus 1. The products 6 and minus 2 add to 4."
            : "An input token selects an embedding of 32 numbers. The model normalises it, prepares Q, K and V for two attention heads, saves the new key and value in the cache, then mixes values from this and earlier tokens. The attention result and the feed-forward result are each added back to their input. After final normalisation the model scores 320 possible tokens. Software picks the token with the highest score, adds it to the output and feeds it back. The animation uses illustrative text."
        }
      >
        <g
          className="fpga-network-intro"
          data-sum={close}
          data-products={products}
          data-compact={compact}
        >
          <defs>
            <marker
              id={arrow}
              viewBox="0 0 8 8"
              refX={7}
              refY={4}
              markerWidth={5}
              markerHeight={5}
              orient="auto"
            >
              <path d="M0 0L8 4L0 8" className="fpga-network-arrow" />
            </marker>
            <clipPath id={clip}>
              <rect x={-35} y={29} width={633} height={501} />
            </clipPath>
          </defs>
          <rect
            x={-40}
            y={24}
            width={640}
            height={157}
            className="fpga-network-reference-backdrop"
          />
          <g className="fpga-network-layout">
            <g clipPath={`url(#${clip})`}>
              <g
                className="fpga-network-camera"
                style={{
                  transform: close ? closeCamera : "matrix(1, 0, 0, 1, 0, 0)",
                }}
              >
                <Overview
                  phase={phase}
                  input={input}
                  output={output}
                  cacheCount={cacheCount}
                  arrow={arrow}
                  close={close}
                />
                <g
                  className="fpga-network-context"
                  data-active={phase === "feed-forward"}
                >
                  {inputs.flatMap((inputY) =>
                    branches.map((branchY) => (
                      <path
                        key={`${inputY}-${branchY}`}
                        d={connection(inputX, inputY, branchX, branchY)}
                        className="fpga-network-edge"
                      />
                    )),
                  )}
                  {branches.flatMap((branchY) =>
                    outputs.map((outputY) => (
                      <path
                        key={`${branchY}-${outputY}`}
                        d={connection(branchX, branchY, outputX, outputY)}
                        className="fpga-network-edge"
                      />
                    )),
                  )}
                </g>
                <g className="fpga-network-selected-paths">
                  {exampleInputs.map((y) => (
                    <path
                      key={y}
                      d={connection(inputX, y, branchX, selectedY)}
                      className="fpga-network-contribution"
                      data-active={
                        activeInput === undefined
                          ? undefined
                          : y === activeInput
                      }
                    />
                  ))}
                  <path
                    d="M271.5 369H295"
                    className="fpga-network-result-path"
                  />
                </g>
                {inputs.map((y) => (
                  <circle
                    key={y}
                    cx={inputX}
                    cy={y}
                    r={5.5}
                    className={`fpga-network-node ${exampleInputs.includes(y) ? "fpga-network-input-node" : "fpga-network-context-node"}`}
                  />
                ))}
                {branches.map((y) => (
                  <circle
                    key={y}
                    cx={branchX}
                    cy={y}
                    r={5.5}
                    className={`fpga-network-node ${y === selectedY ? "fpga-network-selected-node" : "fpga-network-context-node"}`}
                  />
                ))}
              </g>
            </g>
            <g className="fpga-network-close-labels" aria-hidden={!close}>
              <Label x={94} y={145} small>
                Inputs
              </Label>
              <Label x={255} y={145} small>
                Weights
              </Label>
              <Label
                x={94.5}
                y={197.25}
                value
                className="fpga-network-node-value"
              >
                3
              </Label>
              <Label
                x={94.5}
                y={312.75}
                value
                className="fpga-network-node-value"
              >
                2
              </Label>
              <Label x={255} y={198} value>
                × 2
              </Label>
              <Label x={255} y={318} value>
                × (−1)
              </Label>
              <Label x={430} y={255} value className="fpga-network-node-value">
                +
              </Label>
              <Label x={520} y={231} small>
                Sum
              </Label>
              <Label x={520} y={285} value>
                {products ? "4" : "?"}
              </Label>
              <g className="fpga-network-products" aria-hidden={!products}>
                <Label x={357} y={222} value>
                  6
                </Label>
                <Label x={357} y={303} value>
                  −2
                </Label>
              </g>
            </g>
          </g>
          {!compact && (
            <Label
              x={networkChipCamera[0]}
              y={networkChipCamera[1]}
              className="fpga-network-chip-label"
            >
              FPGA
            </Label>
          )}
        </g>
      </WorldLayer>
    </>
  );
};
