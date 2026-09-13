import { useId, useState, type ReactNode } from "react";
import {
  ArrowDown,
  ArrowRight,
  Check,
  CircleDashed,
  Minus,
  X,
} from "lucide-react";
import { paddingState } from "./models";
import "./explorers.css";

const Figure = ({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children: ReactNode;
}) => {
  const id = useId();
  return (
    <figure className="gemma-figure" aria-labelledby={id}>
      <header>
        <h3 id={id}>{title}</h3>
        <p>{intro}</p>
      </header>
      {children}
    </figure>
  );
};

const Result = ({
  label,
  before,
  after,
  scope,
}: {
  label: string;
  before: string;
  after: string;
  scope: string;
}) => (
  <figcaption className="gx-result">
    <span className="gx-eyebrow">Measured / {label}</span>
    <div className="gx-result-values">
      <span>{before}</span>
      <ArrowRight aria-hidden="true" size={24} strokeWidth={1.5} />
      <strong>{after}</strong>
    </div>
    <p>{scope}</p>
  </figcaption>
);

export const SpeculativeRingExplorer = () => {
  const [native, setNative] = useState(false);
  const mapping = [2, 11, 5, 14, 0, 9, 7, 12];
  const ringAfterWrap = [9, 2, 3, 4, 5, 6, 7, 8];
  return (
    <Figure
      title="Designing the KV cache to fit the model"
      intro="Knowing the model architecture up front allows you to design the inference engine around it."
    >
      <div
        className="gx-before-after"
        role="group"
        aria-label="Attention cache implementation"
      >
        <button aria-pressed={!native} onClick={() => setNative(false)}>
          SGLang
        </button>
        <button aria-pressed={native} onClick={() => setNative(true)}>
          Carat
        </button>
      </div>
      <div
        className={`gx-two-panels gx-cache-comparison ${native ? "is-native" : ""}`}
      >
        <section className="gx-panel">
          <h4>
            {native ? "1. Calculate the slot" : "1. Lookup the token slot"}
          </h4>
          {native ? (
            <>
              <div>
                <pre className="gx-formula">
                  <code>slot = (token_number - 1) % window_size</code>
                </pre>
                <div className="gx-cache-example">
                  <span>
                    Token 1
                    <ArrowRight aria-hidden="true" size={14} />
                    slot 0
                  </span>
                  <span>
                    Token 2
                    <ArrowRight aria-hidden="true" size={14} />
                    slot 1
                  </span>
                  <span className="gx-cache-ellipsis" aria-hidden="true">
                    …
                  </span>
                  <span>
                    Token 7
                    <ArrowRight aria-hidden="true" size={14} />
                    slot 6
                  </span>
                  <span>
                    Token 8
                    <ArrowRight aria-hidden="true" size={14} />
                    slot 7
                  </span>
                  <span className="is-wrap">
                    Token 9
                    <ArrowRight aria-hidden="true" size={14} />
                    slot 0
                  </span>
                </div>
              </div>
              <p>
                Slots are numbered 0–7. The first eight tokens fill them in
                order. Token 9 returns to slot 0 and replaces token 1.
              </p>
            </>
          ) : (
            <>
              <div className="gx-page-map">
                {mapping.map((slot, i) => (
                  <div key={i}>
                    <span>Token {i + 1}</span>
                    <ArrowRight aria-hidden="true" size={14} />
                    <strong>slot {slot}</strong>
                  </div>
                ))}
              </div>
              <p>
                SGLang stores a mapping for each token to a cache slot in
                memory.
              </p>
            </>
          )}
        </section>
        <section className="gx-panel">
          <h4>
            {native
              ? "2. Reuse slot 0 after slot 7"
              : "2. Slots in the shared pool"}
          </h4>
          {native ? (
            <>
              <svg
                className="gx-ring"
                viewBox="0 0 400 400"
                role="img"
                aria-label="Eight fixed slots after token nine replaces token one in slot zero"
              >
                <circle cx="200" cy="200" r="122" className="gx-ring-guide" />
                {ringAfterWrap.map((token, slot) => {
                  const angle = (slot / 8) * Math.PI * 2 - Math.PI / 2;
                  const x = 200 + Math.cos(angle) * 122;
                  const y = 200 + Math.sin(angle) * 122;
                  return (
                    <g
                      className={`gx-ring-cell ${slot === 0 ? "is-reused" : ""}`}
                      key={slot}
                    >
                      <title>{`Slot ${slot}, token ${token}`}</title>
                      <circle cx={x} cy={y} r="25" />
                      <text
                        className="gx-ring-slot-number"
                        x={200 + Math.cos(angle) * 172}
                        y={200 + Math.sin(angle) * 172}
                        dominantBaseline="central"
                      >
                        slot {slot}
                      </text>
                      <text
                        className="gx-ring-token"
                        x={x}
                        y={y}
                        dominantBaseline="central"
                      >
                        {token}
                      </text>
                    </g>
                  );
                })}
              </svg>
              <p>
                Token 9 now reuses slot 0 replacing Token 1 which is now outside
                of the sliding context window
              </p>
            </>
          ) : (
            <>
              <div className="gx-shared-pool">
                {Array.from({ length: 16 }, (_, slot) => {
                  const token = mapping.indexOf(slot) + 1;
                  return (
                    <div
                      key={slot}
                      className={`gx-token ${token ? "is-new" : ""}`}
                    >
                      <small>slot {slot}</small>
                      <strong>{token || "—"}</strong>
                    </div>
                  );
                })}
              </div>
              <p>
                Attention looks up the address for each slot, then reads the KV
                data at those addresses, which may be scattered randomly.
              </p>
            </>
          )}
        </section>
      </div>
    </Figure>
  );
};

