import { useContext, useEffect, useState } from "react";
import { useApplicationMotion } from "./ApplicationEnvironments";
import { FigureSlot } from "./FigureSlot";
import { Block, Figure, Label, Transfer, Wire } from "./drawing";
import { WorldLayer } from "./WorldLayer";
import { textRequest } from "./transformerModel";

const tokenReply = textRequest.output
  .replace(/^Resist\b/, "Photoresist")
  .replace(/\.$/, "");
const [firstToken, secondToken] = tokenReply;
const tokenBeats = [
  { activity: "prompt", outputLength: 0, duration: 1000 },
  { activity: "scores", outputLength: 0, duration: 1200 },
  { activity: "choose", outputLength: 0, duration: 650, choice: firstToken },
  { activity: "feedback", outputLength: 1, duration: 750 },
  { activity: "scores", outputLength: 1, duration: 750 },
  { activity: "choose", outputLength: 1, duration: 650, choice: secondToken },
  { activity: "feedback", outputLength: 2, duration: 750 },
  ...Array.from(tokenReply.slice(2), (_, index) => ({
    activity: "repeat" as const,
    outputLength: index + 3,
    duration: 48,
  })),
  {
    activity: "complete",
    outputLength: tokenReply.length,
    duration: 3200,
  },
] as const;
const promptPath = "M100 195V222";
const scoresPath = "M296 247H185";
const feedbackPath = "M185 287H296";
const outputPath = "M100 312V370";

const TokenFigure = () => {
  const slot = useContext(FigureSlot);
  const motion = useApplicationMotion();
  const [step, setStep] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const playing = slot?.active !== false && motion.running && !reducedMotion;
  const beat = tokenBeats[reducedMotion ? tokenBeats.length - 1 : step];
  const { activity, outputLength, duration } = beat;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);

    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!playing) return;

    const timer = window.setTimeout(
      () => setStep((step + 1) % tokenBeats.length),
      duration,
    );
    return () => window.clearTimeout(timer);
  }, [playing, step, duration]);

  const prompting = activity === "prompt";
  const scoring = activity === "scores";
  const choosing = activity === "choose";
  const feedingBack = activity === "feedback";
  const repeating = activity === "repeat";
  const output = tokenReply.slice(0, outputLength);

  return (
    <>
      <WorldLayer
        className="fpga-token-feedback"
        title={`Illustrated token feedback for the prompt “${textRequest.input}”, with an edited software reply. The CPU receives the prompt, then the FPGA sends back scores. The CPU adds the chosen token to the output and sends it back through the model. The completed output reads “${tokenReply}”`}
      >
        <g className="fpga-world-equipment">
          <rect x={-12} y={148} width={559} height={210} rx={8} />
        </g>
        <Label x={410} y={172}>
          FPGA
        </Label>
        <Label x={100} y={184}>
          Prompt “{textRequest.input}”
        </Label>
        <Wire d={`${promptPath}m-5 -9l5 9 5 -9`} active={prompting} />
        <Wire d={scoresPath} active={scoring} />
        <Wire d={feedbackPath} active={feedingBack} />
        <Wire d={outputPath} active={choosing} />
        <path
          d="M195 241L185 247L195 253M286 281L296 287L286 293M94 360L100 370L106 360"
          className="fpga-wire"
        />
        <g data-paused={!playing}>
          {repeating && (
            <g className="fpga-token-burst" aria-hidden="true">
              <path d={`${scoresPath}m10 -6l-10 6 10 6`} className="fpga-signal" />
              <path d={`${outputPath}m-6 -10l6 10 6 -10`} className="fpga-signal" />
              <path d={`${feedbackPath}m-10 -6l10 6 -10 6`} className="fpga-signal" />
            </g>
          )}
          <Transfer d={promptPath} trigger={prompting ? step + 1 : 0} />
          <Transfer d={scoresPath} trigger={scoring ? step + 1 : 0} />
          <Transfer d={feedbackPath} trigger={feedingBack ? step + 1 : 0} />
          <Transfer d={outputPath} trigger={choosing ? step + 1 : 0} />
        </g>
        <Label x={241} y={228} small>
          Scores
        </Label>
        <Label x={241} y={312} small>
          Next token
        </Label>
        <Block
          x={15}
          y={222}
          w={170}
          h={90}
          label="CPU"
          detail={
            "choice" in beat ? `Chooses ${beat.choice}` : "Picks top score"
          }
          active={choosing}
        />
        <g className="fpga-block fpga-block--logic">
          <rect x={-12} y={370} width={559} height={162} rx={4} />
          <Label x={267.5} y={399}>
            Output
          </Label>
          <foreignObject x={8} y={409} width={519} height={120}>
            <div className="fpga-token-output">
              {output}
              <span aria-hidden="true">{tokenReply.slice(outputLength)}</span>
            </div>
          </foreignObject>
        </g>
      </WorldLayer>
      <div ref={motion.host} />
    </>
  );
};

