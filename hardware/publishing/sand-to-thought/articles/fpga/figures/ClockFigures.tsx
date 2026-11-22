import { useState } from "react";
import {
  binary,
  capturePair,
  initialPulse,
  pulseEdge,
  pulsePeriod,
  requestWidth,
} from "./model";
import type { Bit } from "./model";
import {
  BitControls,
  Block,
  ClockControls,
  ClockLine,
  Figure,
  FlipFlop,
  Label,
  Wire,
} from "./drawing";
import { useClock } from "./useFpgaJourney";

type Sample = { d: number; q: number; clock: number };

const Waveforms = ({
  samples,
  compact = false,
}: {
  samples: Sample[];
  compact?: boolean;
}) => {
  const rows = [
    { key: "clock", label: "Clock", y: 245 },
    { key: "d", label: "D", y: 287 },
    { key: "q", label: "Q", y: 329 },
  ] as const;
  const count = Math.max(7, samples.length - 1);
  const start = compact ? 65 : 100;
  const end = compact ? 350 : 515;
  const dx = (end - start - 10) / count;

  return (
    <g>
      <Label x={compact ? 319 : 475} y={219} small>
        Time →
      </Label>
      {rows.map(({ key, label, y }) => {
        let path = `M${start} ${y - 18 * samples[0][key]}`;
        samples.slice(1).forEach((sample, i) => {
          const x =
            start +
            (i + 1) * dx +
            (key === "q" && samples[i].q !== sample.q ? 5 : 0);
          path += `H${x}V${y - 18 * sample[key]}`;
        });
        path += `H${end}`;

        return (
          <g key={key}>
            <Label
              x={start - 12}
              y={y - 3}
              anchor="end"
              small
              value={key !== "clock"}
            >
              {label}
            </Label>
            <path d={`M${start} ${y}H${end}`} className="fpga-guide" />
            <path d={path} className="fpga-wave" />
          </g>
        );
      })}
      {samples.map((sample, i) =>
        i > 0 && sample.clock === 1 && samples[i - 1].clock === 0 ? (
          <path
            key={i}
            d={`M${start + i * dx} 222V338`}
            className="fpga-edge-marker"
          />
        ) : null,
      )}
      <Label x={compact ? 180 : 280} y={362} small>
        Higher line = 1. Lower line = 0.
      </Label>
    </g>
  );
};

const SingleFlipFlop = () => {
  const [d, setD] = useState<Bit>(0);
  const [q, setQ] = useState<Bit>(0);
  const [edge, setEdge] = useState(0);
  const [samples, setSamples] = useState<Sample[]>([{ d: 0, q: 0, clock: 0 }]);
  const capture = () => {
    setQ(d);
    setEdge((value) => value + 1);
    setSamples((previous) =>
      [...previous, { d, q: d, clock: 1 }, { d, q: d, clock: 0 }].slice(-14),
    );
  };
  const { stage, ...clock } = useClock(capture);
  const reset = () => {
    clock.setRunning(false);
    setD(0);
    setQ(0);
    setEdge(0);
    setSamples([{ d: 0, q: 0, clock: 0 }]);
  };

  return (
    <div ref={stage}>
      <Figure
        title={`Data input D is ${d}. The flip-flop holds Q at ${q}. Only a rising clock edge captures D.`}
        compact={{
          viewBox: "0 0 360 370",
          children: (
            <>
              <Wire d="M30 80H125M230 80H330" active={d === q} />
              <Label x={55} y={55} value>
                D = {d}
              </Label>
              <Label x={308} y={55} value>
                Q = {q}
              </Label>
              <FlipFlop x={125} y={45} value={q} capture={edge} />
              <ClockLine x={177} y={130} edge={edge} />
              <Waveforms samples={samples} compact />
            </>
          ),
        }}
      >
        <Wire d="M100 80H226M331 80H470" active={d === q} />
        <Label x={120} y={60} value>
          D = {d}
        </Label>
        <Label x={448} y={60} value>
          Q = {q}
        </Label>
        <FlipFlop x={226} y={45} value={q} capture={edge} />
        <ClockLine x={278} y={130} edge={edge} />
        <Waveforms samples={samples} />
      </Figure>
      <div className="fpga-controls">
        <BitControls
          name="D"
          value={d}
          onChange={() => {
            const next = d === 0 ? 1 : 0;
            setD(next);
            setSamples((previous) =>
              [...previous, { d: next, q, clock: 0 }].slice(-14),
            );
          }}
        />
      </div>
      <ClockControls capture={capture} reset={reset} {...clock} />
      <p className="fpga-status" role="status">
        {edge === 0
          ? "Change D, then apply a clock edge. Q holds its previous value between edges."
          : `After edge ${edge}, Q holds ${q}. ${d !== q ? `D is now ${d}, ready for the next edge.` : "D and Q currently match."}`}
      </p>
    </div>
  );
};