export const AttentionShapeExplorer = () => {
  const [padded, setPadded] = useState(true);
  const state = paddingState(6005, 6004, padded);
  return (
    <Figure
      title="More FLOPs is better."
      intro="Padding the K matrix to be a multiple of 64 improves the execution speed significantly."
    >
      <div className="gx-controls">
        <div className="gx-switch" role="group" aria-label="Matrix extent">
          <button aria-pressed={!padded} onClick={() => setPadded(false)}>
            Exact
          </button>
          <button aria-pressed={padded} onClick={() => setPadded(true)}>
            Padded
          </button>
        </div>
      </div>
      <div className="gx-matrix-heading">
        <span>Earlier columns omitted</span>
        <span className="gx-label-with-icon">
          Last 64 columns
          <ArrowDown aria-hidden="true" size={12} />
        </span>
      </div>
      <div
        className="gx-matrix"
        role="img"
        aria-label={`${state.extent} physical columns. ${state.extra} padded columns excluded from attention.`}
      >
        {state.columns.map((c) => (
          <div
            key={c.index}
            className={`gx-matrix-cell is-${c.kind}`}
            title={`Key ${c.index}: ${c.kind}`}
          >
            <span>{c.index}</span>
            {c.kind === "padding" ? (
              <X aria-hidden="true" size={16} strokeWidth={2} />
            ) : c.kind === "future" ? (
              <Minus aria-hidden="true" size={16} strokeWidth={2} />
            ) : c.kind === "absent" ? (
              <CircleDashed aria-hidden="true" size={16} strokeWidth={2} />
            ) : (
              <Check aria-hidden="true" size={16} strokeWidth={2} />
            )}
          </div>
        ))}
      </div>
      <div className="gx-legend">
        <span>
          <Check aria-hidden="true" size={13} strokeWidth={2} />
          visible key
        </span>
        <span>
          <X aria-hidden="true" size={13} strokeWidth={2} />
          padding masked
        </span>
        <span>
          <CircleDashed aria-hidden="true" size={13} strokeWidth={2} />
          not allocated
        </span>
      </div>
      <div className="gx-bars">
        <span className="gx-eyebrow">Measured time · global attention QK</span>
        <div>
          <label>
            6,005 keys <strong>0.830 ms</strong>
          </label>
          <i style={{ width: "100%" }} />
        </div>
        <div>
          <label>
            6,016 keys <strong>0.105 ms</strong>
          </label>
          <i
            className="gx-fast-bar"
            style={{ width: `${(100 * 0.105) / 0.83}%` }}
          />
        </div>
      </div>
      <p className="gx-footnote">
        Measured on a H200 with BF16 Q and K matricies.
      </p>
    </Figure>
  );
};