type CacheBeat = {
  activity:
    | "ready"
    | "write"
    | "saved"
    | "compare"
    | "weights"
    | "mix"
    | "output"
    | "result";
  stored: number;
  row?: number;
  duration?: number;
};

const cacheBeats: readonly CacheBeat[] = [
  { activity: "ready", stored: 2, duration: 1050 },
  { activity: "write", stored: 2, row: 2, duration: 850 },
  { activity: "saved", stored: 3, row: 2, duration: 450 },
  { activity: "write", stored: 3, row: 3, duration: 850 },
  { activity: "saved", stored: 4, row: 3, duration: 500 },
  { activity: "compare", stored: 4, row: 0, duration: 750 },
  { activity: "compare", stored: 4, row: 1, duration: 750 },
  { activity: "compare", stored: 4, row: 2, duration: 750 },
  { activity: "compare", stored: 4, row: 3, duration: 750 },
  { activity: "weights", stored: 4, duration: 650 },
  { activity: "mix", stored: 4, duration: 850 },
  { activity: "output", stored: 4, duration: 560 },
  { activity: "result", stored: 4 },
];

const cacheY = [186, 228, 270, 312];
const cacheWriteBox = { x: 28, y: 34, width: 120, height: 54 };
const cacheQueryBox = { x: 220, y: 34, w: 157, h: 54 };
const cacheCompareBox = { x: 407, y: 34, w: 180, h: 54 };
const cacheMixBox = { x: 293, y: 366, w: 182, h: 54 };
const cacheResultBox = { x: 125, y: 366, w: 136, h: 54 };
const cacheWriteX = cacheWriteBox.x + cacheWriteBox.width / 2;
const cacheWriteBottom = cacheWriteBox.y + cacheWriteBox.height;
const cacheWritePath = (y: number) =>
  `M${cacheWriteX} ${cacheWriteBottom}V${y}H160`;
const cacheKeyBranch = (y: number) => `M299 ${y}H311`;
const cacheKeyRoute = "V140H483V88";
const cacheValueBranch = (y: number) => `M418 ${y}H470`;
const cacheValueRoute = "V350H344V366";
const cacheQueryPath = "M377 61H407";
const cacheWeightsPath = "M555 88V359H424V366";
const cacheOutputY = cacheMixBox.y + cacheMixBox.h / 2;
const cacheOutputEnd = cacheResultBox.x + cacheResultBox.w;
const cacheOutputPath = `M${cacheMixBox.x} ${cacheOutputY}H${cacheOutputEnd}`;
const cacheOutputArrow = `M${cacheOutputEnd + 5} ${cacheOutputY - 4}l-5 4 5 4`;

const cachePrediction = textRequest.predictions[1];
const cacheQuery = cachePrediction.vectors.qrot.slice(0, 16);
const cacheResult = cachePrediction.vectors.context.slice(0, 16);

const CacheCells = ({
  x,
  y,
  numbers,
  filled,
  emphasis,
}: {
  x: number;
  y: number;
  numbers: readonly number[];
  filled: boolean;
  emphasis?: "pair" | "head";
}) => (
  <g
    className="fpga-cache-cells"
    data-filled={filled}
    transform={`translate(${x} ${y - 17})`}
  >
    {Array.from({ length: numbers.length / 16 }, (_, head) => (
      <g
        key={head}
        data-emphasised={
          emphasis === "pair" || (emphasis === "head" && head === 0)
        }
        transform={`translate(${head * 43} 0)`}
      >
        <rect
          x={-4}
          y={-4}
          width={42}
          height={42}
          rx={4}
          className="fpga-cache-grid-focus"
        />
        {numbers.slice(head * 16, (head + 1) * 16).map((number, index) => (
          <rect
            key={index}
            x={(index % 4) * 9}
            y={Math.floor(index / 4) * 9}
            width={7}
            height={7}
            rx={1}
            className="fpga-cache-cell"
            data-sign={filled ? Math.sign(number) : undefined}
          />
        ))}
      </g>
    ))}
  </g>
);