const RegisterFigure = () => {
  const [input, setInput] = useState(9);
  const [value, setValue] = useState(0);
  const [edge, setEdge] = useState(0);
  const capture = () => {
    setValue(input);
    setEdge((previous) => previous + 1);
  };
  const { stage, ...clock } = useClock(capture);

  return (
    <div ref={stage}>
      <Figure
        title={`Four flip-flops share a clock. Input ${binary(input)} is prepared, while the register holds ${binary(value)}.`}
      >
        <Label x={280} y={45} value>
          Prepared input {binary(input)} = {input}
        </Label>
        {[...binary(value)].map((bit, i) => (
          <g key={i}>
            <Wire d={`M${40 + i * 125} 136H${55 + i * 125}`} />
            <Label x={40 + i * 125} y={110} value>
              {binary(input)[i]}
            </Label>
            <FlipFlop
              x={55 + i * 125}
              y={100}
              value={bit}
              label="Bit"
              capture={edge}
            />
            <Wire d={`M${107 + i * 125} 185V240`} />
          </g>
        ))}
        <Wire d="M107 240H482M280 240V277" />
        <Label x={280} y={300}>
          Shared clock
        </Label>
        <Label x={280} y={345} value>
          Stored output {binary(value)} = {value}
        </Label>
      </Figure>
      <div className="fpga-controls">
        <button type="button" onClick={() => setInput(input === 9 ? 6 : 9)}>
          Prepare input {input === 9 ? "0110 = 6" : "1001 = 9"}
        </button>
      </div>
      <ClockControls
        capture={capture}
        reset={() => {
          clock.setRunning(false);
          setValue(0);
          setEdge(0);
        }}
        {...clock}
      />
      <p className="fpga-status" role="status">
        All four bits capture together. The register currently stores {value}.
      </p>
    </div>
  );
};

export const StorageFigure = ({ scene }: { scene: string }) =>
  scene === "register" ? <RegisterFigure /> : <SingleFlipFlop />;

const CounterFigure = () => {
  const [count, setCount] = useState(0);
  const [edge, setEdge] = useState(0);
  const capture = () => {
    setCount((previous) => (previous + 1) % 16);
    setEdge((previous) => previous + 1);
  };
  const { stage, ...clock } = useClock(capture);

  return (
    <div ref={stage}>
      <Figure
        title={`The four-bit counter holds ${count}. The adder prepares ${(count + 1) % 16}, which is captured at the next edge.`}
      >
        <FlipFlop
          x={145}
          y={110}
          value={binary(count)}
          label="Register"
          width={4}
          capture={edge}
        />
        <Wire
          d="M250 150H355M455 150H500V60H95V150H145"
          active
          bus={{ x: 300, y: 150, width: 4 }}
        />
        <Block
          x={355}
          y={115}
          label="Add 1"
          detail={binary((count + 1) % 16)}
          kind="arithmetic"
        />
        <Label x={285} y={41} small value>
          Prepared next value {(count + 1) % 16}
        </Label>
        <Label x={285} y={220} value>
          Current value {count}
        </Label>
        <ClockLine x={197} y={195} edge={edge} />
        <Label x={280} y={340} small>
          15 + 1 wraps to 0 in a four-bit register.
        </Label>
      </Figure>
      <ClockControls
        capture={capture}
        reset={() => {
          clock.setRunning(false);
          setCount(0);
          setEdge(0);
        }}
        {...clock}
      />
      <p className="fpga-status" role="status">
        {count} is stored. {(count + 1) % 16} is prepared, ready for edge{" "}
        {edge + 1}.
      </p>
    </div>
  );
};

