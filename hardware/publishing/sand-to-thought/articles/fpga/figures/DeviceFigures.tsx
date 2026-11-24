import { useState } from "react";
import { BlockRamFigure } from "./BlockRamFigure";
import { ChipContext } from "./ChipMap";
import { DspDemoFigure } from "./DspDemoFigure";
import { Block, Figure, FlipFlop, Label, Mux, Wire } from "./drawing";

export const LogicBlockFigure = () => {
  const [registered, setRegistered] = useState(true);

  return (
    <ChipContext part="block">
      <Figure
        title={`A simplified logic block contains a LUT, flip-flop and output selector. The ${registered ? "registered" : "direct"} path is selected.`}
        compact={{
          viewBox: "0 0 360 285",
          children: (
            <>
              <rect
                x={10}
                y={20}
                width={340}
                height={240}
                rx={8}
                className="fpga-chip-outline"
              />
              <Label x={180} y={49}>
                Block 1 · simplified
              </Label>
              <Wire d="M5 122H45M133 122H171M276 122H285V137H300M133 122H150V70H285V107H300M332 122H355" />
              <Wire
                d={
                  registered
                    ? "M5 122H45M133 122H171M276 122H285V137H300M332 122H355"
                    : "M5 122H45M133 122H150V70H285V107H300M332 122H355"
                }
                active
              />
              <Block
                x={45}
                y={90}
                w={88}
                h={65}
                label="LUT"
                detail="Rule"
                kind="config"
              />
              <FlipFlop x={171} y={85} value="Held bit" />
              <Mux
                x={300}
                y={122}
                selection={registered ? 1 : 0}
                name="Stored bit"
                showSelectionLabel={false}
              />
              <Label x={289} y={199} small value>
                Stored bit {registered ? 1 : 0}
              </Label>
              <Wire d="M223 170V222" />
              <Label x={223} y={245} small>
                Clock
              </Label>
              <circle cx={150} cy={122} r={3} className="fpga-dot" />
            </>
          ),
        }}
      >
        <rect
          x={65}
          y={55}
          width={435}
          height={265}
          rx={8}
          className="fpga-chip-outline"
        />
        <Label x={280} y={92}>
          Logic block 1 · simplified
        </Label>
        <Wire d="M25 160H110M210 160H255M360 160H415V175H440M210 160H230V115H425V145H440M472 160H535" />
        <Wire
          d={
            registered
              ? "M25 160H110M210 160H255M360 160H415V175H440M472 160H535"
              : "M25 160H110M210 160H230V115H425V145H440M472 160H535"
          }
          active
        />
        <Block x={110} y={125} label="LUT" detail="Stored rule" kind="config" />
        <FlipFlop x={255} y={120} value="Held bit" />
        <Mux x={440} y={160} selection={registered ? 1 : 0} name="Stored bit" />
        <Wire d="M307 205V263" />
        <Label x={307} y={286} small>
          Clock
        </Label>
        <circle cx={230} cy={160} r={3} className="fpga-dot" />
      </Figure>
      <div className="fpga-controls">
        <button
          type="button"
          aria-pressed={!registered}
          onClick={() => setRegistered(false)}
        >
          Direct LUT result
        </button>
        <button
          type="button"
          aria-pressed={registered}
          onClick={() => setRegistered(true)}
        >
          Stored result
        </button>
      </div>
      <p className="fpga-status">
        The stored selection bit chooses which path reaches the output.
      </p>
    </ChipContext>
  );
};

export const ResourcesFigure = ({ scene }: { scene: string }) => {
  if (
    scene === "arithmetic-blocks" ||
    scene === "arithmetic-accumulate" ||
    scene === "arithmetic-save" ||
    scene === "arithmetic-next"
  ) {
    return <DspDemoFigure key={scene} scene={scene} />;
  }

  return <BlockRamFigure />;
};

