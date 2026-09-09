import { useEffect, useId, useState } from "react";
import { ArrowDown, ArrowRight, Ellipsis } from "lucide-react";
import "./explorers.css";
import "./speculative-attention.css";

const heads = Array.from({ length: 8 }, (_, head) => head);
const queries = heads.flatMap((head) =>
  Array.from({ length: 4 }, (_, position) => ({ head, position })),
);
const colors = [
  "#246957",
  "#497baf",
  "#aa6339",
  "#8564a6",
  "#967324",
  "#a85475",
  "#39878b",
  "#647345",
];
function Matrix({
  label,
  shape,
  wide = false,
  cached = false,
  short = false,
  singleHead = false,
  head = 0,
}: {
  label: string;
  shape: string;
  wide?: boolean;
  cached?: boolean;
  short?: boolean;
  singleHead?: boolean;
  head?: number;
}) {
  return (
    <div className={`sa-operand ${wide ? "sa-wide" : ""}`}>
      <strong>{label}</strong>
      <div
        className={`sa-matrix ${short ? "sa-short" : ""} ${singleHead ? "sa-single-head" : ""}`}
        aria-hidden="true"
      >
        {Array.from({ length: singleHead ? 4 : short ? 8 : 32 }, (_, row) => (
          <div
            key={row}
            style={{
              backgroundColor: cached
                ? "var(--muted)"
                : colors[singleHead ? head : Math.floor(row / 4)],
            }}
          />
        ))}
      </div>
      <span>{shape}</span>
    </div>
  );
}