const RegisterPairFigure = () => {
  const [pair, setPair] = useState({ a: 3, b: 0 });
  const [edge, setEdge] = useState(0);
  const capture = () => {
    setPair(capturePair);
    setEdge((previous) => previous + 1);
  };
  const { stage, ...clock } = useClock(capture);

  return (
    <div ref={stage}>
      <Figure
        title={`Register A holds ${pair.a} and B holds ${pair.b}. At the next shared edge A captures ${(pair.a + 1) % 16} and B captures the previous A, ${pair.a}.`}
      >
        <Label x={150} y={40} small>
          Prepared input
        </Label>
        <Label x={410} y={40} small>
          Prepared input
        </Label>
        <Label x={150} y={75} value>
          A + 1 = {(pair.a + 1) % 16}
        </Label>
        <Label x={410} y={75} value>
          A = {pair.a}
        </Label>
        <Wire d="M150 87V108H95V150H120M410 87V108H355V150H380" active />
        <FlipFlop
          x={120}
          y={120}
          value={pair.a}
          label="A"
          captionInside
          width={4}
          capture={edge}
        />
        <FlipFlop
          x={380}
          y={120}
          value={pair.b}
          label="B"
          captionInside
          width={4}
          capture={edge}
        />
        <Wire d="M225 160H280V108H355M173 205V260H433V205M280 260V290" />
        <circle cx={355} cy={108} r={3} className="fpga-dot" />
        <Label x={280} y={321}>
          One shared clock edge
        </Label>
        <Label x={280} y={355} small className="fpga-note">
          B captures the old A. Both registers update together.
        </Label>
      </Figure>
      <ClockControls
        capture={capture}
        reset={() => {
          clock.setRunning(false);
          setPair({ a: 3, b: 0 });
          setEdge(0);
        }}
        {...clock}
      />
      <p className="fpga-status" role="status">
        {edge === 0
          ? "Before the first edge: A = 3, B = 0. Prepared inputs are 4 and 3."
          : `After edge ${edge}: A = ${pair.a}, B = ${pair.b}.`}
      </p>
    </div>
  );
};

export const CountingFigure = ({ scene }: { scene: string }) =>
  scene === "simultaneous-capture" ? <RegisterPairFigure /> : <CounterFigure />;

export const ClockTimingFigure = () => (
  <>
    <Figure title="Data must remain stable for setup time before a rising clock edge and hold time afterwards. A dedicated clock network distributes edges to registers.">
      <Block x={55} y={47} w={105} h={60} label="Register" kind="storage" />
      <Wire d="M160 77H225M325 77H400" active />
      <Block x={225} y={47} label="Logic" h={60} />
      <Block x={400} y={47} label="Register" kind="storage" h={60} />
      <Wire d="M280 161V131H105V107M280 131H450V107" />
      <Label x={280} y={188}>
        Clock distribution
      </Label>
      <Label x={68} y={245} small>
        Clock
      </Label>
      <Label x={68} y={305} small>
        Data
      </Label>
      <path d="M118 250H310V221H445V250H520" className="fpga-wave" />
      <path d="M118 310H185V281H420V310H520" className="fpga-wave" />
      <rect
        x={270}
        y={269}
        width={70}
        height={53}
        className="fpga-timing-window"
      />
      <path d="M310 205V326" className="fpga-edge-marker" />
      <Label x={266} y={351} small anchor="end">
        Setup
      </Label>
      <Label x={350} y={351} small anchor="start">
        Hold
      </Label>
    </Figure>
  </>
);

