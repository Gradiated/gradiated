import { useEffect, useState } from "react";
import { Block, Figure, Label, Wire } from "./drawing";
import { useClock } from "./useFpgaJourney";
import { videoFrame, videoStep, videoTile } from "./ledWallModel";

const Pixels = ({
  pixels,
  x,
  y,
  size,
  visible = true,
}: {
  pixels: number[][];
  x: number;
  y: number;
  size: number;
  visible?: boolean;
}) => (
  <g className="fpga-video-pixels">
    {pixels.flatMap((row, j) =>
      row.map((value, i) => (
        <rect
          key={`${i}-${j}`}
          x={x + i * size}
          y={y + j * size}
          width={size - 1}
          height={size - 1}
          rx={size > 6 ? 1 : 0}
          className={visible && value ? "is-lit" : undefined}
        />
      )),
    )}
  </g>
);

const stages = [
  "Receive the next picture into a buffer. The display keeps its previous picture.",
  "Read each tile’s pixels from the buffer in the order its driver needs.",
  "Four output paths send different parts of the picture to four drivers at once.",
  "The drivers update their tiles together. The complete picture is held for viewing.",
];

export const LedWallFigure = () => {
  const [step, setStep] = useState(3);
  const { phase, incoming, displayed } = videoStep(step);
  const description =
    phase === 0 && displayed === null
      ? "Receive the first picture into a buffer."
      : stages[phase];
  const current = videoFrame(incoming);
  const shown = videoFrame(displayed ?? 0);
  const clock = useClock(() => setStep((value) => value + 1));

  useEffect(() => {
    clock.setRunning(true);
  }, [clock.setRunning]);

  return (
    <div ref={clock.stage}>
      <Figure
        title={`Illustrative LED wall: ${description} Incoming picture ${incoming + 1}; ${displayed === null ? "display not yet loaded" : `displaying picture ${displayed + 1}`}.`}
        viewBox="0 0 560 400"
      >
        <Label x={280} y={24}>
          One picture, four parallel outputs
        </Label>
        <Label x={74} y={83} small>
          Incoming video
        </Label>
        <Pixels pixels={current} x={18} y={100} size={7} />
        <Wire d="M130 128H168" active={phase === 0} />
        {phase === 0 && clock.running && (
          <circle cx={130} cy={128} r={3} className="fpga-video-input-dot" />
        )}
        <rect
          x={152}
          y={48}
          width={378}
          height={132}
          rx={6}
          className="fpga-chip-outline"
        />
        <Label x={341} y={72} small>
          FPGA
        </Label>
        <Label x={200} y={92} small>
          Buffer
        </Label>
        <Pixels pixels={current} x={168} y={109} size={4} visible={phase > 0} />
        <Wire d="M232 128H260" active={phase === 1} />
        <Label x={387} y={92} small>
          Arrange pixels by tile
        </Label>
        <rect
          x={260}
          y={98}
          width={240}
          height={58}
          rx={3}
          className="fpga-chip-outline"
        />
        {[0, 1, 2, 3].map((tile) => {
          const x = 280 + tile * 60;

          return (
            <g key={tile}>
              <Pixels
                pixels={videoTile(current, tile)}
                x={x}
                y={103}
                size={5}
                visible={phase > 0}
              />
              <Wire d={`M${x + 10} 143V202`} active={phase === 2} />
              <Block
                x={x - 14}
                y={202}
                w={48}
                h={27}
                label={`${tile + 1}`}
                kind="storage"
              />
              <Wire d={`M${x + 10} 229V253`} active={phase === 2} />
              {phase === 2 && clock.running && (
                <>
                  <circle
                    cx={x + 10}
                    cy={181}
                    r={3}
                    className="fpga-video-output-dot"
                  />
                  <circle
                    cx={x + 10}
                    cy={231}
                    r={3}
                    className="fpga-video-output-dot"
                  />
                </>
              )}
              <rect
                x={x - 16}
                y={253}
                width={52}
                height={100}
                rx={3}
                className="fpga-chip-outline"
              />
              <Pixels
                pixels={videoTile(shown, tile)}
                x={x - 14}
                y={255}
                size={12}
                visible={displayed !== null}
              />
            </g>
          );
        })}
        <Label x={235} y={221} anchor="end" small>
          LED drivers
        </Label>
        <Label x={380} y={378} small>
          Four tiles form one video wall
        </Label>
        <Label x={74} y={178} small value>
          Picture {incoming + 1}
        </Label>
        <Label x={95} y={290} small anchor="start">
          Receive
        </Label>
        <Label x={95} y={313} small anchor="start">
          Arrange
        </Label>
        <Label x={95} y={336} small anchor="start">
          Send
        </Label>
        <Label x={95} y={359} small anchor="start">
          Display
        </Label>
        <circle cx={80} cy={285 + phase * 23} r={4} className="fpga-junction" />
      </Figure>
      <div className="fpga-controls">
        {!clock.reduced && (
          <button
            type="button"
            onClick={() => clock.setRunning(!clock.running)}
          >
            {clock.running ? "Pause animation" : "Play animation"}
          </button>
        )}
        <button
          type="button"
          disabled={clock.running}
          onClick={() => setStep((value) => value + 1)}
        >
          Next stage
        </button>
        <button type="button" onClick={() => setStep(0)}>
          Restart
        </button>
      </div>
      <p className="fpga-status" aria-live={clock.running ? "off" : "polite"}>
        {description} Timing and pixel counts are enlarged for teaching.
      </p>
    </div>
  );
};
