import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { PointerEvent, ReactElement } from "react";

import { illustrativeRouterPrompts, operatingPoint, routerCurve } from "./data";
import type { RouterPoint } from "./data";

const SMALL_COST = 1;
const LARGE_COST = 6;
const PAD = { top: 18, right: 20, bottom: 44, left: 46 };

const pct = (value: number, digits = 0) => `${(value * 100).toFixed(digits)}%`;

export const RouterFrontier = (): ReactElement => {
  const [drop, setDrop] = useState(0.02);
  const [hover, setHover] = useState<RouterPoint | null>(null);
  const sliderId = useId();
  const box = useRef<HTMLElement>(null);
  const [W, setW] = useState(640);
  const H = W < 480 ? 280 : 300;

  /* Drawn at its real width, so the axis text stays legible on a phone
     instead of being scaled down with the drawing. */
  useEffect(() => {
    const element = box.current;
    if (!element) return;

    const observer = new ResizeObserver(([entry]) => {
      setW(Math.max(280, Math.min(720, Math.round(entry.contentRect.width))));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const curve = useMemo(
    () => routerCurve(illustrativeRouterPrompts(), SMALL_COST, LARGE_COST),
    [],
  );
  const fallback = curve[0];
  const allSmall = curve[curve.length - 1];
  const chosen = operatingPoint(curve, drop);

  const qualities = curve.map((point) => point.quality);
  const yMin = Math.floor((Math.min(...qualities) - 0.03) * 20) / 20;
  const yMax = Math.ceil((Math.max(...qualities) + 0.02) * 20) / 20;
  const xMin = Math.floor(allSmall.relativeCost * 10) / 10;
  const x = (cost: number) =>
    PAD.left + ((cost - xMin) / (1 - xMin)) * (W - PAD.left - PAD.right);
  const y = (quality: number) =>
    PAD.top + ((yMax - quality) / (yMax - yMin)) * (H - PAD.top - PAD.bottom);

  const path = curve
    .map(
      (point, i) =>
        `${i ? "L" : "M"}${x(point.relativeCost).toFixed(1)},${y(point.quality).toFixed(1)}`,
    )
    .join(" ");
  const yTicks = Array.from(
    { length: Math.round((yMax - yMin) / 0.05) + 1 },
    (_, i) => yMin + i * 0.05,
  );
  const xStep = W < 480 ? 0.2 : 0.1;
  const xTicks = Array.from(
    { length: Math.floor((1 - xMin) / xStep + 1e-9) + 1 },
    (_, i) => 1 - i * xStep,
  );
  const focus = hover ?? chosen;

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * W;
    const nearest = curve.reduce((best, point) =>
      Math.abs(x(point.relativeCost) - px) < Math.abs(x(best.relativeCost) - px)
        ? point
        : best,
    );
    setHover(nearest);
  };

  return (
    <figure className="gr-dx gr-dx-frontier" ref={box}>
      <div className="gr-dx-frontier-head">
        <div className="gr-dx-field">
          <label htmlFor={sliderId}>
            max_quality_drop <strong>{pct(drop, 1)}</strong>
          </label>
          <input
            id={sliderId}
            max={0.1}
            min={0}
            onChange={(event) => setDrop(Number(event.target.value))}
            step={0.005}
            type="range"
            value={drop}
          />
        </div>
        <dl className="gr-dx-facts gr-dx-facts--four">
          <div>
            <dt>offload_rate</dt>
            <dd>{pct(focus.offload)}</dd>
          </div>
          <div>
            <dt>routed_quality</dt>
            <dd>{pct(focus.quality, 1)}</dd>
          </div>
          <div>
            <dt>quality_drop</dt>
            <dd>{pct(fallback.quality - focus.quality, 1)}</dd>
          </div>
          <div>
            <dt>cost_savings_pct</dt>
            <dd>{pct(1 - focus.relativeCost)}</dd>
          </div>
        </dl>
      </div>

      <svg
        aria-label={`Quality against cost for every routing threshold. At a ${pct(drop, 1)} allowed drop the router offloads ${pct(chosen.offload)} of prompts and saves ${pct(1 - chosen.relativeCost)}.`}
        className="gr-dx-frontier-chart"
        onPointerLeave={() => setHover(null)}
        onPointerMove={onPointerMove}
        role="img"
        viewBox={`0 0 ${W} ${H}`}
      >
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className="gr-dx-grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text
              className="gr-dx-axis"
              textAnchor="end"
              x={PAD.left - 8}
              y={y(tick) + 4}
            >
              {pct(tick)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <text
            className="gr-dx-axis"
            key={tick}
            textAnchor="middle"
            x={x(tick)}
            y={H - PAD.bottom + 18}
          >
            {pct(tick)}
          </text>
        ))}
        <text
          className="gr-dx-axis"
          textAnchor="middle"
          x={(PAD.left + W - PAD.right) / 2}
          y={H - 6}
        >
          {W < 480
            ? "cost vs. always large"
            : "cost, as a share of always calling the large model"}
        </text>

        <line
          className="gr-dx-target"
          x1={PAD.left}
          x2={W - PAD.right}
          y1={y(fallback.quality - drop)}
          y2={y(fallback.quality - drop)}
        />
        <text
          className="gr-dx-axis"
          x={PAD.left + 6}
          y={y(fallback.quality - drop) - 6}
        >
          fallback quality − {pct(drop, 1)}
        </text>

        <line
          className="gr-dx-random"
          x1={x(allSmall.relativeCost)}
          x2={x(fallback.relativeCost)}
          y1={y(allSmall.quality)}
          y2={y(fallback.quality)}
        />
        <path className="gr-dx-curve" d={path} />

        <circle
          className="gr-dx-dot gr-dx-dot--end"
          cx={x(fallback.relativeCost)}
          cy={y(fallback.quality)}
          r={5}
        />
        <text
          className="gr-dx-label"
          textAnchor="end"
          x={x(fallback.relativeCost) - 10}
          y={y(fallback.quality) - 9}
        >
          always large
        </text>
        <circle
          className="gr-dx-dot gr-dx-dot--end"
          cx={x(allSmall.relativeCost)}
          cy={y(allSmall.quality)}
          r={5}
        />
        <text
          className="gr-dx-label"
          x={x(allSmall.relativeCost) + 10}
          y={y(allSmall.quality) + 4}
        >
          always small
        </text>
        <text
          className="gr-dx-label gr-dx-label--muted"
          x={x((allSmall.relativeCost + 1) / 2) + 8}
          y={y((allSmall.quality + fallback.quality) / 2) + 18}
        >
          random split
        </text>

        <circle
          className="gr-dx-dot gr-dx-dot--chosen"
          cx={x(chosen.relativeCost)}
          cy={y(chosen.quality)}
          r={7}
        />
        {hover ? (
          <g>
            <line
              className="gr-dx-cross"
              x1={x(hover.relativeCost)}
              x2={x(hover.relativeCost)}
              y1={PAD.top}
              y2={H - PAD.bottom}
            />
            <circle
              className="gr-dx-dot"
              cx={x(hover.relativeCost)}
              cy={y(hover.quality)}
              r={5}
            />
          </g>
        ) : null}
      </svg>

      <details className="gr-dx-table">
        <summary>Show the curve as a table</summary>
        <table>
          <thead>
            <tr>
              <th>threshold</th>
              <th>offload_rate</th>
              <th>routed_quality</th>
              <th>cost_savings_pct</th>
            </tr>
          </thead>
          <tbody>
            {curve
              .filter((_, i) => i % 10 === 0)
              .map((point) => (
                <tr key={point.threshold}>
                  <td>{point.threshold.toFixed(2)}</td>
                  <td>{pct(point.offload)}</td>
                  <td>{pct(point.quality, 1)}</td>
                  <td>{pct(1 - point.relativeCost)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </details>

      <figcaption className="gr-dx-caption">
        <strong>Illustrative, not a measurement.</strong> 200 synthetic prompts,
        a small model that costs 1 unit per request and a large one that costs
        6. Each point is one routing threshold; the ringed point is the one
        RouterRecipe would pick: the most offload whose quality stays within{" "}
        <code>max_quality_drop</code> of always calling the fallback. Your run's{" "}
        <code>eval_report.pareto_summary</code> computes the same fields on your
        held-out prompts.
      </figcaption>
    </figure>
  );
};

export default RouterFrontier;
