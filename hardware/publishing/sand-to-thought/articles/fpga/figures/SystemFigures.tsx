import { useState } from "react";
import { initialPulse, pulseEdge, timingBudget } from "./model";
import { Block, Figure, Label, Wire } from "./drawing";

export const ImplementationFigure = ({ scene }: { scene: string }) => {
  const [period, setPeriod] = useState(10);
  const budget = timingBudget(period);
  const tests = [0, 4, 12, 16].map((width) => {
    let state = initialPulse(width);
    let high = 0;
    let aligned = true;
    for (let i = 0; i < 16; i++) {
      high += state.output;
      aligned &&= state.output === Number(state.count < width);
      state = pulseEdge(state);
    }

    return { width, pass: aligned && high === width && state.count === 0 };
  });

  if (scene === "simulate")
    return (
      <>
        <Figure title="Functional pulse-model checks for widths zero, four, twelve and sixteen. Each row shows sixteen output intervals. These are browser model checks, not compiled HDL or physical board tests.">
          <Label x={80} y={70} small>
            Width
          </Label>
          <Label x={280} y={70} small>
            Sixteen output intervals
          </Label>
          {tests.map(({ width, pass }, i) => (
            <g key={width}>
              <Label x={80} y={125 + i * 55} value>
                {width}
              </Label>
              {Array.from({ length: 16 }, (_, count) => (
                <rect
                  key={count}
                  x={165 + count * 14}
                  y={104 + i * 55}
                  width={12}
                  height={28}
                  className={count < width ? "fpga-wave-high" : "fpga-wave-low"}
                />
              ))}
              <Label
                x={465}
                y={125 + i * 55}
                small
                className={pass ? "fpga-pass" : ""}
              >
                {pass ? "Pass" : "Fail"}
              </Label>
            </g>
          ))}
        </Figure>
        <p className="fpga-status">
          Browser model checks. Physical timing still needs checking.
        </p>
      </>
    );

  if (scene === "timing-check")
    return (
      <>
        <Figure
          title={`A hypothetical path needs eight time units, including setup. A clock period of ${period} gives ${budget.slack} units of slack.`}
        >
          <Wire d="M133 140H178M263 140H308M393 140H438" active />
          <Block
            x={38}
            y={110}
            w={95}
            h={65}
            label="Count"
            detail="Register"
            kind="storage"
          />
          <Block
            x={178}
            y={110}
            w={85}
            h={65}
            label="Add"
            detail="3 units"
            kind="arithmetic"
          />
          <Block
            x={308}
            y={110}
            w={85}
            h={65}
            label="Compare"
            detail="2 units"
          />
          <Block
            x={438}
            y={110}
            w={95}
            h={65}
            label="Output"
            detail="Register"
            kind="storage"
          />
          <Label x={280} y={222} small>
            Path + setup: 8 time units
          </Label>
          <path d="M65 285H505" className="fpga-guide" />
          <rect
            x={65}
            y={266}
            width={8 * 36}
            height={22}
            className={budget.passes ? "fpga-budget-pass" : "fpga-budget-fail"}
          />
          <path
            d={`M${65 + period * 36} 250V308`}
            className="fpga-edge-marker"
          />
          <Label x={65 + period * 36} y={333} small>
            Capture deadline
          </Label>
        </Figure>
        <div className="fpga-controls" role="group" aria-label="Timing budget">
          <span>Clock period</span>
          {[7, 10].map((value) => (
            <button
              type="button"
              key={value}
              aria-pressed={period === value}
              onClick={() => setPeriod(value)}
            >
              {value} units
            </button>
          ))}
        </div>
        <p className="fpga-status" role="status">
          {budget.passes
            ? `Meets this setup budget with ${budget.slack} units to spare.`
            : `Misses this setup deadline by ${-budget.slack} unit.`}{" "}
          Invented teaching delays.
        </p>
      </>
    );

  return (
    <>
      <Figure title="Synthesis turns the pulse description into connected count storage, an adder, a comparison circuit and output storage. This is an illustrative circuit, not an actual tool report.">
        <Wire
          d="M140 157H185M255 157H305M395 157H450M280 157V85H20V157H35M350 240V190"
          active
        />
        <circle cx={280} cy={157} r={3} className="fpga-junction" />
        <Block
          x={35}
          y={125}
          w={105}
          label="Count"
          detail="4 bits"
          kind="storage"
        />
        <Block x={185} y={125} w={70} label="Add 1" kind="arithmetic" />
        <Block x={305} y={125} w={90} label="Below?" />
        <Block
          x={450}
          y={125}
          w={100}
          label="Output"
          detail="1 bit"
          kind="storage"
        />
        <Block x={305} y={240} w={90} h={50} label="Width" kind="storage" />
      </Figure>
    </>
  );
};

export const ChoiceFigure = ({ scene }: { scene: string }) => {
  return (
    <>
      <Figure
        title={
          scene === "built-in-timers"
            ? "A microcontroller CPU sets up its hardware timer. The timer generates PWM without a software instruction for each pulse."
            : "A CPU writes parameters into an FPGA register interface and reads results. FPGA logic handles its configured data path."
        }
      >
        <Label x={280} y={55}>
          {scene === "built-in-timers"
            ? "A timer can already do this"
            : "Software and configured hardware cooperate"}
        </Label>
        <Wire d="M105 175H455" active />
        {(scene === "built-in-timers"
          ? ["CPU setup", "Timer", "PWM output"]
          : ["CPU software", "Registers", "FPGA path"]
        ).map((label, i) => (
          <Block
            key={label}
            x={40 + i * 185}
            y={135}
            w={110}
            h={80}
            label={label}
            kind={i === 1 ? "storage" : "logic"}
          />
        ))}
        {scene === "cpu-and-fpga" && <Wire d="M410 215V278H95V215" active />}
      </Figure>
      <p className="fpga-status">
        {scene === "built-in-timers"
          ? "PWM alone does not justify choosing an FPGA. Many microcontrollers provide it directly."
          : "A fixed CPU core and a CPU constructed from configurable logic are different implementations."}
      </p>
    </>
  );
};

export const HistoryFigure = () => (
  <>
    <Figure title="Programmable memory and logic preceded the FPGA. Ross Freeman developed the FPGA concept in 1984. Xilinx introduced the XC2064 in 1985. Later devices integrated more memory, arithmetic and processor resources.">
      <Wire d="M65 130H500" />
      {[
        { x: 70, year: "1970s", label: "Memory → logic" },
        { x: 210, year: "1984", label: "FPGA concept" },
        { x: 350, year: "1985", label: "XC2064" },
        { x: 490, year: "Later", label: "Richer devices" },
      ].map(({ x, year, label }) => (
        <g key={year}>
          <circle cx={x} cy={130} r={5} className="fpga-junction" />
          <Label x={x} y={98} value>
            {year}
          </Label>
          <Label x={x} y={170} small>
            {label}
          </Label>
        </g>
      ))}
      <Block x={65} y={220} w={100} label="Logic" kind="config" />
      <Wire d="M165 252H210M310 252H355" active />
      <Block x={210} y={220} w={100} label="Routing" />
      <Block
        x={355}
        y={205}
        w={160}
        h={95}
        label="Logic + RAM"
        detail="Arithmetic + CPUs"
      />
    </Figure>
    <p className="fpga-status">
      The central idea persists: stored settings select functions and
      connections.
    </p>
  </>
);
