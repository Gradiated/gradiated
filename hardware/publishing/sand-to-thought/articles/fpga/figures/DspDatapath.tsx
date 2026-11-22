import type { ComponentProps, CSSProperties } from "react";
import { Label, Transfer, Wire } from "./drawing";

type DspFlowTiming = { duration: number; delay?: number };
export type DspFlows = Partial<
  Record<"inputs" | "product" | "sum" | "feedback" | "clock", DspFlowTiming>
>;

const DspWire = ({
  flow,
  arrow,
  ...wire
}: ComponentProps<typeof Wire> & { flow?: DspFlowTiming; arrow?: string }) => (
  <g
    className={flow ? "fpga-dsp-wire-flow" : undefined}
    style={
      flow
        ? ({
            "--fpga-dsp-flow-duration": `${flow.duration}ms`,
            "--fpga-dsp-flow-delay": `${flow.delay ?? 0}ms`,
          } as CSSProperties)
        : undefined
    }
  >
    <Wire {...wire} active={wire.active || Boolean(flow)} />
    {arrow && (
      <g aria-hidden="true">
        <path d={arrow} className="fpga-dsp-adder-arrows" />
        {(wire.active || flow) && (
          <path d={arrow} className="fpga-dsp-arrow-highlight" />
        )}
      </g>
    )}
  </g>
);

export const DspDatapath = ({
  input = 3,
  weight = 2,
  total = 0,
  accumulate = false,
  pending = true,
  capture = 0,
  captureFrom,
  showInputNames = false,
  showSavedTotalLabel = true,
  clockTriggered = false,
  flows,
  clockLabelPosition = { x: 459, y: 270 },
}: {
  input?: number;
  weight?: number;
  total?: number;
  accumulate?: boolean;
  pending?: boolean;
  capture?: number;
  captureFrom?: number;
  showInputNames?: boolean;
  showSavedTotalLabel?: boolean;
  clockTriggered?: boolean;
  flows?: DspFlows;
  clockLabelPosition?: { x: number; y: number };
}) => {
  const product = input * weight;
  const capturing = captureFrom !== undefined;
  const highlightPending = !flows && pending;

  return (
    <g
      className="fpga-dsp-datapath"
      data-accumulate={accumulate}
      data-capturing={capturing}
    >
      <g className="fpga-resource-bus">
        <DspWire
          d="M20 120H125V160H170"
          active={highlightPending}
          flow={flows?.inputs}
          bus={{ x: 106, y: 120 }}
        />
        <DspWire
          d="M20 220H125V200H170"
          active={highlightPending}
          flow={flows?.inputs}
          bus={{ x: 106, y: 220 }}
        />
        <DspWire
          d={accumulate ? "M242 180H305" : "M242 180H540"}
          active={highlightPending}
          flow={flows?.product}
          arrow={accumulate ? "M296 176L302 180 296 184Z" : undefined}
          bus={{ x: 267, y: 180 }}
        />
      </g>
      {showInputNames && (
        <>
          <Label x={65} y={72} small>
            Input
          </Label>
          <Label x={65} y={172} small>
            Weight
          </Label>
        </>
      )}
      <g className={pending ? undefined : "fpga-faint"}>
        <Label x={65} y={102} value>
          {input}
        </Label>
        <Label x={65} y={202} value>
          {weight}
        </Label>
      </g>
      <rect
        x={170}
        y={144}
        width={72}
        height={72}
        rx={4}
        className="fpga-gate"
      />
      <path d="M194 168l24 24m0 -24l-24 24" className="fpga-wire" />
      <g className="fpga-dsp-direct-output" aria-hidden={accumulate}>
        <Label x={470} y={160} value>
          {product}
        </Label>
      </g>
      <g className="fpga-dsp-accumulator" aria-hidden={!accumulate}>
        <g className="fpga-resource-bus">
          <DspWire
            d="M361 180H408"
            active={highlightPending}
            flow={flows?.sum}
            arrow="M364 176L370 180 364 184Z"
          />
        </g>
        <circle cx={333} cy={180} r={28} className="fpga-gate" />
        <path d="M321 180h24m-12 -12v24" className="fpga-wire" />
        <Label
          x={275}
          y={156}
          value
          className={pending ? undefined : "fpga-faint"}
        >
          {product}
        </Label>
        <g className={capturing ? "fpga-dsp-capture-result" : undefined}>
          <Label x={385} y={146} value className="fpga-dsp-register-value">
            {pending ? total + product : capturing ? total : null}
          </Label>
        </g>
        {showSavedTotalLabel && (
          <Label x={459} y={129} small>
            Saved total
          </Label>
        )}
        <g className="fpga-block fpga-block--storage">
          <rect x={408} y={148} width={102} height={64} rx={4} />
          <Label
            x={459}
            y={180}
            value
            className="fpga-dsp-register-value fpga-dsp-saved-result"
          >
            {total}
          </Label>
          {capturing && (
            <Label
              x={459}
              y={180}
              value
              className="fpga-dsp-register-value fpga-dsp-previous-total"
            >
              {captureFrom}
            </Label>
          )}
        </g>
        <g className="fpga-resource-bus fpga-dsp-feedback">
          <DspWire
            d="M510 180H540V285H333V208"
            active={!flows && (pending || capturing)}
            flow={flows?.feedback}
            arrow="M329 217L333 211 337 217Z"
            bus={{ x: 350, y: 285 }}
          />
        </g>
        <Label x={381} y={269} value className="fpga-dsp-saved-result">
          {total}
        </Label>
        {capturing && (
          <Label x={381} y={269} value className="fpga-dsp-previous-total">
            {captureFrom}
          </Label>
        )}
        <DspWire d="M459 245V212" flow={flows?.clock} />
        <path d="M453 212l6 -7 6 7" className="fpga-wire" />
        <Label
          x={clockLabelPosition.x}
          y={clockLabelPosition.y}
          small
          className={clockTriggered ? "fpga-dsp-clock-triggered" : undefined}
        >
          Clock
        </Label>
        {(capture > 0 || capturing) && (
          <rect
            key={capture}
            x={405}
            y={145}
            width={108}
            height={70}
            rx={6}
            className={`fpga-captured ${capturing ? "fpga-dsp-capture-flash" : ""}`}
          />
        )}
        <Transfer d="M363 180H408" trigger={capture} />
        <Transfer d="M459 245V212" trigger={capture} />
        {capturing && (
          <g className="fpga-dsp-capture-clock">
            <Transfer d="M459 245V212" trigger={1} />
          </g>
        )}
      </g>
    </g>
  );
};
