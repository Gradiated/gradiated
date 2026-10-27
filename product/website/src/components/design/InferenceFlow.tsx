import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactElement, ReactNode } from "react";
import { ModelPicker, OPEN_MODELS } from "./ModelPicker";
import { PhoneFlow } from "./PhoneFlow";

/**
 * The inference machine, from one application's seat — the loop fold's
 * sibling, built on the same chassis: the product mock card on the left
 * (model selector pill over the phone render), the endpoint field and a
 * vertical stack on the right, one canvas drawing the traffic over the DOM's
 * rectangles.
 *
 * The story is the inference pitch: choose an open model (the selector),
 * set the latency your workload actually needs (the service-class control),
 * and the requests run phone → endpoint → scheduler → model and stream back
 * as signal-green tokens — faster and solo in real time, slower and in
 * convoys on batch, which is where the savings live.
 */

const MODELS = OPEN_MODELS;

/* The traffic's two poles; the slider interpolates between them. 0 is
   real-time (fast, solo bits), 1 is batch (slow convoys, packed — where
   the savings story lives). */
const REALTIME = { speed: 1.7, group: 1, period: 0.85 } as const;
const BATCH = { speed: 0.55, group: 4, period: 3.8 } as const;
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

const TOKENS = 6;
const TOKEN_GAP = 0.085;

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeIO = (t: number): number =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

type P = { x: number; y: number };

