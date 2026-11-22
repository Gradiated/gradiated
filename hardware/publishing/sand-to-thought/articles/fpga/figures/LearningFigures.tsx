import { useState } from "react";
import { lookup } from "./model";
import type { Bit } from "./model";
import { BitControls, Block, Figure, Label, Wire } from "./drawing";

export const BitAdditionFigure = () => {
  const [a, setA] = useState<Bit>(1);
  const [b, setB] = useState<Bit>(1);
  const sum = lookup("XOR", a, b);
  const carry = lookup("AND", a, b);

  return (
    <>
      <Figure
        title={`Add the individual bits ${a} and ${b}. XOR produces sum ${sum}; AND produces carry ${carry}. The two-bit answer ${carry}${sum} represents ${a + b}.`}
        viewBox="0 0 440 330"
      >
        <Label x={60} y={76} value>
          A = {a}
        </Label>
        <Label x={60} y={244} value>
          B = {b}
        </Label>
        <Wire
          d="M60 90V108H170M105 108V220H170M60 224V132H170M60 224H130V244H170M280 120H360M280 232H360"
          active
        />
        <circle cx={105} cy={108} r={3} className="fpga-junction" />
        <circle cx={60} cy={224} r={3} className="fpga-junction" />
        <Block
          x={170}
          y={90}
          w={110}
          h={55}
          label="XOR LUT"
          detail="0 1 1 0"
          kind="config"
        />
        <Block
          x={170}
          y={202}
          w={110}
          h={55}
          label="AND LUT"
          detail="0 0 0 1"
          kind="config"
        />
        <Label x={360} y={98} small>
          Sum bit
        </Label>
        <Label x={360} y={147} value>
          {sum}
        </Label>
        <Label x={360} y={210} small>
          Carry bit
        </Label>
        <Label x={360} y={259} value>
          {carry}
        </Label>
        <Label x={220} y={309} value>
          {a} + {b} = {carry}
          {sum} in binary = {a + b}
        </Label>
      </Figure>
      <div className="fpga-controls">
        <BitControls
          name="A"
          value={a}
          onChange={() => setA(a === 0 ? 1 : 0)}
        />
        <BitControls
          name="B"
          value={b}
          onChange={() => setB(b === 0 ? 1 : 0)}
        />
      </div>
      <p className="fpga-status" role="status">
        The LUT settings stay fixed. Changing the inputs selects the sum and
        carry answers.
      </p>
    </>
  );
};

export const OurBoardFigure = () => (
  <>
    <Figure
      title="Simplified KV260 system. The K26 module contains a Zynq chip with fixed processors and programmable logic, alongside working memory and boot storage. This is a relationship diagram, not a chip floor plan."
      viewBox="0 0 440 370"
    >
      <rect
        x={16}
        y={14}
        width={408}
        height={341}
        rx={8}
        className="fpga-chip-outline"
      />
      <Label x={220} y={42}>
        Our KV260 starter kit
      </Label>
      <rect
        x={36}
        y={61}
        width={368}
        height={230}
        rx={6}
        className="fpga-chip-outline"
      />
      <Label x={220} y={85} small>
        K26 module
      </Label>
      <rect
        x={55}
        y={101}
        width={330}
        height={112}
        rx={6}
        className="fpga-chip-outline"
      />
      <Label x={220} y={124} small>
        Zynq UltraScale+ chip
      </Label>
      <Block
        x={69}
        y={144}
        w={125}
        h={53}
        label="CPU"
        detail="Runs software"
      />
      <Wire d="M194 170H246" />
      <Block
        x={246}
        y={144}
        w={125}
        h={53}
        label="FPGA logic"
        detail="LUTs, RAM, DSPs"
        kind="config"
      />
      <Wire d="M130 213V233M310 213V233" />
      <Block
        x={55}
        y={233}
        w={145}
        h={41}
        label="Working memory"
        kind="memory"
      />
      <Block
        x={240}
        y={233}
        w={145}
        h={41}
        label="Boot storage"
        kind="config"
      />
      <Label x={220} y={322} small>
        Carrier board · power and external connections
      </Label>
    </Figure>
    <p className="fpga-status">
      The FPGA resources are one part of the system. This simplified view omits
      other components and internal connections.
    </p>
  </>
);
