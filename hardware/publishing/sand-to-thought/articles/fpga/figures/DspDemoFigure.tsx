import { useContext, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { FigureSlot } from "./FigureSlot";
import { useApplicationMotion } from "./ApplicationEnvironments";
import { DspDatapath } from "./DspDatapath";
import type { DspFlows } from "./DspDatapath";
import { Figure, Label } from "./drawing";

const timelines = {
  "arithmetic-blocks": [900],
  "arithmetic-accumulate": [750, 1400],
  "arithmetic-save": [900, 1200],
  "arithmetic-next": [900, 1700, 2600, 3500, 3800],
} as const;

type DemoScene = keyof typeof timelines;

const feedbackInputY = 240;
const waitingResultX = 389;
const timing = {
  input: { duration: 800 },
  product: { duration: 600 },
  pendingSum: { duration: 500 },
  clock: { duration: 600, delay: 300 },
  capture: { duration: 300, delay: 600 },
  feedback: { duration: 1100 },
};

const NumberTile = ({
  value,
  x = 0,
  y = 0,
}: {
  value: number;
  x?: number;
  y?: number;
}) => (
  <g transform={`translate(${x} ${y})`} className="fpga-dsp-number">
    <circle r={Math.abs(value) >= 10 ? 17 : 16} />
    <Label x={0} y={0} value>
      {value}
    </Label>
  </g>
);

const MovingNumber = ({
  value,
  path,
  duration = 800,
  delay = 0,
  holdAtEnd = false,
  onArrival,
}: {
  value: number;
  path: string;
  duration?: number;
  delay?: number;
  holdAtEnd?: boolean;
  onArrival?: () => void;
}) => (
  <g
    className="fpga-dsp-moving-number"
    data-hold={holdAtEnd || undefined}
    onAnimationEnd={onArrival}
    style={
      {
        offsetPath: `path("${path}")`,
        animationDuration: `${duration}ms`,
        animationDelay: `${delay}ms`,
      } as CSSProperties
    }
  >
    <NumberTile value={value} />
  </g>
);

export const DspDemoFigure = ({ scene }: { scene: DemoScene }) => {
  const active = useContext(FigureSlot)?.active !== false;
  const motion = useApplicationMotion();
  const [beat, setBeat] = useState(0);
  const [reduced, setReduced] = useState(false);
  const timeline = timelines[scene];
  const accumulating = scene !== "arithmetic-blocks";
  const firstAccumulation = scene === "arithmetic-accumulate";
  const saving = scene === "arithmetic-save";
  const repeating = scene === "arithmetic-next";
  const captures = saving || repeating;
  const finalBeat = captures ? timeline.length + 1 : timeline.length;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);

    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!active) return;

    setBeat(reduced ? finalBeat : 0);
    if (!motion.running || reduced) return;

    const timers = timeline.map((time, i) =>
      window.setTimeout(() => setBeat(i + 1), time),
    );

    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [active, finalBeat, motion.running, reduced, timeline]);

  const total = saving
    ? beat >= 1
      ? 6
      : 0
    : repeating
      ? beat >= 4
        ? 10
        : 6
      : 0;
  const clock = saving ? beat === 0 : repeating && beat === 3;
  const inputs = !saving && !firstAccumulation && beat === 0;
  const product = firstAccumulation ? beat === 0 : repeating && beat === 1;
  const directProduct = !accumulating && beat > 0;
  const pendingSum = firstAccumulation && beat === 1;
  const feedback = (saving && beat === 2) || (repeating && beat === 5);
  const finished = captures && beat === finalBeat;
  const adderInput = finished ? total : repeating ? 6 : 0;
  const result = saving
    ? beat === 0
      ? 6
      : null
    : repeating
      ? beat === 2 || beat === 3
        ? 10
        : null
      : firstAccumulation && beat === timeline.length
        ? 6
        : null;
  const animate = motion.running && !reduced;
  const clockTriggered =
    animate && ((saving && beat === 1) || (repeating && beat === 4));
  const flows: DspFlows = animate
    ? {
        inputs: inputs ? timing.input : undefined,
        product: product || directProduct ? timing.product : undefined,
        sum: clock
          ? timing.capture
          : pendingSum
            ? timing.pendingSum
            : undefined,
        feedback: feedback ? timing.feedback : undefined,
        clock: clock ? timing.clock : undefined,
      }
    : {};
  const productReady = saving || (repeating ? beat >= 2 : beat >= 1);
  const captured = (saving && beat >= 1) || (repeating && beat >= 4);
  const equation = captured
    ? `Total = ${total}`
    : repeating
      ? "6 + 4 = 10"
      : "0 + 6 = 6";
  const title = repeating
    ? "The register starts with the previous total, 6. New inputs 2 and 2 produce 4. The saved 6 is already at the adder’s lower input, ready for the adder to prepare 6 + 4 = 10. The register holds 6 until the clock edge captures 10, which then travels back to the adder."
    : saving
      ? "The adder's next total, 6, waits outside a register holding 0. A clock pulse captures 6. Its output connects back to the adder through the lower wire, and the register holds 6 for the next calculation."
      : accumulating
        ? "The multiplier prepares 3 times 2, or 6. The initial total, 0, is already at the adder’s lower input. The adder prepares 0 + 6 = 6. The saved total remains 0 until a clock edge captures the new value."
        : "Two input numbers, 3 and 2, arrive at the dedicated multiplier. Their product, 6, travels along its output bus. The circuitry stays in place as the numbers move.";

  return (
    <div ref={motion.host}>
      <Figure title={title}>
        <g
          className="fpga-resource-circuit fpga-dsp-demo"
          data-scene={scene}
          data-beat={beat}
          data-total={total}
          data-finished={finished}
        >
          <DspDatapath
            input={repeating ? 2 : 3}
            weight={2}
            total={total}
            accumulate={accumulating}
            pending={!finished}
            showSavedTotalLabel={false}
            clockTriggered={clockTriggered}
            flows={flows}
            clockLabelPosition={{ x: 497, y: 243 }}
          />
          <g className="fpga-dsp-demo-values">
            <g className={finished ? "fpga-faint" : undefined}>
              <Label x={65} y={102} value>
                {repeating ? 2 : 3}
              </Label>
              <Label x={65} y={202} value>
                2
              </Label>
            </g>
            {directProduct &&
              (animate ? (
                <MovingNumber
                  value={6}
                  path="M248 180H470"
                  {...timing.product}
                  holdAtEnd
                />
              ) : (
                <NumberTile value={6} x={470} y={180} />
              ))}
            {accumulating && (
              <>
                {captures && (
                  <Label x={280} y={65} value className="fpga-dsp-equation">
                    {equation}
                  </Label>
                )}
                <Label
                  x={309}
                  y={feedbackInputY}
                  value
                  anchor="end"
                  className="fpga-dsp-adder-input"
                >
                  {adderInput}
                </Label>
                {productReady && (
                  <Label
                    x={275}
                    y={156}
                    value
                    className={finished ? "fpga-faint" : undefined}
                  >
                    {repeating ? 4 : 6}
                  </Label>
                )}
                <Label
                  x={459}
                  y={180}
                  value
                  className="fpga-dsp-register-value"
                >
                  {total}
                </Label>
                {result !== null && (
                  <g
                    className={
                      clock && animate ? "fpga-dsp-waiting-result" : undefined
                    }
                  >
                    <NumberTile value={result} x={waitingResultX} y={180} />
                  </g>
                )}
              </>
            )}
          </g>
          {animate && (
            <g key={beat} className="fpga-dsp-demo-motion" aria-hidden="true">
              {inputs && (
                <>
                  <MovingNumber
                    value={repeating ? 2 : 3}
                    path="M65 120H125V160H170"
                    {...timing.input}
                  />
                  <MovingNumber
                    value={2}
                    path="M65 220H125V200H170"
                    {...timing.input}
                  />
                </>
              )}
              {product && (
                <MovingNumber
                  value={repeating ? 4 : 6}
                  path="M248 180H303"
                  {...timing.product}
                />
              )}
              {feedback && (
                <MovingNumber
                  value={total}
                  path={`M510 180H540V285H333V${feedbackInputY}`}
                  {...timing.feedback}
                  holdAtEnd
                  onArrival={() => setBeat(finalBeat)}
                />
              )}
              {pendingSum && (
                <MovingNumber
                  value={6}
                  path={`M363 180H${waitingResultX}`}
                  {...timing.pendingSum}
                  holdAtEnd
                />
              )}
              {clock && (
                <>
                  <circle
                    r={5}
                    className="fpga-dsp-demo-clock"
                    style={{
                      offsetPath: 'path("M459 245V212")',
                      animationDuration: `${timing.clock.duration}ms`,
                      animationDelay: `${timing.clock.delay}ms`,
                    }}
                  />
                  <MovingNumber
                    value={result!}
                    path={`M${waitingResultX} 180H459`}
                    {...timing.capture}
                  />
                </>
              )}
              {clockTriggered && (
                <rect
                  x={405}
                  y={145}
                  width={108}
                  height={70}
                  rx={6}
                  className="fpga-dsp-demo-capture"
                />
              )}
            </g>
          )}
        </g>
      </Figure>
    </div>
  );
};