export const PulseFigure = () => {
  const [state, setState] = useState(initialPulse);
  const capture = () => setState(pulseEdge);
  const { stage, ...clock } = useClock(capture);
  const values = pulsePeriod(state.width);
  const next = pulseEdge(state);

  return (
    <div ref={stage}>
      <Figure
        title={`Pulse generator. Count ${state.count}, width ${state.width}, output ${state.output}. The next edge captures count ${next.count} and output ${next.output}.`}
        compact={{
          viewBox: "0 0 360 340",
          children: (
            <>
              <Block
                x={20}
                y={35}
                w={94}
                h={70}
                label="Count"
                detail={state.count}
                kind="storage"
              />
              <Wire
                d="M114 70H200M290 70H337V16H5V70H20"
                active
                bus={{ x: 150, y: 70, width: 4 }}
              />
              <Block
                x={200}
                y={45}
                w={90}
                h={50}
                label="Add 1"
                detail={next.count}
                kind="arithmetic"
              />
              <Wire d="M337 70V165H290M200 165H114" active />
              <circle cx={337} cy={70} r={3} className="fpga-junction" />
              <Block
                x={200}
                y={140}
                w={90}
                h={50}
                label="Below?"
                detail={next.output}
              />
              <Block
                x={20}
                y={130}
                w={94}
                h={70}
                label="Output"
                detail={state.output}
                kind="storage"
              />
              <Wire d="M244 205V190" active />
              <Block
                x={194}
                y={205}
                w={100}
                h={34}
                label={`width ${next.width}`}
                kind="storage"
              />
              <Label x={95} y={232} small>
                Shared clock
              </Label>
              <Wire d="M67 105V120H151V210H67V200M151 210V230" />
              {[105, 200].map((y) => (
                <path key={y} d={`M57 ${y}l10 -8 10 8`} className="fpga-wire" />
              ))}
              <Label x={4} y={250} small anchor="start">
                Count
              </Label>
              <Label x={20} y={278} small>
                Out
              </Label>
              <Label x={20} y={327} small>
                Out
              </Label>
              {values.map((value, i) => {
                const x = 48 + (i % 8) * 37;
                const y = i < 8 ? 261 : 310;

                return (
                  <g key={i}>
                    <Label x={x + 17} y={y - 5} small value>
                      {i}
                    </Label>
                    <rect
                      x={x}
                      y={y}
                      width={34}
                      height={23}
                      className={value ? "fpga-wave-high" : "fpga-wave-low"}
                    />
                    <Label x={x + 17} y={y + 18} small value>
                      {value}
                    </Label>
                    {i === state.count && (
                      <rect
                        x={x}
                        y={y}
                        width={34}
                        height={23}
                        className="fpga-current-count"
                      />
                    )}
                  </g>
                );
              })}
            </>
          ),
        }}
      >
        <FlipFlop
          x={55}
          y={55}
          value={state.count}
          label="Count"
          width={4}
          capture={state.edges}
        />
        <Wire d="M160 92H205" active bus={{ x: 182, y: 92, width: 4 }} />
        <Wire d="M290 92H333" active bus={{ x: 310, y: 92, width: 4 }} />
        <Wire d="M290 92V24H25V92H55" active />
        <circle cx={290} cy={92} r={3} className="fpga-junction" />
        <Block
          x={205}
          y={62}
          w={85}
          h={58}
          label="Add 1"
          detail={next.count}
          kind="arithmetic"
        />
        <Block
          x={333}
          y={62}
          w={85}
          h={58}
          label="Below?"
          detail={next.output}
          kind="logic"
        />
        <Wire d="M418 92H443M548 92H555" active />
        <Wire d="M375 170V120" active bus={{ x: 375, y: 145, width: 5 }} />
        <FlipFlop
          x={443}
          y={55}
          value={state.output}
          label="Output"
          capture={state.edges}
        />
        <Block
          x={325}
          y={170}
          w={100}
          h={44}
          label={`width ${next.width}`}
          kind="storage"
        />
        <Wire d="M107 140V235H495V140M280 235V255" />
        <Label x={280} y={277} small>
          Clock
        </Label>
        <Label x={35} y={322} small anchor="end">
          Out
        </Label>
        <Label x={45} y={354} small anchor="end">
          Count
        </Label>
        {values.map((value, i) => (
          <g key={i}>
            <rect
              x={56 + i * 29}
              y={300}
              width={28}
              height={30}
              className={value ? "fpga-wave-high" : "fpga-wave-low"}
            />
            <Label x={70 + i * 29} y={322} value small>
              {value}
            </Label>
            <Label x={70 + i * 29} y={354} small value>
              {i}
            </Label>
            {i === state.count && (
              <path d={`M${70 + i * 29} 288l-5 -7h10z`} className="fpga-dot" />
            )}
          </g>
        ))}
      </Figure>
      <div className="fpga-controls" role="group" aria-label="Pulse width">
        <span>Width</span>
        {[0, 4, 12, 16].map((width) => (
          <button
            type="button"
            key={width}
            aria-pressed={state.pending === width}
            onClick={() =>
              setState((previous) => requestWidth(previous, width))
            }
          >
            {width}
          </button>
        ))}
      </div>
      <ClockControls
        capture={capture}
        reset={() => {
          clock.setRunning(false);
          setState(initialPulse());
        }}
        {...clock}
      />
      <div className="fpga-controls">
        <button
          type="button"
          onClick={() =>
            setState((previous) => {
              let nextState = previous;
              for (let i = 0; i < 16 - previous.count; i++)
                nextState = pulseEdge(nextState);
              return nextState;
            })
          }
        >
          Advance to next period
        </button>
      </div>
      <p className="fpga-status" role="status">
        {state.pending !== state.width
          ? `Width ${state.pending} takes effect when the count returns to 0.`
          : `${state.width} of 16 intervals are high.`}
      </p>
    </div>
  );
};
