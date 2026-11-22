import type { MachineId } from "./model";
import { siliconColours } from "./materials";

export const MachineIcon = ({ machine }: { machine: MachineId }) => (
  <svg viewBox="0 0 100 86" aria-hidden="true" className="fab-machine-svg">
    <path d="M13 70 48 82 91 63 56 52Z" fill="currentColor" opacity=".08" />
    <path d="m14 25 36-15 35 15v42L50 81 14 67Z" fill="var(--fab-paper)" />
    <path d="m14 25 36 14 35-14M50 39v42M14 25l36-15 35 15v42L50 81 14 67Z" />
    {machine === "litho" ? (
      <>
        <path d="M29 26 50 18 70 26 50 34ZM50 34v17m-8-3 8 14 8-14M22 60l20 8 28-11" />
        <path d="m28 41 12 5m-12 5 12 5" />
      </>
    ) : null}
    {machine === "furnace" || machine === "anneal" ? (
      <>
        <path d="m21 45 22 9v18l-22-9Zm4-9c-5-7 5-8 0-15m8 18c-5-7 5-8 0-15m30 21 14-6v23l-14 6Z" />
        <path d="m25 53 12 5m-12 3 12 5" />
      </>
    ) : null}
    {machine === "coat" || machine === "polish" ? (
      <>
        <ellipse cx="50" cy="27" rx="22" ry="9" />
        <path d="M34 25q16 12 32 0m-20 1 5 4 7-3m-6 14v11m10-7v11m-40-1 20 8" />
        {machine === "coat" ? (
          <path d="M48 13v9m0-9 15-5" />
        ) : (
          <path d="m32 23 12-4 15 5-11 5Z" />
        )}
      </>
    ) : null}
    {machine === "implant" ? (
      <>
        <path d="m25 23 18 7 20-9m-21 9v17m-7-4 7 11 7-6m13-9v17l14-5V34Z" />
        <path d="m22 60 20 8m-17-9v-3m8 7v-3m7 6v-3" />
      </>
    ) : null}
    {machine === "etch" || machine === "deposit" || machine === "metal" ? (
      <>
        <ellipse cx="50" cy="26" rx="19" ry="8" />
        <path d="M31 26v9q19 14 38 0v-9m-28 9v12m9-10v14m9-16v12m-37 9 19 8" />
        {machine === "deposit" || machine === "metal" ? (
          <path d="m23 60 18 8m-18-3 18 8" />
        ) : (
          <path d="m25 55 5-2 5 2" />
        )}
      </>
    ) : null}
    {machine === "develop" || machine === "strip" ? (
      <>
        <path d="m24 31 16 6 23-9-16-6Zm0 0v15l16 6 23-9V28m-34 8v7m7-4v7m11-8v7m10-11v7" />
        <path d="m23 60 17 7" />
      </>
    ) : null}
    {machine === "inspect" ? (
      <>
        <circle cx="48" cy="28" r="11" />
        <path d="m56 36 12 10M38 28h20m-10-10v20m-25 22 20 8 25-10m-47-8 12 5" />
      </>
    ) : null}
    <circle cx="76" cy="58" r="2" fill="currentColor" stroke="none" />
  </svg>
);

export const Wafer = ({ patterned = true }: { patterned?: boolean }) => (
  <svg viewBox="0 0 180 90" aria-hidden="true" className="fab-wafer-svg">
    <defs>
      <clipPath id="fab-wafer-disc">
        <ellipse cx="90" cy="41" rx="69" ry="25" />
      </clipPath>
    </defs>
    <ellipse cx="90" cy="58" rx="72" ry="22" fill="#ded7cb" opacity=".5" />
    <path
      d="M21 41v6c0 15 31 27 69 27s69-12 69-27v-6"
      fill={siliconColours.side}
      stroke="currentColor"
      strokeWidth="1.2"
    />
    <ellipse
      cx="90"
      cy="41"
      rx="69"
      ry="25"
      fill={siliconColours.top}
      stroke="currentColor"
      strokeWidth="1.2"
    />
    {patterned ? (
      <g
        clipPath="url(#fab-wafer-disc)"
        stroke={siliconColours.hatch}
        strokeWidth=".8"
      >
        {Array.from({ length: 9 }, (_, n) => (
          <path key={`v${n}`} d={`M${26 + n * 16} 10v64`} />
        ))}
        {Array.from({ length: 5 }, (_, n) => (
          <path key={`h${n}`} d={`M10 ${17 + n * 12}h160`} />
        ))}
      </g>
    ) : null}
    <path
      d="m84 65 6-5 6 5"
      fill="var(--fab-paper)"
      stroke="currentColor"
      strokeWidth="1"
    />
  </svg>
);