export const Fp8DataflowExplorer = () => {
  const [optimized, setOptimized] = useState(false);
  const values = [
    [2, -1, 4, 0],
    [8, -3, 1, 2],
  ];
  const maxima = values.map((row) => Math.max(...row.map(Math.abs)));
  return (
    <Figure
      title="Find the largest value without reading everything twice."
      intro="FP8 stores numbers using fewer bits. Before converting a layer’s output, we find its largest absolute value and use it to set the conversion scale."
    >
      <div
        className="gx-before-after"
        role="group"
        aria-label="Finding the maximum"
      >
        <button aria-pressed={!optimized} onClick={() => setOptimized(false)}>
          Before: read it again
        </button>
        <button aria-pressed={optimized} onClick={() => setOptimized(true)}>
          After: save the maximum
        </button>
      </div>
      <div className="gx-number-flow">
        <section className="gx-panel">
          <span className="gx-eyebrow">1. Produce the values</span>
          <h4>
            {optimized
              ? "Save a maximum for each row"
              : "Write the activation tensor"}
          </h4>
          <div className="gx-number-rows">
            {values.map((row, i) => (
              <div key={i} className="gx-number-row">
                <span className="gx-row-name">Row {i + 1}</span>
                <div className="gx-row-values">
                  {row.map((value, j) => (
                    <span
                      key={j}
                      className={`gx-number ${optimized && Math.abs(value) === maxima[i] ? "is-largest" : ""}`}
                    >
                      {value}
                    </span>
                  ))}
                </div>
                {optimized && (
                  <span className="gx-saved-max">max {maxima[i]}</span>
                )}
              </div>
            ))}
          </div>
          <p>
            {optimized
              ? "The producer already has these values. It records each row’s maximum while writing the row."
              : "The producer finishes writing. The next operation still needs to find the maximum."}
          </p>
        </section>
        <div className="gx-flow-arrow" aria-hidden="true">
          <ArrowDown size={22} strokeWidth={1.5} />
        </div>
        <section className="gx-panel">
          <span className="gx-eyebrow">2. Find the tensor’s maximum</span>
          <h4>
            {optimized
              ? "Read two saved numbers"
              : "Read all eight values again"}
          </h4>
          <div className="gx-number-scan">
            {(optimized ? maxima : values.flat()).map((v, i) => (
              <span
                className={`gx-number ${v === 8 ? "is-largest" : ""}`}
                key={i}
              >
                {v}
              </span>
            ))}
            <ArrowRight
              aria-hidden="true"
              className="gx-number-arrow"
              size={22}
              strokeWidth={1.5}
            />
            <strong className="gx-final-max">8</strong>
          </div>
          <p>
            {optimized
              ? "The maximum of the row maxima is also the maximum of the whole tensor."
              : "Scan the full tensor to find the largest absolute value: 8."}
          </p>
        </section>
        <div className="gx-flow-arrow" aria-hidden="true">
          <ArrowDown size={22} strokeWidth={1.5} />
        </div>
        <div className="gx-unchanged">
          <strong>3. Convert to FP8 using the same scale</strong>
          <span>
            Both approaches find 8. The conversion still reads the activation
            values.
          </span>
        </div>
      </div>
      <div className="gx-simple-takeaway" aria-live="polite">
        {optimized
          ? "We avoid a full read just to find the maximum. We pass a small summary to the next kernel instead."
          : "The extra work is the full-tensor scan between producing the values and converting them."}
      </div>
      <div className="gx-real-size">
        <span className="gx-eyebrow">
          At a real Gemma shape · 64 rows × 5,376 values
        </span>
        <div>
          <span>
            Activation scan removed<strong>672 KiB</strong>
          </span>
          <span>
            Saved summary<strong>256 bytes</strong>
          </span>
        </div>
        <p>
          Each conversion block reads the same 256-byte summary instead of
          running a separate scan over the 672 KiB activation.
        </p>
      </div>
      <details className="gx-details">
        <summary>Why keep separate kernels instead of fusing them?</summary>
        <p>
          A fused kernel still has to wait for every block’s values before it
          knows the global maximum. Our cooperative GELU fusion improved a fixed
          test but did not improve live traffic.
        </p>
        <p>
          The retained RMSNorm implementation keeps separate launches. Each
          conversion block independently reduces the small row-max vector.
          Repeating that small calculation avoids a grid-wide barrier inside
          conversion.
        </p>
        <p>
          The saved maxima come from the BF16-rounded values, preserving the
          original tensor scale and FP8 bytes for the same inputs. These are
          related experiments, not a three-way timing comparison of one
          operator.
        </p>
      </details>
      <Result
        label="whole verifier · 0.99% faster"
        before="23.6713 ms"
        after="23.4379 ms"
        scope="Measured on H200 · batch 16 · four draft tokens · 6,000-token context."
      />
    </Figure>
  );
};