export const BoundaryFigure = ({ scene }: { scene: string }) => {
  const [power, setPowered] = useState(true);
  const [configuration, setConfigured] = useState(true);
  const roles = scene === "memory-roles";
  const powered = !roles || power;
  const configured = !roles || configuration;

  return (
    <>
      <Figure
        title={
          roles
            ? "Configuration settings, register state and data memory serve different jobs. External flash retains a bitstream when power is off."
            : "Input and output pins connect the FPGA's configured circuit to the outside world."
        }
      >
        {roles && (
          <>
            <Block
              x={215}
              y={12}
              w={130}
              h={52}
              label="Board flash"
              detail="Keeps bitstream"
              kind="config"
            />
            <Wire d="M280 64V95" control active={powered && configured} />
          </>
        )}
        <rect
          x={85}
          y={95}
          width={390}
          height={220}
          rx={8}
          className="fpga-chip-outline"
        />
        <Label x={280} y={124}>
          FPGA {powered ? "powered" : "power off"}
        </Label>
        <Wire
          d="M20 185H145M245 185H315M420 185H540"
          active={powered && configured}
        />
        <path
          d="M85 173L103 185L85 197Z M457 173L475 185L457 197Z"
          className="fpga-gate"
        />
        <Block
          x={145}
          y={153}
          label="LUT"
          detail={powered && configured ? "Rule loaded" : "No settings"}
          kind="config"
        />
        <FlipFlop
          x={315}
          y={145}
          value={powered && configured ? "Working bit" : "—"}
        />
        <Label x={32} y={163} small>
          Input
        </Label>
        <Label x={527} y={163} small>
          Output
        </Label>
        {roles ? (
          <>
            <Block
              x={150}
              y={252}
              w={265}
              h={43}
              label={
                powered
                  ? "BRAM · working data"
                  : "BRAM · contents lost"
              }
              kind="memory"
            />
          </>
        ) : (
          <>
            <Wire d="M367 230V270" />
            <Label x={367} y={294} small>
              Clock
            </Label>
          </>
        )}
        <Label x={280} y={350} small>
          {roles
            ? "Storage technology and storage job are different ideas."
            : "Pins and I/O buffers form the electrical boundary."}
        </Label>
      </Figure>
      {roles && (
        <div className="fpga-controls">
          <button
            type="button"
            onClick={() => {
              setPowered(!powered);
              setConfigured(false);
            }}
          >
            {powered ? "Power off" : "Power on"}
          </button>
          <button
            type="button"
            disabled={!powered || configured}
            onClick={() => setConfigured(true)}
          >
            Load configuration
          </button>
        </div>
      )}
      <p className="fpga-status" role="status">
        {roles
          ? !powered
            ? "Flash keeps the file. SRAM configuration and working state do not survive power loss."
            : configured
              ? "Settings choose the circuit. Registers and BRAM hold its working data."
              : "Power has returned. Configuration must be loaded before this circuit can run."
          : "A signal follows the configured logic path. A clock edge captures its result before output."}
      </p>
    </>
  );
};

export const ConfigureFigure = ({ scene }: { scene: string }) => {
  const [powered, setPowered] = useState(true);
  const [configured, setConfigured] = useState(false);
  const [width, setWidth] = useState(4);
  const [loads, setLoads] = useState(0);
  const parameter = scene === "running-parameters";
  const ready = parameter || configured;

  return (
    <>
      <Figure
        title={
          parameter
            ? `The working parameter width is ${width}. Configuration and routing remain fixed.`
            : "A bitstream loads the SRAM settings that choose LUT functions and routes. This is separate from the working signal path."
        }
      >
        <Block
          x={45}
          y={35}
          w={160}
          h={63}
          label="Flash or host"
          detail="Configuration file"
          kind="config"
        />
        <Wire d="M205 67H310V115" control active={ready && powered} />
        <Label x={358} y={67} small>
          Configuration interface
        </Label>
        <rect
          x={95}
          y={115}
          width={365}
          height={205}
          rx={8}
          className="fpga-chip-outline"
        />
        <Label x={280} y={145}>
          FPGA ·{" "}
          {powered ? (ready ? "configured" : "awaiting settings") : "power off"}
        </Label>
        <Block
          x={130}
          y={175}
          w={140}
          h={65}
          label="Pulse circuit"
          detail={powered && ready ? "Fixed arrangement" : "Not running"}
        />
        <Wire d="M270 207H340M95 207H130" active={powered && ready} />
        <Block
          x={340}
          y={175}
          w={85}
          h={65}
          label="Output"
          detail={powered && ready ? "Pulses" : "—"}
          kind="storage"
        />
        <Block
          x={180}
          y={260}
          w={180}
          h={40}
          label={`Working width ${width}`}
          kind="storage"
        />
        <Label x={280} y={354} small>
          {parameter
            ? "A new parameter uses the existing circuit."
            : "Loading settings and running the circuit are separate activities."}
        </Label>
      </Figure>
      <div className="fpga-controls">
        {parameter ? (
          [4, 12].map((value) => (
            <button
              type="button"
              key={value}
              aria-pressed={width === value}
              onClick={() => setWidth(value)}
            >
              Write width {value}
            </button>
          ))
        ) : (
          <>
            <button
              type="button"
              disabled={!powered || configured}
              onClick={() => {
                setConfigured(true);
                setLoads((count) => count + 1);
              }}
            >
              Load bitstream
            </button>
            <button
              type="button"
              onClick={() => {
                setPowered(!powered);
                setConfigured(false);
              }}
            >
              {powered ? "Power off" : "Power on"}
            </button>
          </>
        )}
      </div>
      <p className="fpga-status" role="status">
        {parameter
          ? "The working register changes; LUT settings and routes stay fixed. Period-boundary handling was shown in the pulse example."
          : !powered
            ? "The SRAM settings are lost. The stored bitstream remains available outside the chip."
            : configured
              ? `Configuration loaded${loads > 1 ? ` ${loads} times` : ""}. The configured circuit can now run.`
              : "Load the stored bitstream to establish the circuit."}
      </p>
    </>
  );
};
