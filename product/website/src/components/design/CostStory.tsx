import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

/**
 * Traffic, running.
 *
 * Chips stream in from the right and travel left, and each column rises from
 * the floor as it arrives — so the motion reads on both axes at once: the
 * stream moves sideways while the usage it carries builds upward. The top
 * profile is the token trace, and it keeps moving whether or not anything
 * interesting is happening, the way a live meter does.
 *
 * Cost is the line drawn over the field. An earlier pass coloured each chip by
 * what it cost, which put two arguments on one surface and made both harder to
 * read; the chips are the quantity now, and cost is the only thing that moves
 * independently of them. That separation is what the switch demonstrates —
 * throw it and the chips keep arriving at exactly the same rate while the line
 * bends away.
 *
 * Cost compounds rather than ramps, so the line bends: each column's step is
 * proportional to where cost already is. Per-bar variation sits on top of the
 * trend and the line is plotted as a short moving average, because a pure
 * trend draws an arc and an arc reads as a drawing rather than a measurement.
 *
 * THE FIGURES ARE ILLUSTRATIVE. Nothing here is measured — the volumes, the
 * rate and the per-bar readings are all synthetic, chosen to be plausible. The
 * panel carries no note saying so, which is worth knowing given it sits under
 * a lede quoting a real savings range.
 *
 * Canvas, not SVG: a few thousand chips repainted every frame.
 */

const clamp = (n: number, min: number, max: number) =>
  Math.min(max, Math.max(min, n));

const smoothstep = (edge0: number, edge1: number, x: number) => {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
};

/** Chip and gutter. Half the first pass — small enough to read as a stream. */
const CELL = 6;
const GAP = 3;
const PITCH = CELL + GAP;

/** How fast the stream travels, in pixels a second. */
const SPEED = 34;

/** How long a fresh column takes to rise from the floor. */
const RISE_MS = 420;

// Baseline cost rises across the visible window. The switch applies the same
// pricing multiplier to the whole trace, the meter, and hover values.
const RISE_ACROSS = 1.903;
const CREEP_ACROSS = 0.1024;
const CEILING = 0.95;
const TRAINED_MULTIPLIER = 0.2;
const PRICE_TRANSITION_SECONDS = 0.22;

type Rates = { compound: number; creep: number };
const ratesFor = (columns: number): Rates => ({
  compound: Math.pow(RISE_ACROSS, 1 / columns) - 1,
  creep: CREEP_ACROSS / columns,
});
const nextCost = (cost: number, rates: Rates) =>
  Math.min(CEILING, cost + rates.creep + rates.compound * cost);

/* The trend alone draws a smooth arc, which reads as a drawing rather than a
   measurement — real spend moves column to column. This is the per-bar
   variation around the trend; the line is then plotted as a short moving
   average so it has movement without becoming noise. */
const wobbleAt = (p: number) =>
  1 +
  0.16 * Math.sin(p * 2.3) +
  0.09 * Math.sin(p * 0.94 + 2) +
  0.05 * Math.sin(p * 5.1 + 1.1);

/** Bars averaged into each plotted point. */
const SMOOTH = 4;

/* Ember. Every other brand gradient has a stop that is either the page ground
   or the chip colour, and a line drawn over this field has to differ from both
   along its whole length — Terrace and Tide fade out at the old end, Shallows
   starts in the same teal as the chips and merges into them. */
const COST_GRADIENT = "ember";

/** The token trace. Layered periods so it never visibly repeats. */
const usageAt = (p: number) =>
  clamp(
    0.52 +
      0.17 * Math.sin(p * 1.7) +
      0.11 * Math.sin(p * 0.61 + 1.3) +
      0.07 * Math.sin(p * 3.4 + 0.4) +
      0.05 * Math.sin(p * 7.9 + 2.1),
    0.12,
    1,
  );

const TOKENS_RATE = 4.1e6;
/* What a unit of traffic costs an hour at full rate. The meter reads a RATE,
   not a running total: a total climbs for as long as the tab is open, so it
   says more about how long you have been looking than about what anything
   costs. A rate also answers to the toggle, which is the point being made. */