export const EngineArchitecture = () => {
  const [global, setGlobal] = useState(false);
  return (
    <Figure
      title="Attention layers in Gemma 4"
      intro="Gemma splits its 60 layers into 10 groups of six layers. Five layers use a short attention window, then one looks across the full history. That pattern repeats ten times."
    >
      <div className="gx-model-flow">
        <div>
          <strong>Input tokens</strong>
          <span>Convert token IDs into vectors</span>
        </div>
        <span className="gx-model-arrow" aria-hidden="true">
          <ArrowDown size={18} strokeWidth={1.5} />
        </span>
        <span className="gx-footnote">
          Layers run left to right, then continue on the next row.
        </span>
        <section
          className="gx-model-layers"
          aria-label="60 layers: ten groups of five local layers followed by one global layer"
        >
          {Array.from({ length: 10 }, (_, row) => (
            <div className="gx-layer-row" key={row}>
              <span>
                {row * 6 + 1}–{row * 6 + 6}
              </span>
              {Array.from({ length: 6 }, (_, col) => {
                const full = col === 5;
                return (
                  <span
                    key={col}
                    className={`gx-model-layer ${full ? "is-global" : "is-local"} ${full === global ? "is-selected" : ""}`}
                    title={`Layer ${row * 6 + col + 1}: ${full ? "global" : "local"} attention`}
                  >
                    {full ? "G" : "L"}
                  </span>
                );
              })}
            </div>
          ))}
        </section>
        <span className="gx-model-arrow" aria-hidden="true">
          <ArrowDown size={18} strokeWidth={1.5} />
        </span>
        <div>
          <strong>Next-token scores</strong>
          <span>Choose a token, then repeat</span>
        </div>
      </div>
      <div
        className="gx-before-after"
        role="group"
        aria-label="Layer attention type"
      >
        <button aria-pressed={!global} onClick={() => setGlobal(false)}>
          Local · 50 layers
        </button>
        <button aria-pressed={global} onClick={() => setGlobal(true)}>
          Global · 10 layers
        </button>
      </div>
      <section className="gx-panel gx-model-detail" aria-live="polite">
        <h4>
          {global ? "Read the full history" : "Read the latest 1,024 tokens"}
        </h4>
        <div className="gx-history-label">
          <span>Start of conversation</span>
          <span className="gx-history-current">
            Current token{" "}
            <ArrowDown aria-hidden="true" size={12} strokeWidth={1.8} />
          </span>
        </div>
        <div
          className="gx-model-history"
          role="img"
          aria-label={
            global
              ? "All 6,144 token positions visible"
              : "Latest 1,024 of 6,144 token positions visible"
          }
        >
          {Array.from({ length: 48 }, (_, i) => (
            <span key={i} className={global || i >= 40 ? "is-visible" : ""} />
          ))}
        </div>
        <p>
          <strong>
            {global ? "Keep the history." : "Reuse the old slots."}
          </strong>{" "}
          {global
            ? "These layers need their earlier keys and values as the conversation grows. A fixed 1,024-token ring would lose data they still need."
            : "These layers no longer read keys and values outside the window. A 1,024-slot ring can replace old entries as new tokens arrive."}
        </p>
      </section>
    </Figure>
  );
};
