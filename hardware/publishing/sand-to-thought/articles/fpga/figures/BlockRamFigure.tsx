import { useContext, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { FigureSlot } from "./FigureSlot";
import { Figure, Label, Wire } from "./drawing";

const binary = (word: number, width = 4) =>
  word.toString(2).padStart(width, "0");

const Bits = ({ word, x, y }: { word: number; x: number; y: number }) => (
  <g className="fpga-bram-word">
    {[...binary(word)].map((bit, i) => (
      <Label
        key={i}
        x={x + (i - 1.5) * 19}
        y={y}
        value
        className={`fpga-bram-bit fpga-bram-bit--${bit}`}
      >
        {bit}
      </Label>
    ))}
  </g>
);

type Operation = {
  kind: "write" | "read";
  address: number;
  word: number;
  id: number;
  announce: boolean;
};

export const BlockRamFigure = () => {
  const active = useContext(FigureSlot)?.active !== false;
  const [words, setWords] = useState([0, 0, 0, 0]);
  const [read, setRead] = useState<number | null>(null);
  const [location, setLocation] = useState(0);
  const [incoming, setIncoming] = useState(3);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [automatic, setAutomatic] = useState(true);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);
  const controls = useRef<HTMLDivElement>(null);
  const remainingAddresses = useRef<number[]>([]);
  const serial = useRef(0);
  const [last, setLast] = useState(
    "This example starts with sixteen zero bits. Choose an address and write data, then select Write or Read.",
  );
  const writing = operation?.kind === "write";

  useEffect(() => {
    const element = controls.current;
    if (!element) return;

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let intersecting = false;
    const update = () => {
      setVisible(intersecting && !document.hidden);
      setReduced(media.matches);
    };
    const observer = new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      update();
    });
    observer.observe(element.closest(".fpga-stage") ?? element);
    document.addEventListener("visibilitychange", update);
    media.addEventListener("change", update);
    update();

    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
      media.removeEventListener("change", update);
    };
  }, []);

  useEffect(() => {
    if (!active || !visible || reduced || !automatic || operation) return;

    const timer = window.setTimeout(
      () => {
        if (!remainingAddresses.current.length) {
          const addresses = [0, 1, 2, 3];
          for (let i = addresses.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [addresses[i], addresses[j]] = [addresses[j], addresses[i]];
          }
          remainingAddresses.current = addresses;
        }

        const address = remainingAddresses.current.pop()!;
        const word = (words[address] + 1 + Math.floor(Math.random() * 15)) % 16;
        setLocation(address);
        setIncoming(word);
        setOperation({
          kind: "write",
          address,
          word,
          id: ++serial.current,
          announce: false,
        });
      },
      serial.current === 0 ? 1000 : 600,
    );

    return () => window.clearTimeout(timer);
  }, [active, automatic, operation, reduced, visible, words]);

  useEffect(() => {
    if (!active || !operation) return;

    if (!visible || reduced) {
      setOperation(null);
      return;
    }

    const capture = window.setTimeout(() => {
      if (operation.kind === "write") {
        setWords((previous) =>
          previous.map((word, i) =>
            i === operation.address ? operation.word : word,
          ),
        );
      } else {
        setRead(operation.word);
      }
      if (operation.announce) {
        setLast(
          `${operation.kind === "write" ? "Wrote" : "Read"} ${binary(operation.word)} (${operation.word}) ${operation.kind === "write" ? "into" : "from"} address ${binary(operation.address, 2)}.`,
        );
      }
    }, 900);
    const finish = window.setTimeout(() => setOperation(null), 1500);

    return () => {
      window.clearTimeout(capture);
      window.clearTimeout(finish);
    };
  }, [active, operation, reduced, visible]);

  const pause = () => {
    setAutomatic(false);
    setOperation(null);
    setLast("Automatic writes paused. Choose an address and write data.");
  };

  const begin = (kind: Operation["kind"]) => {
    setAutomatic(false);
    const word = kind === "write" ? incoming : words[location];
    if (reduced) {
      if (kind === "write") {
        setWords((previous) =>
          previous.map((stored, i) => (i === location ? word : stored)),
        );
      } else {
        setRead(word);
      }
      setLast(
        `${kind === "write" ? "Wrote" : "Read"} ${binary(word)} (${word}) ${kind === "write" ? "into" : "from"} address ${binary(location, 2)}.`,
      );
      return;
    }

    setLast(
      kind === "write"
        ? "Write enable opens the gate. Waiting for the clock edge to save the new value."
        : "Waiting for the clock edge to read the selected value.",
    );
    setOperation({
      kind,
      address: location,
      word,
      id: ++serial.current,
      announce: true,
    });
  };

  return (
    <>
      <Figure
        title={`This simplified BRAM has four rows of four SRAM bits. Red means 0 and green means 1. This teaching example starts with zeros. The two-bit address ${binary(location, 2)} selects the highlighted row. The four-bit write data is ${binary(incoming)}. A small barrier illustrates write enable: closed at 0, open at 1. Opening it permits a write, but the row changes only when the clock pulse arrives. The read output shows the last value it received until the next read. Automatic writes visit shuffled addresses and overwrite their data. Pause to inspect a result, or choose your own address and write data. Write and Read demonstrate individual operations in slow motion.`}
      >
        <g
          className="fpga-bram-circuit"
          data-operation={operation?.kind ?? "idle"}
          data-writing={writing}
          data-automatic={automatic && visible && !reduced}
        >
          <Label x={326} y={64}>
            SRAM cells
          </Label>
          <g className="fpga-resource-bus">
            <Wire d="M20 114H220" active bus={{ x: 177, y: 114 }} />
            <Wire d="M20 202H160" active bus={{ x: 121, y: 202 }} />
            <Wire d="M168 202H220" active={writing} />
            <Wire
              d="M432 180H550"
              active={read !== null}
              bus={{ x: 452, y: 180 }}
            />
          </g>
          <Label x={86} y={87} small>
            Address
          </Label>
          <Label x={86} y={145} value>
            {binary(location, 2)}
          </Label>
          <Label x={86} y={179} small>
            Write data
          </Label>
          <Bits word={incoming} x={86} y={234} />
          <Label x={492} y={155} small>
            Read data
          </Label>
          {read === null ? (
            <Label x={492} y={214} value>
              —
            </Label>
          ) : (
            <Bits word={read} x={492} y={214} />
          )}

          <rect
            x={220}
            y={92}
            width={212}
            height={184}
            rx={4}
            className="fpga-bram-array"
          />
          <rect
            x={222}
            y={94 + location * 44}
            width={208}
            height={44}
            rx={3}
            className="fpga-selected-row fpga-bram-selected"
          />
          {words.map((word, row) => (
            <g
              key={row}
              className="fpga-bram-row"
              data-address={row}
              data-word={binary(word)}
            >
              <Label
                x={242}
                y={123 + row * 44}
                value
                className="fpga-bram-address"
              >
                {binary(row, 2)}
              </Label>
              {[...binary(word)].map((bit, column) => (
                <g
                  key={column}
                  className={`fpga-bram-cell fpga-bram-bit--${bit}`}
                >
                  <rect
                    x={258 + column * 44}
                    y={98 + row * 44}
                    width={36}
                    height={36}
                    rx={3}
                  />
                  <Label
                    key={bit}
                    x={276 + column * 44}
                    y={123 + row * 44}
                    value
                  >
                    {bit}
                  </Label>
                </g>
              ))}
            </g>
          ))}

          <Wire d="M164 292V220" control active={writing} />
          <Label x={82} y={299} small>
            Write enable
          </Label>
          <Label
            x={145}
            y={324}
            value
            className={`fpga-bram-bit fpga-bram-bit--${writing ? 1 : 0}`}
          >
            {writing ? 1 : 0}
          </Label>
          <g className="fpga-bram-gate" data-open={writing}>
            <path d="M164 220V184" />
          </g>
          <circle cx={164} cy={220} r={3} className="fpga-bram-hinge" />
          <Wire d="M326 332V276" />
          <path d="M318 276l8 -10 8 10" className="fpga-wire" />
          <Label x={326} y={359} small>
            Clock
          </Label>

          {operation && (
            <g
              key={operation.id}
              className="fpga-bram-operation"
              aria-hidden="true"
            >
              <circle
                r={4}
                className="fpga-bram-clock-packet"
                style={{ offsetPath: 'path("M326 332V276")' } as CSSProperties}
              />
              {writing ? (
                <>
                  <circle
                    r={5}
                    className="fpga-bram-write-packet"
                    style={
                      { offsetPath: 'path("M20 202H220")' } as CSSProperties
                    }
                  />
                  <rect
                    x={256}
                    y={96 + operation.address * 44}
                    width={172}
                    height={40}
                    rx={4}
                    className="fpga-bram-capture"
                  />
                </>
              ) : (
                <circle
                  r={5}
                  className="fpga-bram-read-packet"
                  style={
                    { offsetPath: 'path("M432 180H550")' } as CSSProperties
                  }
                />
              )}
            </g>
          )}
        </g>
      </Figure>
      <div
        className="fpga-controls"
        role="group"
        aria-label="BRAM address"
        ref={controls}
      >
        <span>Address</span>
        {[0, 1, 2, 3].map((i) => (
          <button
            type="button"
            key={i}
            aria-pressed={location === i}
            onClick={() => {
              pause();
              setLocation(i);
            }}
          >
            {i}
          </button>
        ))}
        {!reduced && (
          <button
            type="button"
            aria-label={
              automatic ? "Pause automatic writes" : "Resume automatic writes"
            }
            onClick={() => {
              if (automatic) {
                pause();
              } else {
                setAutomatic(true);
                setOperation(null);
                setLast("Automatic writes resumed.");
              }
            }}
          >
            {automatic ? "Pause" : "Auto write"}
          </button>
        )}
      </div>
      <div
        className="fpga-controls fpga-bram-controls"
        role="group"
        aria-label="BRAM operations"
      >
        <label>
          Write data
          <select
            value={incoming}
            onFocus={pause}
            onChange={(event) => {
              pause();
              setIncoming(Number(event.target.value));
            }}
          >
            {Array.from({ length: 16 }, (_, word) => (
              <option key={word} value={word}>
                {word}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          aria-label={`Write ${incoming} to address ${location}`}
          onClick={() => begin("write")}
        >
          Write
        </button>
        <button
          type="button"
          aria-label={`Read address ${location}`}
          onClick={() => begin("read")}
        >
          Read
        </button>
      </div>
      <p className="sr-only" role="status">
        {last}
      </p>
    </>
  );
};
