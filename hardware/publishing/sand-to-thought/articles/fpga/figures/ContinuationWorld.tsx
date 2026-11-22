import { BoardFigure } from "./BoardFigure";
import { Block, Label, Wire } from "./drawing";
import { initialPulse, pulseEdge } from "./model";
import { WorldLayer } from "./WorldLayer";

export const worldSceneKeys = [
  "our-board",
  "board-request",
  "simulate",
  "built-in-timers",
] as const;

const Simulation = () => (
  <>
    <Label x={70} y={335} small>
      Width
    </Label>
    <Label x={280} y={335} small>
      Simulated output
    </Label>
    {[0, 4, 12, 16].map((width, row) => {
      let state = initialPulse(width);
      let high = 0;
      let aligned = true;
      for (let interval = 0; interval < 16; interval++) {
        high += state.output;
        aligned &&= state.output === Number(state.count < width);
        state = pulseEdge(state);
      }
      const pass = aligned && high === width && state.count === 0;

      return (
        <g key={width}>
          <Label x={70} y={366 + row * 37} value>
            {width}
          </Label>
          {Array.from({ length: 16 }, (_, interval) => (
            <rect
              key={interval}
              x={145 + interval * 17}
              y={345 + row * 37}
              width={15}
              height={26}
              className={interval < width ? "fpga-wave-high" : "fpga-wave-low"}
            />
          ))}
          <Label
            x={470}
            y={366 + row * 37}
            small
            className={pass ? "fpga-pass" : ""}
          >
            {pass ? "Pass" : "Fail"}
          </Label>
        </g>
      );
    })}
  </>
);

const Timers = () => (
  <>
    <Label x={104} y={140}>
      Microcontroller
    </Label>
    <Label x={408} y={140}>
      FPGA
    </Label>
    <g className="fpga-world-equipment">
      <rect x={-10} y={168} width={225} height={220} rx={8} />
    </g>
    <Block x={40} y={195} w={125} h={50} label="CPU setup" />
    <Wire d="M102 245V279" control />
    <Block x={40} y={279} w={125} h={55} label="Timer" kind="storage" />
    <Wire d="M102 334V457" active />
    <path d="M20 457h30v-25h30v25h30v-25h30v25h30" className="fpga-wave" />
    <Wire d="M527 321.2H552V457H480" active />
    <path d="M330 457h30v-25h30v25h30v-25h30v25h30" className="fpga-wave" />
  </>
);

export const ContinuationWorld = ({
  scene,
  lecture,
}: {
  scene: string;
  lecture?: boolean;
}) => (
  <>
    <WorldLayer
      className={
        scene === "our-board" || scene === "board-request"
          ? "fpga-board-world"
          : undefined
      }
      title={
        scene === "our-board" || scene === "board-request"
          ? "The KV260 carrier holds the K26 module, which contains the Zynq chip, DDR4 and boot flash. The chip contains the CPU, controllers and FPGA logic. The carrier’s microSD and Ethernet connect to the controllers. In the request view, the board starts from boot flash and loads Linux from microSD into DDR4. The laptop sends its prompt to the CPU through Ethernet and the controllers. The CPU sends tokens to the FPGA and receives scores over an on-chip connection. Each chosen token travels to the laptop and back to the FPGA for the next prediction. The laptop screen pairs an example prompt with a reply from the software evaluation. The animation shows the order of transfers at an illustrative pace."
          : scene === "simulate"
            ? "Browser pulse-model checks beside the same FPGA circuit. Four rows each show sixteen output intervals. These are model checks, not hardware measurements."
            : "A microcontroller's fixed timer and a configured FPGA circuit can both generate PWM. The drawings show alternative implementations, not chips connected together."
      }
    >
      {scene === "our-board" || scene === "board-request" ? (
        <BoardFigure
          request={scene === "board-request"}
          lecture={lecture}
        />
      ) : scene === "simulate" ? (
        <Simulation />
      ) : (
        <Timers />
      )}
    </WorldLayer>
  </>
);