const CacheVectorBlock = ({
  x,
  y,
  w,
  h,
  label,
  numbers,
  filled,
  active,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  numbers: readonly number[];
  filled: boolean;
  active: boolean;
}) => (
  <g className={`fpga-block fpga-block--logic ${active ? "is-selected" : ""}`}>
    <rect x={x} y={y} width={w} height={h} rx={4} />
    <Label x={x + (w - 48) / 2} y={y + h / 2 + 8}>
      {label}
    </Label>
    <CacheCells
      x={x + w - 48}
      y={y + h / 2}
      numbers={numbers}
      filled={filled}
      emphasis={active ? "head" : undefined}
    />
  </g>
);

const cacheRainLanes = [-20, 10, 0, -10, 20];

const CacheWriteRain = () => (
  <g className="fpga-cache-rain" aria-hidden="true">
    {Array.from({ length: cacheRainLanes.length * 3 }, (_, index) => {
      const size = 5 + (index % 3);
      const lane = cacheRainLanes[index % cacheRainLanes.length];

      return (
        <rect
          key={index}
          x={cacheWriteX + lane - size / 2}
          y={cacheWriteBox.y - 22 - size}
          width={size}
          height={size}
          rx={0.8}
          className="fpga-cache-cell"
          data-sign={index % 2 === 0 ? 1 : -1}
          style={{
            animationDelay: `${index * 28}ms`,
            animationDuration: `${420 + (index % 4) * 20}ms`,
          }}
        />
      );
    })}
  </g>
);