const region = {
  silicon: siliconColours.top,
  oxide: "#c8d8dc",
  resist: "#d9bdcb",
  poly: "#a4b7a0",
  n: "#9ebfb3",
  p: "#cba4a2",
  metal: "#8f9aab",
};

export const FabricationDrawing = ({
  index,
  progress,
  input,
}: {
  index: number;
  progress: number;
  input: number;
}) => {
  const stage = index === 0 ? 18 : index;
  const reveal = (at: number) => (stage > at ? 1 : stage === at ? progress : 0);
  const isPatterning = stage >= 4 && stage <= 9;
  const well = reveal(9);
  const isolation = reveal(10);
  const gateOxide = reveal(11);
  const poly = reveal(12);
  const patternedGate = reveal(13);
  const implant = reveal(14);
  const contacts = index === 0 ? 0 : reveal(16);
  const metal = reveal(17);
  const complete = stage >= 17;
  const residualResist = stage < 8 ? 1 : stage === 8 ? 1 - progress : 0;
  const openResist = stage >= 6;
  const openOxide = stage >= 7;
  const processLayer = stage >= 4 && stage <= 9;

  if (index === 20) {
    return (
      <svg
        viewBox="0 0 600 450"
        className="fab-drawing"
        role="img"
        aria-label="A patterned wafer, an individual die and a chip package"
      >
        <text x="32" y="30" className="fab-svg-eyebrow">
          MANY COPIES, MADE TOGETHER
        </text>
        <g transform="translate(20 45) scale(2.1)">
          <Wafer />
        </g>
        <path d="M348 139h35m-8-6 8 6-8 6" className="fab-svg-wire" />
        <g transform="translate(420 94)">
          <rect
            width="82"
            height="82"
            rx="3"
            fill={region.silicon}
            stroke="currentColor"
          />
          <path
            d="M12 12h58v58H12Z M22 22h38v38H22Z M32 32h18v18H32Z"
            fill="none"
            stroke="#8f9aab"
          />
          <text x="41" y="109" textAnchor="middle">
            One die
          </text>
        </g>
        <path d="M460 223v40m-6-8 6 8 6-8" className="fab-svg-wire" />
        <g transform="translate(377 278)">
          <path
            d="m0 30 83-29 83 29v39l-83 29L0 69Z"
            fill="#ddd5c9"
            stroke="currentColor"
          />
          <path
            d="m0 30 83 29 83-29m-83 29v39"
            fill="none"
            stroke="currentColor"
          />
          <path
            d="m43 28 40-14 40 14-40 14Z"
            fill={region.metal}
            stroke="currentColor"
          />
          {Array.from({ length: 5 }, (_, n) => (
            <path
              key={n}
              d={`m${12 + n * 15} ${73 + n * 5} -13 6m${94 + n * 15} ${94 - n * 5} 13 6`}
              stroke="currentColor"
            />
          ))}
        </g>
        <text x="60" y="320">
          Inspect the structures.
        </text>
        <text x="60" y="350">
          Test the connections.
        </text>
        <text x="60" y="380">
          Connect the chip to the world.
        </text>
      </svg>
    );
  }

  return (
    <svg
      viewBox="0 0 600 450"
      className="fab-drawing"
      role="img"
      aria-label={`${complete ? "Connected planar NOT gate" : "Planar transistor fabrication"}, with a top view above a matching cross-section`}
    >
      <defs>
        <pattern
          id="fab-si-hatch"
          width="9"
          height="9"
          patternUnits="userSpaceOnUse"
        >
          <path d="M0 9 9 0" stroke={siliconColours.hatch} strokeWidth=".65" />
        </pattern>
        <pattern
          id="fab-oxide-hatch"
          width="8"
          height="8"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="3" cy="3" r=".7" fill="#718f96" />
        </pattern>
        <clipPath id="fab-body-clip">
          <rect x="40" y="270" width="520" height="112" rx="2" />
        </clipPath>
      </defs>
      <text x="32" y="14" className="fab-svg-eyebrow">
        TOP VIEW
      </text>
      <rect
        x="40"
        y="38"
        width="520"
        height="130"
        rx="4"
        fill={region.silicon}
        fillOpacity=".45"
        stroke="#b8ac99"
      />
      <rect
        x="330"
        y="38"
        width={230 * well}
        height="130"
        rx="4"
        fill={region.n}
        fillOpacity=".45"
      />
      {processLayer ? (
        <g fill={region.oxide}>
          <rect x="40" y="38" width={openOxide ? 290 : 520} height="130" />
          {openOxide ? <rect x="550" y="38" width="10" height="130" /> : null}
        </g>
      ) : null}
      {isolation > 0 ? (
        <g opacity={isolation}>
          <rect
            x="40"
            y="38"
            width="520"
            height="130"
            rx="4"
            fill={region.oxide}
          />
          <rect
            x="80"
            y="76"
            width="160"
            height="50"
            fill={region.silicon}
            stroke="#a99d89"
          />
          <rect
            x="360"
            y="76"
            width="160"
            height="50"
            fill={region.n}
            stroke="#74978b"
          />
        </g>
      ) : null}
      {poly > 0 ? (
        <g opacity={poly} fill={region.poly} stroke="#60725c">
          {stage < 13 ? (
            <rect x="40" y="48" width="520" height="110" fillOpacity=".8" />
          ) : (
            <>
              <rect x="147" y="58" width="26" height="98" />
              <rect x="427" y="58" width="26" height="98" />
              {complete ? (
                <path d="M160 156v14h280v-14" strokeWidth="6" fill="none" />
              ) : null}
            </>
          )}
        </g>
      ) : null}
      {implant > 0 ? (
        <g opacity={implant}>
          {[95, 173].map((x) => (
            <rect
              key={x}
              x={x}
              y="81"
              width={x === 95 ? 52 : 57}
              height="40"
              fill={region.n}
              stroke="#608a79"
            />
          ))}
          {[375, 453].map((x) => (
            <rect
              key={x}
              x={x}
              y="81"
              width={x === 375 ? 52 : 57}
              height="40"
              fill={region.p}
              stroke="#9f7472"
            />
          ))}
        </g>
      ) : null}
      {stage >= 4 && stage <= 8 ? (
        <g fill={region.resist} opacity={residualResist * 0.9}>
          <rect
            x="40"
            y="38"
            width={stage === 4 ? 520 * progress : openResist ? 290 : 520}
            height="130"
          />
          {openResist ? <rect x="550" y="38" width="10" height="130" /> : null}
        </g>
      ) : null}
      {stage === 5 ? (
        <rect
          x="330"
          y="38"
          width="220"
          height="130"
          fill="#e5d2ed"
          opacity={0.3 + 0.3 * progress}
        />
      ) : null}
      {complete ? (
        <g
          fill="none"
          stroke={region.metal}
          strokeWidth="7"
          strokeLinejoin="round"
        >
          <path d="M60 55v46h55M60 55V42M540 42v59h-50M210 101V48h180v53M300 48V32" />
          <path d="M160 170h280" stroke={region.poly} strokeWidth="6" />
        </g>
      ) : null}
      {contacts > 0 ? (
        <g
          opacity={contacts}
          fill={complete ? "#5c6677" : "#f7f3ec"}
          stroke="currentColor"
          strokeWidth="1"
        >
          {[60, 115, 210, 390, 490, 540].map((x) => (
            <rect key={x} x={x - 5} y="96" width="10" height="10" />
          ))}
        </g>
      ) : null}
      {complete ? (
        <>
          <text x="60" y="32" textAnchor="middle" className="fab-svg-value">
            0 V
          </text>
          <text x="540" y="32" textAnchor="middle" className="fab-svg-value">
            1 V
          </text>
          <text x="300" y="22" textAnchor="middle" className="fab-svg-value">
            Q = {1 - input}
          </text>
          <text x="300" y="192" textAnchor="middle" className="fab-svg-value">
            A = {input}
          </text>
          <path
            d={input ? "M60 42v59h150V48h90V32" : "M540 42v59H390V48h-90V32"}
            className="fab-svg-signal"
          />
        </>
      ) : null}
      {!complete ? (
        <>
          <path
            d="M30 102h540"
            stroke="#736c62"
            strokeDasharray="4 5"
            strokeWidth="1"
          />
          <text x="24" y="107" textAnchor="end" className="fab-svg-small">
            a
          </text>
          <text x="576" y="107" className="fab-svg-small">
            a
          </text>
          <text x="300" y="191" textAnchor="middle" className="fab-svg-small">
            The dotted line cuts through the view below
          </text>
        </>
      ) : null}
      <text x="32" y="225" className="fab-svg-eyebrow">
        CROSS-SECTION
      </text>
      <g transform="translate(0 30)">
        <g clipPath="url(#fab-body-clip)">
          <rect x="40" y="270" width="520" height="112" fill={region.silicon} />
          <rect
            x="40"
            y="270"
            width="520"
            height="112"
            fill="url(#fab-si-hatch)"
          />
          <rect
            x="330"
            y="270"
            width={230 * well}
            height="100"
            rx="20"
            fill={region.n}
            fillOpacity=".75"
          />
        </g>
        {processLayer ? (
          <g>
            <rect
              x="40"
              y="256"
              width={openOxide ? 290 : 520}
              height="14"
              fill={region.oxide}
              stroke="#708f98"
            />
            {openOxide ? (
              <rect
                x="550"
                y="256"
                width="10"
                height="14"
                fill={region.oxide}
                stroke="#708f98"
              />
            ) : null}
            {residualResist > 0 && stage <= 8 ? (
              <g opacity={residualResist} fill={region.resist} stroke="#9c7789">
                <rect
                  x="40"
                  y="237"
                  width={stage === 4 ? 520 * progress : openResist ? 290 : 520}
                  height="19"
                />
                {openResist ? (
                  <rect x="550" y="237" width="10" height="19" />
                ) : null}
              </g>
            ) : null}
            {stage === 5 ? (
              <g stroke="#b094c8" strokeWidth="3" opacity={progress}>
                {[350, 390, 430, 470, 510, 535].map((x) => (
                  <path key={x} d={`M${x} 207v28m-4-7 4 7 4-7`} />
                ))}
              </g>
            ) : null}
          </g>
        ) : null}
        {isolation > 0 ? (
          <g opacity={isolation} fill={region.oxide} stroke="#708f98">
            {[
              [40, 40],
              [240, 120],
              [520, 40],
            ].map(([x, width]) => (
              <rect key={x} x={x} y="250" width={width} height="30" rx="5" />
            ))}
          </g>
        ) : null}
        {gateOxide > 0 ? (
          <g opacity={gateOxide} fill={region.oxide} stroke="#708f98">
            {[80, 360].map((x) => (
              <rect key={x} x={x} y="264" width="160" height="6" />
            ))}
          </g>
        ) : null}
        {poly > 0 ? (
          <g opacity={poly} fill={region.poly} stroke="#60725c">
            {stage < 13 ? (
              <rect x="40" y="241" width="520" height={23 * poly} />
            ) : (
              <>
                <rect
                  x="40"
                  y="241"
                  width="520"
                  height="23"
                  opacity={1 - patternedGate}
                />
                <rect x="147" y="241" width="26" height="23" />
                <rect x="427" y="241" width="26" height="23" />
              </>
            )}
          </g>
        ) : null}
        {implant > 0 ? (
          <g opacity={implant}>
            {[90, 173].map((x) => (
              <rect
                key={x}
                x={x}
                y="270"
                width="57"
                height="24"
                rx="3"
                fill={region.n}
                stroke="#608a79"
              />
            ))}
            {[370, 453].map((x) => (
              <rect
                key={x}
                x={x}
                y="270"
                width="57"
                height="24"
                rx="3"
                fill={region.p}
                stroke="#9f7472"
              />
            ))}
            <rect x="55" y="280" width="15" height="20" fill={region.p} />
            <rect x="533" y="280" width="15" height="20" fill={region.n} />
          </g>
        ) : null}
        {stage === 9 || stage === 14 ? (
          <g
            stroke="#638f80"
            strokeWidth="2"
            opacity={Math.sin(progress * Math.PI)}
          >
            {(stage === 9
              ? [355, 390, 425, 460, 495, 530]
              : [100, 115, 130, 190, 205, 220, 380, 395, 410, 470, 485, 500]
            ).map((x) => (
              <path key={x} d={`M${x} 215v48m-3-6 3 6 3-6`} />
            ))}
          </g>
        ) : null}
        {contacts > 0 ? (
          <g opacity={contacts}>
            <rect
              x="40"
              y="208"
              width="520"
              height="61"
              fill={region.oxide}
              fillOpacity=".82"
            />
            <rect
              x="40"
              y="208"
              width="520"
              height="61"
              fill="url(#fab-oxide-hatch)"
            />
            {[60, 115, 160, 210, 390, 440, 490, 540].map((x) => (
              <rect
                key={x}
                x={x - 5}
                y="208"
                width="10"
                height={
                  x === 160 || x === 440 ? 33 : x === 60 || x === 540 ? 72 : 62
                }
                fill={complete ? region.metal : "var(--fab-paper)"}
                stroke={complete ? "#5c6677" : "#708f98"}
              />
            ))}
            {complete ? (
              <path
                d="M40 208h520"
                stroke={region.metal}
                strokeWidth="9"
                strokeDasharray="40 22 52 18 55 20 46 28 50 22 45 25"
              />
            ) : null}
          </g>
        ) : null}
        {stage === 19 ? (
          <g opacity={progress}>
            <rect
              x="40"
              y="181"
              width="520"
              height="23"
              fill={region.oxide}
              fillOpacity=".8"
            />
            <path
              d="M120 176h120m60 0h175M325 181v27"
              fill="none"
              stroke={region.metal}
              strokeWidth="9"
            />
            <path
              d="M325 176v-15h75"
              fill="none"
              stroke="#55687f"
              strokeWidth="2"
            />
            <text x="409" y="165" className="fab-svg-small">
              via
            </text>
          </g>
        ) : null}
        <path d="M40 270v112h520V270" fill="none" stroke="#9e8f7b" />
        <text
          x="175"
          y="343"
          textAnchor="middle"
          className="fab-svg-small"
          style={{ fill: siliconColours.label }}
        >
          p-type silicon
        </text>
        {well > 0 ? (
          <text
            x="445"
            y="343"
            textAnchor="middle"
            className="fab-svg-small"
            opacity={well}
          >
            n-well
          </text>
        ) : null}
        {(stage >= 13 && stage <= 15) || index === 0 ? (
          <>
            <path d="M160 239v-20h-45" fill="none" stroke="#60725c" />
            <text x="106" y="221" textAnchor="end" className="fab-svg-small">
              gate
            </text>
          </>
        ) : null}
        {implant > 0 ? (
          <>
            {[115, 210].map((x) => (
              <text
                x={x}
                y="286"
                textAnchor="middle"
                className="fab-svg-small"
                key={x}
              >
                n+
              </text>
            ))}
            {[395, 485].map((x) => (
              <text
                x={x}
                y="286"
                textAnchor="middle"
                className="fab-svg-small"
                key={x}
              >
                p+
              </text>
            ))}
          </>
        ) : null}
        {complete ? (
          <>
            <path
              d={input ? "M147 273h26" : "M427 273h26"}
              className="fab-svg-signal"
            />
            <text
              x="160"
              y="366"
              textAnchor="middle"
              className="fab-svg-small"
              style={{ fill: siliconColours.label }}
            >
              n-type · {input ? "on" : "off"}
            </text>
            <text x="440" y="366" textAnchor="middle" className="fab-svg-small">
              p-type · {input ? "off" : "on"}
            </text>
          </>
        ) : null}
        {stage === 11 ? (
          <>
            <path d="M160 265v-24h-45" fill="none" stroke="#708f98" />
            <text x="106" y="242" textAnchor="end" className="fab-svg-small">
              gate oxide
            </text>
          </>
        ) : null}
      </g>
      {isPatterning ? (
        <text x="300" y="440" textAnchor="middle" className="fab-svg-small">
          Temporary resist selects where the material changes
        </text>
      ) : (
        <text x="300" y="440" textAnchor="middle" className="fab-svg-small">
          Planar transistors · thicknesses exaggerated
        </text>
      )}
    </svg>
  );
};