const COST_PER_HOUR = 9_400;

type Column = { born: number; cost: number; rows: number };

const hexToRgb = (hex: string) => {
  const clean = hex.trim().replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ] as const;
};

export const CostStory = (): ReactElement => {
  const [gradiated, setGradiated] = useState(false);
  const [meters, setMeters] = useState({ cost: 0, tokens: 0 });

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const hoverRef = useRef<number | null>(null);
  const redrawRef = useRef<(() => void) | null>(null);
  /* Read by the loop so flipping it does not tear the stream down. */
  const onRef = useRef(gradiated);
  onRef.current = gradiated;

  useEffect(() => {
    redrawRef.current?.();
  }, [gradiated]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const root = document.querySelector(".gr-root") ?? document.documentElement;
    const styles = getComputedStyle(root);
    /* Traffic is one colour: it is the quantity, not the argument. Cost is the
       line drawn over it, in one of the brand gradients — read from the tokens
       so it follows the palette rather than hard-coding two hex values here. */
    const chip = styles.getPropertyValue("--gradient-shallows-from").trim();
    /* Ember's two stops, used by VALUE rather than by position: red is the
       expensive end, amber the cheap one. Mapped down the plot's height, so
       the line reddens as it climbs and cools as it falls — the colour says
       the same thing as the height, which is what makes the drop legible in a
       glance rather than needing the axis read. */
    const dear = hexToRgb(
      styles.getPropertyValue(`--gradient-${COST_GRADIENT}-from`),
    );
    const cheap = hexToRgb(
      styles.getPropertyValue(`--gradient-${COST_GRADIENT}-to`),
    );

    /** The ink for one cost value, 0..1. */
    const inkAt = (value: number) => {
      const mix = clamp(value, 0, 1);
      const r = Math.round(cheap[0] + (dear[0] - cheap[0]) * mix);
      const g = Math.round(cheap[1] + (dear[1] - cheap[1]) * mix);
      const b = Math.round(cheap[2] + (dear[2] - cheap[2]) * mix);
      return `rgb(${r} ${g} ${b})`;
    };

    let width = 0;
    let height = 0;
    let rows = 0;
    let dpr = 1;
    let columns: Column[] = [];
    let phase = 0;
    let offset = 0;
    let tokens = 0;

    let cost = 0.3;
    let priceMultiplier = onRef.current ? TRAINED_MULTIPLIER : 1;
    /* Replaced on every layout, since it depends on how many columns fit. */
    let rates = ratesFor(128);

    const makeColumn = (now: number): Column => {
      phase += 0.16;
      cost = nextCost(cost, rates);
      return {
        born: now,
        cost: clamp(cost * wobbleAt(phase), 0.02, 0.99),
        rows: Math.max(1, Math.round(usageAt(phase) * rows)),
      };
    };

    const layout = () => {
      const box = wrap.getBoundingClientRect();
      if (box.width < 4 || box.height < 4) return;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      width = box.width;
      height = box.height;
      /* Only the backing store is set here. Setting style.width too pins the
         canvas to whatever it measured on the first frame — which was before
         --u resolved — and an inline style outranks the stylesheet, so it
         never caught up when the panel grew. CSS owns the display size. */
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      rows = Math.max(4, Math.floor(height / PITCH));
      const need = Math.ceil(width / PITCH) + 2;
      rates = ratesFor(need);
      const now = performance.now();
      /* Back to the start of the ramp. `cost` lives outside this function so
         the run can keep compounding across frames — which means a resize,
         which rebuilds the whole field, would otherwise carry the accumulated
         cost in and start the new field near the ceiling. */
      cost = 0.3;
      /* Start full rather than empty: a meter that begins blank looks broken
         for its first few seconds. Everything already on screen is grown. */
      columns = Array.from({ length: need }, () => {
        const column = makeColumn(now);
        return { ...column, born: now - RISE_MS };
      });
      redrawRef.current?.();
    };

    layout();
    const resize = new ResizeObserver(layout);
    resize.observe(wrap);

    /* Reduced motion gets the trace standing still. A meter that never stops
       moving is precisely what that setting is asking about. */
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    let raf = 0;
    let last = performance.now();
    let onScreen = true;

    const paint = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;

      const targetMultiplier = onRef.current ? TRAINED_MULTIPLIER : 1;
      priceMultiplier = reduced.matches
        ? targetMultiplier
        : priceMultiplier +
          (targetMultiplier - priceMultiplier) *
            (1 - Math.exp(-dt / PRICE_TRANSITION_SECONDS));

      offset += reduced.matches ? 0 : SPEED * dt;
      while (offset >= PITCH) {
        offset -= PITCH;
        columns.shift();
        const column = makeColumn(now);
        columns.push(column);
        tokens += column.rows * TOKENS_RATE;
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < columns.length; i += 1) {
        const column = columns[i];
        const x = i * PITCH - offset;
        if (x + CELL < 0 || x > width) continue;

        /* Eased so the column settles rather than snapping to height. */
        const grown = smoothstep(
          0,
          1,
          clamp((now - column.born) / RISE_MS, 0, 1),
        );
        const filled = column.rows * grown;
        const whole = Math.floor(filled);
        const part = filled - whole;

        ctx.fillStyle = chip;

        for (let row = 0; row < whole; row += 1) {
          ctx.globalAlpha = smoothstep(0, height * 0.32, (row + 1) * PITCH);
          ctx.fillRect(x, height - (row + 1) * PITCH, CELL, CELL);
        }
        /* The chip currently arriving, fading up as it lands. */
        if (part > 0 && whole < column.rows) {
          ctx.globalAlpha = part * smoothstep(0, height * 0.32, (whole + 1) * PITCH);
          ctx.fillRect(x, height - (whole + 1) * PITCH, CELL, CELL);
        }
      }
      ctx.globalAlpha = 1;

      /* The cost trace, over the field. Plotted from the same columns, so it
         scrolls with the traffic it is charging for. */
      // Use nearly the full height so low costs sit near the chart floor.
      const top = height * 0.1;
      const bottom = height * 0.94;
      const costY = (value: number) => bottom - value * (bottom - top);

      const smoothed = (i: number) => {
        let total = 0;
        let n = 0;
        for (let k = Math.max(0, i - SMOOTH + 1); k <= i; k += 1) {
          total += columns[k].cost;
          n += 1;
        }
        return (total / n) * priceMultiplier;
      };

      ctx.beginPath();
      let started = false;
      for (let i = 0; i < columns.length; i += 1) {
        const px = i * PITCH - offset + CELL / 2;
        if (px < -PITCH || px > width + PITCH) continue;
        const py = costY(smoothed(i));
        if (started) ctx.lineTo(px, py);
        else {
          ctx.moveTo(px, py);
          started = true;
        }
      }
      /* Down the plot, not across it: the stroke's colour then depends on
         where the line IS rather than on where it happens to be on screen, so
         a given cost is always the same colour whatever moment it belongs to.
         Rebuilt per frame because the canvas gradient is in device space and
         the field is resized by its pane. */
      const ramp = ctx.createLinearGradient(0, top, 0, bottom);
      ramp.addColorStop(0, inkAt(1));
      ramp.addColorStop(1, inkAt(0));
      ctx.strokeStyle = ramp;
      ctx.lineWidth = 3;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();

      /* The head of the trace — what says this is now rather than history. */
      const tail = columns.length - 1;
      if (tail >= 0) {
        const px = tail * PITCH - offset + CELL / 2;
        ctx.beginPath();
        ctx.arc(px, costY(smoothed(tail)), 4, 0, Math.PI * 2);
        ctx.fillStyle = inkAt(smoothed(tail));
        ctx.fill();
      }

      /* Inspection. The hovered column is picked from the pointer's x, so a
         reader can put a number on any bar they can see. */
      const at = hoverRef.current;
      if (at !== null && columns[at]) {
        const px = at * PITCH - offset;
        ctx.fillStyle = inkAt(columns[at].cost * priceMultiplier);
        ctx.globalAlpha = 0.18;
        ctx.fillRect(px - 1, 0, CELL + 2, height);
        ctx.globalAlpha = 1;
      }

      setMeters({
        cost: (tail >= 0 ? smoothed(tail) : 0) * COST_PER_HOUR,
        tokens,
      });
      raf = requestAnimationFrame(paint);
    };

    const visibility = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting === onScreen) return;
        onScreen = entry.isIntersecting;
        if (onScreen) {
          last = performance.now();
          raf = requestAnimationFrame(paint);
        } else cancelAnimationFrame(raf);
      },
      { threshold: 0.1 },
    );
    if (reduced.matches) {
      redrawRef.current = () => {
        paint(performance.now());
        cancelAnimationFrame(raf);
      };
      redrawRef.current();
      return () => {
        redrawRef.current = null;
        resize.disconnect();
        visibility.disconnect();
      };
    }

    visibility.observe(wrap);
    raf = requestAnimationFrame(paint);

    const inspect = (event: PointerEvent) => {
      const rect = wrap.getBoundingClientRect();
      const local = event.clientX - rect.left;
      const index = Math.round((local + offset - CELL / 2) / PITCH);
      const column = columns[index];
      if (!column) return;
      hoverRef.current = index;

      const tip = tipRef.current;
      if (!tip) return;
      const tokensHere = column.rows * TOKENS_RATE;
      tip.innerHTML = `<span>${(tokensHere / 1e6).toFixed(0)}M tokens</span><span>$${Math.round(
        column.cost * priceMultiplier * COST_PER_HOUR,
      ).toLocaleString("en-US")} / hr</span>`;
      tip.style.opacity = "1";
      /* Flipped near the right edge so the card is never the thing that makes
         the panel scroll. */
      const flip = local > rect.width * 0.7;
      tip.style.left = `${local}px`;
      tip.style.top = `${Math.max(8, rect.height - column.rows * PITCH - 56)}px`;
      tip.style.transform = `translate(${flip ? "calc(-100% - 12px)" : "12px"}, 0)`;
    };

    const release = () => {
      hoverRef.current = null;
      if (tipRef.current) tipRef.current.style.opacity = "0";
    };

    wrap.addEventListener("pointermove", inspect);
    wrap.addEventListener("pointerleave", release);

    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
      visibility.disconnect();
      wrap.removeEventListener("pointermove", inspect);
      wrap.removeEventListener("pointerleave", release);
    };
  }, []);

  return (
    <div className="gr-cost">
      <div className="gr-cost-meters">
        <p className="gr-cost-meter">
          <span className="gr-label gr-cost-meter-name">Tokens</span>
          <span className="gr-cost-meter-value">
            {(meters.tokens / 1e9).toFixed(2)}B
          </span>
        </p>
        <p className="gr-cost-meter">
          <span className="gr-label gr-cost-meter-name">
            Spend / hr
            <span aria-hidden className="gr-cost-live" />
          </span>
          <span className="gr-cost-meter-value">
            ${Math.round(meters.cost).toLocaleString("en-US")}
          </span>
        </p>

        {/* One switch rather than two buttons: this is a thing that is on or
            off, and a pair of pills read as a choice between two products. */}
        <button
          aria-checked={gradiated}
          className="gr-cost-switch"
          onClick={() => setGradiated((on) => !on)}
          role="switch"
          type="button"
        >
          <span className="gr-cost-switch-name">Gradiated</span>
          <span aria-hidden className="gr-cost-switch-track">
            <span className="gr-cost-switch-knob" />
          </span>
        </button>
      </div>

      <div className="gr-cost-field" ref={wrapRef}>
        <canvas aria-hidden className="gr-cost-canvas" ref={canvasRef} />
        <div aria-hidden className="gr-cost-tip" ref={tipRef} />
      </div>

      <p className="gr-visually-hidden">
        Token use streams past continuously while the cost of serving it
        compounds upward. With Gradiated, the illustrative serving cost drops by
        80% while the volume carries on unchanged. Figures are illustrative.
      </p>
    </div>
  );
};