export const InferenceFlow = ({
  header,
}: {
  /** Rendered above the fold's title — the machine toggle lives here. */
  header?: ReactNode;
} = {}): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mockRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const tileRefs = useRef<(HTMLDivElement | null)[]>([]);

  const [model, setModel] = useState(0);
  const modelRef = useRef(model);
  modelRef.current = model;
  /* 0 = real-time, 1 = batch; opens on batch. */
  const [latency, setLatency] = useState(1);
  const latencyRef = useRef(latency);
  latencyRef.current = latency;

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!host || !canvas || !ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const root = host.closest<HTMLElement>(".gr-root") ?? document.body;

    let inkBit = "#211e19";
    let inkGreen = "#2fd655";
    let inkWire = "#c9c2b2";
    const readInk = () => {
      const styles = getComputedStyle(root);
      inkBit = styles.getPropertyValue("--color-text").trim() || inkBit;
      inkGreen =
        styles.getPropertyValue("--color-signal-green").trim() || inkGreen;
      inkWire = styles.getPropertyValue("--color-rule").trim() || inkWire;
    };
    readInk();
    const themeObserver = new MutationObserver(readInk);
    themeObserver.observe(root, { attributeFilter: ["data-theme"] });

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const size = () => {
      const rect = host.getBoundingClientRect();
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    };
    size();
    const resizeObserver = new ResizeObserver(size);
    resizeObserver.observe(host);

    /* Two orthogonal runs, the loop fold's drafting style: OUT is phone →
       field → one straight drop into the models box; HOME leaves the box's
       floor, runs left under the copy, and climbs back into the phone — the
       response arriving where the request was born. */
    const paths = (
      narrow: boolean,
    ): { outA: P[]; outB: P[]; home: P[] } | null => {
      const hostRect = host.getBoundingClientRect();
      const mock = mockRef.current?.getBoundingClientRect();
      const field = fieldRef.current?.getBoundingClientRect();
      const box = rowRefs.current[0]?.getBoundingClientRect();
      const copy = copyRef.current?.getBoundingClientRect();
      const tile = tileRefs.current[modelRef.current]?.getBoundingClientRect();
      if (!mock || !field || !box || !tile) return null;
      const rel = (x: number, y: number): P => ({
        x: x - hostRect.left,
        y: y - hostRect.top,
      });
      if (narrow) {
        /* The phone column is stacked above on a phone, so the diagram is
           just the conversation: one rail down (request), one rail up
           (the response, in inference green). */
        const cx = tile.left + tile.width / 2;
        return {
          outA: [],
          outB: [rel(cx - 9, field.bottom), rel(cx - 9, tile.top)],
          home: [rel(cx + 9, tile.top), rel(cx + 9, field.bottom)],
        };
      }
      const fieldY = field.top + field.height / 2;
      const dropX = Math.min(
        field.right - 14,
        Math.max(field.left + 14, box.left + box.width / 2),
      );
      const railY =
        Math.max(mock.bottom, box.bottom, copy ? copy.bottom : 0) + 48;
      const homeX = mock.left + mock.width * 0.12;
      /* Two disjoint out wires — the request ENTERS the field and
         re-emerges from its floor, like the mock; no diagonal between. */
      return {
        outA: [rel(mock.right, fieldY), rel(field.left, fieldY)],
        outB: [rel(dropX, field.bottom), rel(dropX, tile.top)],
        home: [
          rel(dropX, tile.bottom),
          rel(dropX, railY),
          rel(homeX, railY),
          rel(homeX, mock.bottom),
        ],
      };
    };

    /* Distance-true travel along a polyline — constant speed through the
       corners. */
    const along = (pts: P[], t: number): P => {
      const lens: number[] = [];
      let total = 0;
      for (let i = 0; i < pts.length - 1; i++) {
        const l = Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y);
        lens.push(l);
        total += l;
      }
      let d = clamp01(t) * total;
      for (let i = 0; i < lens.length; i++) {
        if (d <= lens[i] || i === lens.length - 1) {
          const u = lens[i] === 0 ? 0 : clamp01(d / lens[i]);
          return {
            x: pts[i].x + (pts[i + 1].x - pts[i].x) * u,
            y: pts[i].y + (pts[i + 1].y - pts[i].y) * u,
          };
        }
        d -= lens[i];
      }
      return pts[pts.length - 1];
    };

    const square = (p: P, s: number, fill: string, alpha: number) => {
      ctx.globalAlpha = alpha;
      ctx.fillStyle = fill;
      ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
      ctx.globalAlpha = 1;
    };

    let rafId = 0;
    let visible = false;
    const start = performance.now();

    const frame = () => {
      rafId = 0;
      if (!visible) return;
      const k = latencyRef.current;
      const lat = {
        speed: mix(REALTIME.speed, BATCH.speed, k),
        group: Math.round(mix(REALTIME.group, BATCH.group, k)),
        period: mix(REALTIME.period, BATCH.period, k),
      };
      const narrow = window.matchMedia("(max-width: 900px)").matches;
      const t = (performance.now() - start) / 1000;
      const p = paths(narrow);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
      if (!p) {
        rafId = requestAnimationFrame(frame);
        return;
      }

      /* The standing wires: ruler lines, same ink as the lattice. */
      ctx.strokeStyle = inkWire;
      ctx.lineWidth = 1;
      for (const wire of [p.outA, p.outB, p.home]) {
        if (wire.length < 2) continue;
        ctx.beginPath();
        ctx.moveTo(wire[0].x, wire[0].y);
        for (let i = 1; i < wire.length; i++) ctx.lineTo(wire[i].x, wire[i].y);
        ctx.stroke();
      }

      if (reduced.matches) {
        rafId = requestAnimationFrame(frame);
        return;
      }

      const OUT = 1.25 / lat.speed;
      const DWELL = 0.25 / lat.speed;
      const BACK = 1.5 / lat.speed;
      const span = OUT + DWELL + BACK + TOKENS * TOKEN_GAP;

      for (let g = 0; g < lat.group; g++) {
        const shifted = t - g * 0.16;
        const first = Math.max(0, Math.floor((shifted - span) / lat.period));
        for (let wave = first; wave * lat.period <= shifted; wave++) {
          const local = shifted - wave * lat.period;
          if (local < 0 || local > span) continue;
          if (local < OUT) {
            const u = local / OUT;
            if (narrow) {
              square(along(p.outB, u), 5, inkBit, 0.9);
            } else if (u < 0.42) {
              /* Through the field: wire A, a beat inside, then wire B. */
              square(along(p.outA, u / 0.42), 5, inkBit, 0.9);
            } else if (u > 0.52) {
              square(along(p.outB, (u - 0.52) / 0.48), 5, inkBit, 0.9);
            }
          } else if (local > OUT + DWELL) {
            for (let k = 0; k < TOKENS; k++) {
              const tk = (local - OUT - DWELL - k * TOKEN_GAP) / BACK;
              if (tk <= 0 || tk >= 1) continue;
              square(along(p.home, tk), 4, inkGreen, 0.95);
            }
          }
        }
      }

      rafId = requestAnimationFrame(frame);
    };

    const run = () => {
      if (rafId === 0 && visible) rafId = requestAnimationFrame(frame);
    };
    const halt = () => {
      if (rafId !== 0) cancelAnimationFrame(rafId);
      rafId = 0;
    };

    /* Same two jobs as the loop's observer: run the canvas only on screen,
       and release the entrance gesture the first time it arrives. */
    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible) {
          host.classList.add("gr-loop--seen");
          run();
        } else halt();
      },
      { rootMargin: "60px" },
    );
    io.observe(host);

    const onReduced = () => {
      halt();
      run();
    };
    reduced.addEventListener("change", onReduced);

    return () => {
      halt();
      io.disconnect();
      resizeObserver.disconnect();
      themeObserver.disconnect();
      reduced.removeEventListener("change", onReduced);
    };
  }, []);

  return (
    <section className="gr-loop gr-inf" ref={hostRef}>
      <canvas className="gr-loop-canvas" ref={canvasRef} />
      <div className="gr-loop-grid">
        <div className="gr-loop-left">
          <div
            className="gr-loop-mock gr-enter"
            ref={mockRef}
            style={{ "--enter-delay": "0.1s" } as CSSProperties}
          >
            <PhoneFlow />
          </div>
          <div
            className="gr-loop-copy gr-enter"
            ref={copyRef}
            style={{ "--enter-delay": "0.3s" } as CSSProperties}
          >
            <p>
              Choose an open model, then set the latency your workload actually
              needs.
            </p>
            <p>
              We handle the infrastructure behind one API, so you get serious
              savings without giving up reliability, technical depth, or a
              provider you can trust.
            </p>
          </div>
        </div>

        <div className="gr-loop-right">
          {header}
          <h2 className="gr-heading gr-loop-title gr-enter">
            Choose your model <br />
            and latency.
          </h2>
          <div
            className="gr-loop-controls gr-enter"
            style={{ "--enter-delay": "0.2s" } as CSSProperties}
          >
            <div className="gr-loop-field" ref={fieldRef}>
              <span>https://api.gradiated.com</span>
              <span className="gr-loop-caret" />
            </div>
            <ModelPicker onChange={setModel} value={model} />
          </div>
          <div
            className="gr-inf-slider gr-enter"
            style={{ "--enter-delay": "0.25s" } as CSSProperties}
          >
            <span className="gr-inf-slider-label">Real-time</span>
            <input
              aria-label="Latency"
              max={100}
              min={0}
              onChange={(event) =>
                setLatency(Number(event.currentTarget.value) / 100)
              }
              type="range"
              value={Math.round(latency * 100)}
            />
            <span className="gr-inf-slider-label">Batch</span>
          </div>
          <div
            className="gr-loop-stack gr-enter"
            style={{ "--enter-delay": "0.35s" } as CSSProperties}
          >
            <div
              className="gr-loop-row gr-inf-row"
              ref={(el) => {
                rowRefs.current[0] = el;
              }}
            >
              <span className="gr-loop-rowlabel">Open models</span>
              <div className="gr-inf-tiles">
                {MODELS.map((item, tileIndex) => {
                  /* The chosen model takes the centre slot — under the
                     wire — and the others step aside; selection moves the
                     MODELS, never the path. */
                  const others = MODELS.map((_, i) => i).filter(
                    (i) => i !== model,
                  );
                  const slot =
                    tileIndex === model
                      ? 0
                      : others.indexOf(tileIndex) === 0
                        ? -1
                        : 1;
                  return (
                    <div
                      aria-label={item.name}
                      className="gr-inf-tile"
                      data-active={tileIndex === model || undefined}
                      key={item.name}
                      ref={(el) => {
                        tileRefs.current[tileIndex] = el;
                      }}
                      style={{ "--slot": slot } as CSSProperties}
                      title={item.name}
                    >
                      <img alt="" src={item.src} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
