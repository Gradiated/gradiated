import type { ReactNode } from "react";
import { logicColours } from "./materials";
import { inverterOperation } from "./process";

export const InverterViews = ({
  input,
  progress,
  children,
}: {
  input: number;
  progress: number;
  children: ReactNode;
}) => {
  const electrical = inverterOperation(input, progress);
  const inputColour = input ? logicColours.high : logicColours.low;
  const outputColour = input ? logicColours.low : logicColours.high;
  const output = electrical.output ?? "…";
  const signal = (d: string, colour: string, amount: number) => (
    <g
      fill="none"
      stroke={colour}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="1"
      strokeDashoffset={1 - amount}
      opacity={amount > 0 ? 1 : 0}
    >
      <path d={d} pathLength="1" strokeWidth="9" opacity=".13" />
      <path d={d} pathLength="1" strokeWidth="3" />
    </g>
  );

  return (
    <div
      className="fab-inverter-views"
      data-input={input}
      data-output={electrical.output ?? "settling"}
    >
      <svg
        className="fab-inverter-symbol"
        viewBox="0 0 420 110"
        role="img"
        aria-label={`NOT gate symbol. Input ${input}, output ${output}.`}
      >
        <g fill="none" stroke="var(--fab-ink)" strokeWidth="1.8">
          <path d="M45 48H180 M250 48H375" />
          <path d="M180 19 235 48 180 77Z" />
          <circle cx="243" cy="48" r="7" />
        </g>
        {signal("M45 48H180", inputColour, electrical.input)}
        {signal("M250 48H375", outputColour, electrical.exit)}
        <g fontSize="16" textAnchor="middle">
          <text x="85" y="85" fill={inputColour}>
            Input = {input}
          </text>
          <text
            x="337"
            y="85"
            fill={
              electrical.output === undefined
                ? "var(--fab-muted)"
                : outputColour
            }
          >
            Output = {output}
          </text>
          <text x="203" y="105" fill="var(--fab-muted)" fontSize="13">
            NOT
          </text>
        </g>
      </svg>
      <div className="fab-inverter-details">
        <svg
          className="fab-inverter-circuit"
          viewBox="0 0 240 280"
          role="img"
          aria-label={`Two-transistor inverter. The ${input ? "n" : "p"}-type transistor connects the output to ${input ? "0" : "+1"} volts.`}
        >
          <g
            fill="none"
            stroke="var(--fab-ink)"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M140 35V70H125 M125 110H140V180H125 M125 220H140V245 M140 140H215" />
            <path d="M125 70V110 M110 75V105 M125 180V220 M110 185V215" />
            <path d="M25 140H80 M80 90V200H110 M80 90H102" />
            <circle cx="106" cy="90" r="4" />
            <circle cx="140" cy="140" r="2.5" fill="var(--fab-ink)" />
            <circle cx="80" cy="140" r="2.5" fill="var(--fab-ink)" />
            <path d="M126 35H154 M128 245H152 M132 250H148 M137 255H143" />
          </g>
          {signal("M140 35V70H125", logicColours.high, 1)}
          {signal("M125 220H140V245", logicColours.low, 1)}
          {signal("M25 140H80", inputColour, electrical.input)}
          {signal("M80 140V90H102", inputColour, electrical.gates)}
          {signal("M80 140V200H110", inputColour, electrical.gates)}
          {signal("M110 75V105", inputColour, electrical.electrodes)}
          {signal("M110 185V215", inputColour, electrical.electrodes)}
          {signal(
            input
              ? "M140 245V220H125V180H140V140"
              : "M140 35V70H125V110H140V140",
            outputColour,
            electrical.transfer,
          )}
          {signal("M140 140H215", outputColour, electrical.exit)}
          <g fontSize="16" fill="var(--fab-muted)">
            <text x="140" y="22" textAnchor="middle" fill={logicColours.high}>
              +1 V
            </text>
            <text x="140" y="275" textAnchor="middle" fill={logicColours.low}>
              0 V
            </text>
            <text x="171" y="85">
              p-type
            </text>
            <text
              x="171"
              y="103"
              fontSize="13"
              opacity={electrical.electrodes}
              fill={input === 0 ? outputColour : "var(--fab-muted)"}
            >
              {input === 0 ? "on" : "off"}
            </text>
            <text x="171" y="195">
              n-type
            </text>
            <text
              x="171"
              y="213"
              fontSize="13"
              opacity={electrical.electrodes}
              fill={input === 1 ? outputColour : "var(--fab-muted)"}
            >
              {input === 1 ? "on" : "off"}
            </text>
            <text x="25" y="128" textAnchor="middle" fill={inputColour}>
              Input
            </text>
            <text
              x="194"
              y="128"
              textAnchor="middle"
              fill={
                electrical.output === undefined
                  ? "var(--fab-muted)"
                  : outputColour
              }
            >
              Output
            </text>
          </g>
        </svg>
        <figure
          className="fab-detail-panel"
          aria-label="The same inverter in silicon"
        >
          {children}
        </figure>
      </div>
    </div>
  );
};