export function SpeculativeAttentionExplorer() {
  const id = useId();
  const [mode, setMode] = useState<"sglang" | "carat">("sglang");
  const [playing, setPlaying] = useState(false);
  const [tick, setTick] = useState(0);
  const carat = mode === "carat";
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), 650);
    return () => window.clearInterval(timer);
  }, [playing]);
  useEffect(() => {
    if (tick >= 4) setPlaying(false);
  }, [tick]);
  function select(next: "sglang" | "carat") {
    setMode(next);
    setTick(0);
    setPlaying(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  const phase = Math.min(tick, 3);

  return (
    <>
      <figure
        className="gemma-figure sa-explorer"
        aria-labelledby={`${id}-title`}
      >
        <header>
          <h3 id={`${id}-title`}>
            Optimizing attention for speculative decoding
          </h3>
          <p>
            Eight query heads share one KV head. Each head has four query
            positions on a forward pass with speculative decoding.
          </p>
        </header>
        <div
          className="sa-tabs"
          role="group"
          aria-label="Attention implementation"
        >
          <button aria-pressed={!carat} onClick={() => select("sglang")}>
            SGLang
          </button>
          <button aria-pressed={carat} onClick={() => select("carat")}>
            Carat
          </button>
        </div>
        <div className="sa-work">
          <section className="sa-queries" aria-label="Query arrangement">
            <h4>
              {carat
                ? "Query rows grouped together"
                : "Four positions for each head"}
            </h4>
            <svg
              viewBox="0 0 220 450"
              role="img"
              aria-label={
                carat
                  ? "All 32 queries packed into one matrix. Head colors are preserved."
                  : "Eight head rows, each with positions q0 through q3."
              }
            >
              {!carat &&
                [0, 1, 2, 3].map((q) => (
                  <text
                    key={q}
                    x={64 + q * 43}
                    y="24"
                    textAnchor="middle"
                    className="sa-axis"
                  >
                    q{q}
                  </text>
                ))}
              {!carat &&
                heads.map((h) => (
                  <text key={h} x="12" y={61 + h * 48} className="sa-axis">
                    h{h}
                  </text>
                ))}
              {queries.map(({ head, position }) => {
                const row = head * 4 + position;
                return (
                  <g
                    key={row}
                    className="sa-query"
                    style={{
                      transform: `translate(${carat ? 57 : 46 + position * 43}px, ${carat ? 14 + row * 13.3 : 41 + head * 48}px)`,
                    }}
                  >
                    <rect
                      width={carat ? 114 : 36}
                      height={carat ? 11 : 31}
                      rx="3"
                      fill={colors[head]}
                    />
                    <text
                      x={carat ? 57 : 18}
                      y={carat ? 8.5 : 20}
                      textAnchor="middle"
                      className={carat ? "sa-packed-label" : "sa-cell-label"}
                    >
                      {carat ? `h${head} q${position}` : `q${position}`}
                    </text>
                  </g>
                );
              })}
            </svg>
            <div className="sa-query-feed" aria-hidden="true">
              <ArrowRight size={20} />
            </div>
          </section>
          <section
            className="sa-execution"
            aria-label={`${carat ? "Carat" : "SGLang"} execution structure`}
          >
            <h4>
              {carat
                ? "32 rows, processed together"
                : "Eight heads, working in parallel"}
            </h4>
            {carat ? (
              <div className="sa-matrix-flow">
                <div
                  className="sa-equation"
                  data-active={phase === 0}
                  role="img"
                  aria-label="Q, 32 by d, times cached keys transposed, d by N, produces scores, 32 by N."
                >
                  <Matrix label="Q" shape="32 × d" />
                  <span className="sa-operator">×</span>
                  <Matrix label="Cached Kᵀ" shape="d × N" wide cached short />
                  <span className="sa-operator">=</span>
                  <Matrix label="Scores" shape="32 × N" wide />
                </div>
                <div className="sa-softmax-bridge" data-active={phase === 1}>
                  <ArrowDown size={18} aria-hidden="true" />
                  <strong>Mask + softmax</strong>
                  <ArrowDown size={18} aria-hidden="true" />
                </div>
                <div
                  className="sa-equation"
                  data-active={phase >= 2}
                  role="img"
                  aria-label="Weights, 32 by N, times cached values, N by d, produces output, 32 by d."
                >
                  <Matrix label="Weights" shape="32 × N" wide />
                  <span className="sa-operator">×</span>
                  <Matrix label="Cached V" shape="N × d" cached />
                  <span className="sa-operator">=</span>
                  <Matrix label="Output" shape="32 × d" />
                </div>
                <p className="sa-small sa-dimensions">
                  N = cached tokens · d = head width
                </p>
              </div>
            ) : (
              <div className="sa-fused sa-independent">
                {[1, 2, null].map((head) =>
                  head === null ? (
                    <div
                      className="sa-head-omission"
                      key="omitted"
                      aria-label="Other heads omitted"
                    >
                      <Ellipsis size={22} aria-hidden="true" />
                    </div>
                  ) : (
                    <div
                      className="sa-head-flow"
                      key={head}
                      style={{
                        backgroundColor: `color-mix(in srgb, ${colors[head]} 8%, var(--paper))`,
                      }}
                      aria-label={`Head ${head}: independent attention calculation`}
                    >
                      <div className="sa-fusion-label">
                        <strong style={{ color: colors[head] }}>
                          Head {head}
                        </strong>
                        <strong>Fused</strong>
                      </div>
                      <div className="sa-equation">
                        <Matrix
                          label="Q"
                          shape="4 × d"
                          singleHead
                          head={head}
                        />
                        <span className="sa-operator">×</span>
                        <Matrix
                          label="Kᵀ chunk"
                          shape="d × C"
                          wide
                          cached
                          short
                        />
                        <span className="sa-operator">=</span>
                        <Matrix
                          label="Scores"
                          shape="4 × C"
                          wide
                          singleHead
                          head={head}
                        />
                      </div>
                      <div className="sa-head-softmax">
                        <ArrowDown size={16} aria-hidden="true" />
                        <strong>Mask + softmax</strong>
                      </div>
                      <div className="sa-equation">
                        <Matrix
                          label="Weights"
                          shape="4 × C"
                          wide
                          singleHead
                          head={head}
                        />
                        <span className="sa-operator">×</span>
                        <Matrix label="V chunk" shape="C × d" cached short />
                        <span className="sa-operator">=</span>
                        <Matrix
                          label="Partial output"
                          shape="4 × d"
                          singleHead
                          head={head}
                        />
                      </div>
                    </div>
                  ),
                )}
                <p className="sa-small sa-dimensions">
                  C = tokens in one chunk · d = head width
                </p>
              </div>
            )}
          </section>
        </div>
        <div
          className="gx-bars sa-measurement"
          aria-live="polite"
          aria-atomic="true"
        >
          <h4>Measured global-attention core</h4>
          <div>
            <label>
              SGLang <strong>1.60 ms</strong>
            </label>
            <i style={{ width: "100%" }} aria-hidden="true" />
          </div>
          <div>
            <label>
              Carat <strong>0.099 ms</strong>
            </label>
            <i
              className="gx-fast-bar"
              style={{ width: `${(100 * 0.099) / 1.6}%` }}
              aria-hidden="true"
            />
          </div>
        </div>
      </figure>
    </>
  );
}