const CacheFigure = () => {
  const slot = useContext(FigureSlot);
  const active = slot?.active !== false;
  const motion = useApplicationMotion();
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const { activity, stored, row, duration } = cacheBeats[step];

  useEffect(() => {
    if (!active || !motion.running || paused || duration === undefined) return;

    const timer = window.setTimeout(() => setStep(step + 1), duration);
    return () => window.clearTimeout(timer);
  }, [active, motion.running, paused, step, duration]);

  const writing = activity === "write";
  const comparing = activity === "compare";
  const sendingWeights = activity === "weights";
  const mixing = activity === "mix";
  const weightsPathActive = sendingWeights || mixing;
  const delivering = activity === "output";
  const complete = activity === "result";
  const showValuePaths = mixing || delivering || complete;
  const keyReadY = comparing && row !== undefined ? cacheY[row] : undefined;
  const keyPath =
    keyReadY === undefined ? "" : cacheKeyBranch(keyReadY) + cacheKeyRoute;
  const incoming = step < 3 ? 3 : 4;
  const writeY = cacheY[incoming - 1];
  const writePath = cacheWritePath(writeY);
  const description = writing
    ? `Write token ${incoming}’s key and value to its row.`
    : comparing && row !== undefined
      ? `The first attention head compares token 4’s query with key ${row + 1}.`
      : complete
        ? "The first attention head’s sixteen result numbers are ready."
        : sendingWeights
          ? "The weights derived from the key comparisons travel to Mix values."
          : showValuePaths
            ? "The first attention head mixes all four values using the weights from the key comparisons."
            : `The cache holds a key and value for each of the first ${stored} tokens.`;

  return (
    <>
      <div ref={motion.host} />
      <Figure
        title={`KV cache in BRAM. The surrounding FPGA logic compares keys and mixes values outside the memory. Each key and value has two groups of sixteen numbers. ${description}`}
        viewBox="0 0 600 432"
      >
        <g
          className="fpga-cache-demo"
          data-stored={stored}
          data-activity={activity}
          data-paused={paused || !active || !motion.running}
        >
          <path
            className="fpga-cache-rails"
            d="M12 52H598M12 70H598M12 384H598M12 402H598"
            aria-hidden="true"
          />
          <g className="fpga-block fpga-block--memory">
            <rect x={146} y={103} width={308} height={237} rx={6} />
            <Label x={300} y={130}>
              KV cache in BRAM
            </Label>
          </g>
          <Label x={183} y={161} small className="fpga-cache-compact-label">
            Token
          </Label>
          <Label x={258.5} y={161} small>
            Key
          </Label>
          <Label x={377.5} y={161} small>
            Value
          </Label>
          <g className="fpga-cache-key-route">
            <Wire
              d={`M311 ${cacheY[cacheY.length - 1]}${cacheKeyRoute}`}
              faint
            />
            {cacheY.map((y) => (
              <Wire key={y} d={cacheKeyBranch(y)} faint />
            ))}
            {keyPath && (
              <>
                <Wire d={keyPath} active />
                <Transfer d={keyPath} trigger={step} />
              </>
            )}
          </g>
          <g className="fpga-cache-value-flow">
            <Wire
              d={`M470 ${cacheY[0]}${cacheValueRoute}`}
              faint={!showValuePaths}
              active={showValuePaths}
            />
            {cacheY.map((y) => (
              <g key={y}>
                <Wire
                  d={cacheValueBranch(y)}
                  faint={!showValuePaths}
                  active={showValuePaths}
                />
                {mixing && (
                  <Transfer
                    d={cacheValueBranch(y) + cacheValueRoute}
                    trigger={step}
                  />
                )}
              </g>
            ))}
          </g>
          {(writing || activity === "saved") && (
            <Wire
              d={`${writePath}M156 ${writeY - 4}L160 ${writeY}L156 ${writeY + 4}`}
              active={writing}
              faint={!writing}
            />
          )}
          {writing && <Transfer d={writePath} trigger={step} />}
          {textRequest.cacheRows.map(({ key, value }, index) => {
            const y = cacheY[index];
            const filled = index < stored;
            const savingRow =
              (writing || activity === "saved") && row === index;
            const selectedKey = comparing && row === index;

            return (
              <g key={index} className="fpga-cache-pair" data-filled={filled}>
                <rect
                  x={160}
                  y={y - 21}
                  width={280}
                  height={42}
                  rx={5}
                  className="fpga-cache-row-outline"
                  data-highlighted={savingRow}
                />
                <Label x={183} y={y + 7} small value>
                  {index + 1}
                </Label>
                <CacheCells
                  x={220}
                  y={y}
                  numbers={key}
                  filled={filled}
                  emphasis={
                    savingRow ? "pair" : selectedKey ? "head" : undefined
                  }
                />
                <CacheCells
                  x={339}
                  y={y}
                  numbers={value}
                  filled={filled}
                  emphasis={savingRow ? "pair" : mixing ? "head" : undefined}
                />
              </g>
            );
          })}
          <Wire d={cacheQueryPath} active={comparing} faint={!comparing} />
          <Transfer
            d={cacheQueryPath}
            trigger={comparing && row === 0 ? step : 0}
          />
          <Wire
            d={cacheWeightsPath}
            active={weightsPathActive}
            faint={!weightsPathActive}
          />
          <Transfer d={cacheWeightsPath} trigger={sendingWeights ? step : 0} />
          <Wire
            d={cacheOutputPath + cacheOutputArrow}
            active={delivering}
            faint={!delivering}
          />
          <Transfer d={cacheOutputPath} trigger={delivering ? step : 0} />
          {writing && <CacheWriteRain />}
          <g className="fpga-cache-logic">
            <Label x={404} y={23} small className="fpga-cache-logic-label">
              FPGA logic
            </Label>
            <g className={`fpga-block ${writing ? "is-selected" : ""}`}>
              <rect {...cacheWriteBox} rx={4} />
              <Label x={cacheWriteX} y={cacheWriteBox.y + 34} small>
                New K &amp; V
              </Label>
            </g>
            <CacheVectorBlock
              {...cacheQueryBox}
              label="Query"
              numbers={cacheQuery}
              filled={stored === 4}
              active={comparing}
            />
            <Block
              {...cacheCompareBox}
              label="Compare keys"
              active={comparing || sendingWeights}
            />
            <Block {...cacheMixBox} label="Mix values" active={mixing} />
            <CacheVectorBlock
              {...cacheResultBox}
              label="Result"
              numbers={cacheResult}
              filled={complete}
              active={complete}
            />
          </g>
        </g>
      </Figure>
      <div className="fpga-controls">
        <div
          className="fpga-cache-sign-key"
          role="img"
          aria-label="Filled cells use green for positive numbers, red for negative numbers and grey for zero"
        >
          {([
            [1, "Positive"],
            [-1, "Negative"],
            [0, "Zero"],
          ] as const).map(([sign, label]) => (
            <span key={sign}>
              <svg
                className="fpga-cache-cells"
                width={10}
                height={10}
                aria-hidden="true"
              >
                <rect
                  className="fpga-cache-cell"
                  data-sign={sign}
                  width={10}
                  height={10}
                  rx={1}
                />
              </svg>
              {label}
            </span>
          ))}
        </div>
        {!complete && (
          <button type="button" onClick={() => setPaused(!paused)}>
            {paused ? "Resume" : "Pause"}
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setPaused(false);
            setStep(0);
          }}
        >
          Replay KV cache
        </button>
      </div>
    </>
  );
};

export const TransformerFigure = ({ scene }: { scene: string }) =>
  scene === "transformer-cache" ? <CacheFigure /> : <TokenFigure />;
