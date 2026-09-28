import { useEffect, useRef } from "react";
import type { CSSProperties, ReactElement } from "react";
import { PhoneFlow } from "./PhoneFlow";

/**
 * The loop fold (new-homepage-layout, fold 3).
 *
 * The product story drawn as a live diagram: a product screen points at the
 * Gradiated endpoint (the URL is erased and retyped — the swap IS the
 * integration), Start kicks off post-training, and traces flow DOWN a
 * vertical stack of stages — PRODUCTION TRACES → RL ENVIRONMENT → EVALS →
 * POST-TRAINING — with each finished model logging out LEFT into the
 * "Your Gradiated models" slots. That is the loop: every model's traffic
 * seeds the next round.
 *
 * The DOM owns the layout (grid, rows, slots); the canvas reads the DOM's
 * rectangles each frame and draws the bits, the rollout, the scan and the
 * connectors on top. Same choreography and clocks as ever: keyframes from
 * the original hero, generations pipelined every GEN_PERIOD seconds.
 */

const GEN_LEN = 10.2;
const GEN_PERIOD = 6.5;

/* wide maze for the wide row: rollout runs left to right */
const MR = 11;
const MC = 31;
const ER = 6; // eval grid rows; columns follow from the trace count

const OLD_URL = "https://api.openai.com/v1";
const NEW_URL = "https://api.gradiated.com";
const URL_KEEP = "https://api.".length;

type Bit = {
  sx: number;
  sy: number;
  mx: number;
  my: number;
  ex: number;
  ey: number;
  du: number;
  dv: number;
  delay: number;
  ta: number;
  pass: boolean;
  tv: number;
  k6: number;
  dist: number;
  rank: number;
};

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));
const easeIO = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const easeO = (t: number): number => 1 - Math.pow(1 - t, 3);
const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

const ENGINE = ((): {
  bits: Bit[];
  path: [number, number][];
  DS: number;
  passN: number;
} => {
  let seedState = 11;
  const rnd = (): number => {
    seedState = (seedState * 16807) % 2147483647;
    return (seedState - 1) / 2147483646;
  };
  const maze: number[][] = Array.from({ length: MR }, () => Array(MC).fill(1));
  const stack: [number, number][] = [[1, 1]];
  maze[1][1] = 0;
  while (stack.length) {
    const [r, c] = stack[stack.length - 1];
    const dirs: [number, number][] = [
      [0, 2],
      [0, -2],
      [2, 0],
      [-2, 0],
    ];
    for (let i = dirs.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [dirs[i], dirs[j]] = [dirs[j], dirs[i]];
    }
    let moved = false;
    for (const [dr, dc] of dirs) {
      const nr = r + dr;
      const nc = c + dc;
      if (
        nr > 0 &&
        nr < MR - 1 &&
        nc > 0 &&
        nc < MC - 1 &&
        maze[nr][nc] === 1
      ) {
        maze[r + dr / 2][c + dc / 2] = 0;
        maze[nr][nc] = 0;
        stack.push([nr, nc]);
        moved = true;
        break;
      }
    }
    if (!moved) stack.pop();
  }
  for (let k = 0; k < 10; k++) {
    const r = 1 + Math.floor(rnd() * (MR - 2));
    const c = 1 + Math.floor(rnd() * (MC - 2));
    if (
      maze[r][c] === 1 &&
      ((maze[r - 1][c] === 0 && maze[r + 1][c] === 0) ||
        (maze[r][c - 1] === 0 && maze[r][c + 1] === 0))
    )
      maze[r][c] = 0;
  }
  maze[1][0] = 0;
  maze[MR - 2][MC - 1] = 0;

  /* rollout: left to right */
  const key = (r: number, c: number): number => r * MC + c;
  const prev = new Map<number, [number, number] | null>([[key(1, 0), null]]);
  const q: [number, number][] = [[1, 0]];
  while (q.length) {
    const [r, c] = q.shift() as [number, number];
    if (r === MR - 2 && c === MC - 1) break;
    for (const [dr, dc] of [
      [0, 1],
      [1, 0],
      [0, -1],
      [-1, 0],
    ]) {
      const nr = r + dr;
      const nc = c + dc;
      if (
        nr < 0 ||
        nc < 0 ||
        nr >= MR ||
        nc >= MC ||
        maze[nr][nc] ||
        prev.has(key(nr, nc))
      )
        continue;
      prev.set(key(nr, nc), [r, c]);
      q.push([nr, nc]);
    }
  }
  const path: [number, number][] = [];
  let cur: [number, number] | null = [MR - 2, MC - 1];
  while (cur) {
    path.unshift([cur[1] / (MC - 1), cur[0] / (MR - 1)]);
    cur = prev.get(key(cur[0], cur[1])) ?? null;
  }

  const walls: [number, number][] = [];
  for (let r = 0; r < MR; r++)
    for (let c = 0; c < MC; c++) if (maze[r][c]) walls.push([r, c]);
  const bits: Bit[] = walls.map(([r, c]) => ({
    mx: c / (MC - 1),
    my: r / (MR - 1),
    sx: 0.04 + rnd() * 0.92,
    sy: 0.12 + rnd() * 0.76,
    ex: 0,
    ey: 0,
    du: 0,
    dv: 0,
    delay: rnd() * 0.9,
    ta: rnd(),
    pass: rnd() < 0.78,
    tv: 0,
    k6: 0,
    dist: 0,
    rank: 0,
  }));

  /* eval grid: wide, ordered by maze x so the drop reads straight; the
     scan sweeps left to right, like the original */
  const EC = Math.ceil(bits.length / ER);
  [...bits]
    .sort((a, b) => a.mx - b.mx || a.my - b.my)
    .forEach((b, rank) => {
      const cc = Math.floor(rank / ER);
      const rr = rank % ER;
      b.ex = cc / Math.max(1, EC - 1);
      b.ey = rr / (ER - 1);
      b.tv = 4.8 + b.ex * 1.0;
    });

  const passers = bits
    .filter((b) => b.pass)
    .sort((a, b) => a.ex - b.ex || a.ey - b.ey);
  const DS = Math.ceil(Math.sqrt(passers.length));
  let maxD = 0.0001;
  passers.forEach((b, rank) => {
    b.du = (rank % DS) - (DS - 1) / 2;
    b.dv = Math.floor(rank / DS) - (DS - 1) / 2;
    b.dist = Math.hypot(b.du, b.dv);
    maxD = Math.max(maxD, b.dist);
  });
  passers.forEach((b, rank) => {
    b.dist /= maxD;
    b.rank = rank;
    /* near-uniform exit: the die crosses the divider and CONDENSES into
       the model icon as one object — the data forms the model */
    b.k6 = 8.4 + 0.1 * b.dist;
  });

  return { bits, path, DS, passN: passers.length };
})();

/* a polyline walker for the loop's wires: point at distance u*total */
const alongPath = (pts: [number, number][], u: number): [number, number] => {
  const segs: number[] = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    segs.push(l);
    total += l;
  }
  let d = clamp01(u) * total;
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const f = segs[i] > 0 ? d / segs[i] : 0;
      return [
        lerp(pts[i][0], pts[i + 1][0], f),
        lerp(pts[i][1], pts[i + 1][1], f),
      ];
    }
    d -= segs[i];
  }
  return pts[pts.length - 1];
};

const pathLen = (pts: [number, number][]): number => {
  let total = 0;
  for (let i = 1; i < pts.length; i++)
    total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return total;
};

const bez2 = (
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
  dx: number,
  dy: number,
  u: number,
): [number, number] => {
  const v = 1 - u;
  return [
    ax * v * v * v + bx * 3 * v * v * u + cx * 3 * v * u * u + dx * u * u * u,
    ay * v * v * v + by * 3 * v * v * u + cy * 3 * v * u * u + dy * u * u * u,
  ];
};

const STAGE_LABELS = [
  "Production traces",
  "RL environment",
  "Evals",
  "Post-training",
];

export const LoopSection = (): ReactElement => {
  const hostRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mockRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const urlRef = useRef<HTMLSpanElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const modelZoneRef = useRef<HTMLDivElement>(null);
  const selectorRef = useRef<HTMLDivElement>(null);
  const selBtnRef = useRef<HTMLButtonElement>(null);
  const selLabelRef = useRef<HTMLSpanElement>(null);
  const selMenuRef = useRef<HTMLDivElement>(null);
  const slotsWrapRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const mockEl = mockRef.current;
    const fieldEl = fieldRef.current;
    const urlEl = urlRef.current;
    const startEl = startRef.current;
    const modelZone = modelZoneRef.current;
    const slotsWrap = slotsWrapRef.current;
    const selector = selectorRef.current;
    const selBtn = selBtnRef.current;
    const selLabel = selLabelRef.current;
    const selMenu = selMenuRef.current;
    const rows = rowRefs.current;
    if (
      !host ||
      !canvas ||
      !mockEl ||
      !fieldEl ||
      !urlEl ||
      !startEl ||
      !modelZone ||
      !slotsWrap
    )
      return;
    if (!selector || !selBtn || !selLabel || !selMenu) return;
    if (rows.some((r) => !r)) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const rootEl =
      (canvas.closest(".gr-root") as HTMLElement) ?? document.documentElement;
    let ink = "#2F2D29";
    const readInk = (): void => {
      ink =
        getComputedStyle(rootEl).getPropertyValue("--color-text").trim() ||
        "#2F2D29";
    };
    readInk();
    const themed = new MutationObserver(readInk);
    themed.observe(rootEl, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    let W = 0;
    let H = 0;
    const resize = new ResizeObserver(() => {
      const box = host.getBoundingClientRect();
      W = box.width;
      H = box.height;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    });
    resize.observe(host);

    /* ---- the URL swap, then the engine ---- */
    let visible = false;
    let sequenceAt = -1; // wall-clock start of the erase/type sequence
    let engineStart = -1;
    let filled = -1; // newest generation shown in the slots

    /* The model log: an icon EXISTS only once post-training has produced
       it. The newest sits at the right, where its data arrives; each new
       model pushes the older ones left, into the fade. */
    const slotEls: HTMLDivElement[] = [];
    const SLOT_STEP = 70;

    /* the product's model selector: provider model until the first
       Gradiated model ships, then the newest version is LIVE */
    const versions: string[] = [];
    const renderSelector = (): void => {
      const live = versions.length > 0;
      selector.classList.toggle("gr-loop-selector--live", live);
      selLabel.textContent = live ? versions[0] : "gpt-4o";
      selMenu.innerHTML = "";
      const list = live ? versions : ["gpt-4o"];
      list.forEach((v, i) => {
        const item = document.createElement("div");
        item.className =
          "gr-loop-selector-item" +
          (i === 0 ? " gr-loop-selector-item--live" : "");
        if (i === 0) {
          const dot = document.createElement("span");
          dot.className = "gr-loop-livedot";
          item.appendChild(dot);
        }
        item.appendChild(document.createTextNode(v));
        selMenu.appendChild(item);
      });
    };
    renderSelector();
    const onSelToggle = (e: MouseEvent): void => {
      e.stopPropagation();
      selector.classList.toggle("gr-loop-selector--open");
    };
    const onDocClick = (): void =>
      selector.classList.remove("gr-loop-selector--open");
    selBtn.addEventListener("click", onSelToggle);
    document.addEventListener("click", onDocClick);
    const placeSlots = (): void => {
      slotEls.forEach((el, age) => {
        el.style.transform = `translateX(${-age * SLOT_STEP}px)`;
      });
      while (slotEls.length > 7) {
        const el = slotEls.pop();
        el?.remove();
      }
    };
    const createSlot = (version: string): void => {
      const el = document.createElement("div");
      el.className = "gr-loop-slot gr-loop-slot--filled gr-loop-slot--new";
      el.dataset.v = version;
      slotsWrap.appendChild(el);
      slotEls.unshift(el);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => el.classList.remove("gr-loop-slot--new")),
      );
      placeSlots();
    };

    const seen = new IntersectionObserver(
      ([e]) => {
        visible = e.isIntersecting;
        /* the content's entrance and the diagram's first beat share this
           moment — the blocks settle in while the URL swap winds up */
        if (visible) host.classList.add("gr-loop--seen");
        if (visible && sequenceAt < 0)
          sequenceAt = performance.now() / 1000 + 0.5;
      },
      { threshold: 0.35 },
    );
    seen.observe(host);

    const urlState = (t: number): string => {
      if (reduced) return NEW_URL;
      if (sequenceAt < 0 || t < sequenceAt) return OLD_URL;
      const e = t - sequenceAt;
      const erase = (OLD_URL.length - URL_KEEP) * 0.045;
      if (e < erase)
        return OLD_URL.slice(0, OLD_URL.length - Math.floor(e / 0.045));
      const typed = Math.floor((e - erase - 0.25) / 0.06);
      if (typed < 0) return OLD_URL.slice(0, URL_KEEP);
      return NEW_URL.slice(0, Math.min(NEW_URL.length, URL_KEEP + typed));
    };
    const swapDone = (t: number): boolean =>
      reduced ||
      (sequenceAt >= 0 &&
        t >
          sequenceAt +
            (OLD_URL.length - URL_KEEP) * 0.045 +
            0.25 +
            (NEW_URL.length - URL_KEEP) * 0.06);

    const begin = (t: number): void => {
      engineStart = t;
      filled = -1;
      slotEls.length = 0;
      slotsWrap.innerHTML = "";
      versions.length = 0;
      renderSelector();
    };
    const onStart = (): void => {
      const t = performance.now() / 1000;
      if (!swapDone(t)) sequenceAt = t - 100; // complete the swap instantly
      begin(t);
    };
    startEl.addEventListener("click", onStart);

    /* section-relative rectangle of a DOM node */
    const rel = (
      el: Element,
    ): { x: number; y: number; w: number; h: number } => {
      const hb = host.getBoundingClientRect();
      const b = el.getBoundingClientRect();
      return {
        x: b.left - hb.left,
        y: b.top - hb.top,
        w: b.width,
        h: b.height,
      };
    };
    const inset = (
      r: { x: number; y: number; w: number; h: number },
      px: number,
      py: number,
    ) => ({
      x: r.x + px,
      y: r.y + py,
      w: r.w - 2 * px,
      h: r.h - 2 * py,
    });

    let raf = 0;
    const frame = (now: number): void => {
      raf = requestAnimationFrame(frame);
      if (!visible || W < 4) return;
      const t = now / 1000;

      urlEl.textContent = urlState(t);
      if (swapDone(t) && engineStart < 0 && !reduced) begin(t + 0.6);
      startEl.classList.toggle("gr-loop-start--ready", swapDone(t));

      /* single-column layout: the cross-layout wires (product -> endpoint,
         endpoint -> stack, and the return loop) assume the two-column
         geometry and are overkill on mobile — the column IS the flow */
      const narrow = matchMedia("(max-width: 900px)").matches;
      const R = rows.map((r) => inset(rel(r as HTMLDivElement), 18, 12));
      const mock = rel(mockEl);
      const field = rel(fieldEl);
      /* the last row is chambered: models left of the divider, the die in
         the open right section */
      const mz = rel(modelZone);
      const rowLast = rel(rows[3] as HTMLDivElement);

      ctx.clearRect(0, 0, W, H);
      ctx.strokeStyle = ink;
      ctx.fillStyle = ink;
      ctx.lineWidth = 1;

      /* ---- connectors: the circuit the loop runs on ---- */
      const fcy = field.y + field.h / 2;
      const fcx = field.x + field.w / 2;
      const mx = mock.x + 24;
      if (!narrow) {
        ctx.save();
        ctx.globalAlpha = 0.3;
        ctx.beginPath();
        ctx.moveTo(mock.x + mock.w, fcy);
        ctx.lineTo(field.x, fcy);
        ctx.moveTo(fcx, field.y + field.h);
        ctx.lineTo(fcx, R[0].y - 12);
        ctx.stroke();
        ctx.restore();
      }

      const tE = engineStart >= 0 ? t - engineStart : -1;
      if (tE < 0) return;

      const mazeCellW = R[1].w / (MC - 1);
      const bit = Math.max(
        3,
        Math.min(mazeCellW * 0.42, (R[1].h / (MR - 1)) * 0.5),
      );
      const at = (
        r: { x: number; y: number; w: number; h: number },
        nx: number,
        ny: number,
      ): [number, number] => [r.x + nx * r.w, r.y + ny * r.h];

      const dzX = mz.x + mz.w + 22;
      const dzW = rowLast.x + rowLast.w - 18 - dzX;
      const dieSide = Math.min(R[3].h, dzW) * 0.72;
      const DP = (dieSide * 0.85) / ENGINE.DS;
      /* the packed square's chip size: at most 55% of the pitch, so the
         formation reads as a grid of chips, never a fused blob */
      const dieBit = Math.min(bit, DP * 0.55);
      const dieC: [number, number] = [dzX + dzW / 2, R[3].y + R[3].h / 2];

      /* a model icon is CREATED by its arriving data */
      const latest = Math.floor((tE - 9.2) / GEN_PERIOD);
      if (latest > filled && latest >= 0) {
        filled = latest;
        const version = latest === 0 ? "v1" : `v1.${latest}`;
        createSlot(version);
        versions.unshift(version);
        if (versions.length > 6) versions.pop();
        renderSelector();
      }
      /* the newest icon's berth: at the right edge of the log, data
         entering from its right side */
      const wrap = rel(slotsWrap);
      const slotCx = wrap.x + wrap.w - 28;
      const slotCy = wrap.y + 28;

      /* once the first model has shipped, the loop is CLOSED: bits stream
         single file from the models back through the product, into the
         endpoint, and down into production traces — continuously */
      const sA = clamp01((tE - 9.6) / 1.2);
      const retY = rowLast.y + rowLast.h / 2;
      if (!narrow) {
        /* the return leg: model traffic feeds the product. It connects to
           the LEFT SIDE of the last box and runs up the product's spine.
           Drawn as a static wire always, ridden by bits once shipped. */
        ctx.save();
        ctx.globalAlpha = 0.3;
        ctx.beginPath();
        ctx.moveTo(rowLast.x, retY);
        ctx.lineTo(mx, retY);
        ctx.lineTo(mx, mock.y + mock.h);
        ctx.stroke();
        ctx.restore();
      }
      if (!narrow && sA > 0.01) {
        const wires: [number, number][][] = [
          [
            [rowLast.x, retY],
            [mx, retY],
            [mx, mock.y + mock.h],
          ],
        ];
        for (const wire of wires) {
          const len = pathLen(wire);
          const n = Math.max(3, Math.floor(len / 30));
          for (let j = 0; j < n; j++) {
            const ph = ((t * 80) / len + j / n) % 1;
            const [wx, wy] = alongPath(wire, ph);
            ctx.globalAlpha =
              sA * 0.55 * Math.min(1, ph * 6) * Math.min(1, (1 - ph) * 6);
            ctx.fillRect(wx - bit / 2, wy - bit / 2, bit, bit);
          }
        }
      }

      const gLo = Math.max(0, Math.ceil((tE - GEN_LEN) / GEN_PERIOD));
      const gHi = Math.floor(tE / GEN_PERIOD) + 1;
      for (let g = gLo; g <= gHi; g++) {
        const T = tE - g * GEN_PERIOD;
        const outPt: [number, number] = [slotCx, slotCy];

        for (const b of ENGINE.bits) {
          const appear = -GEN_PERIOD * (0.05 + 0.9 * b.ta);
          if (T < appear) continue;
          const d = b.delay;
          const k0 = d;
          const k1 = d + 1.6;
          const k2 = 3.6 + 0.25 * d;
          const k3 = 4.4 + 0.25 * d;
          const k4 = 6.15 + 0.2 * d;
          const k5 = 7.0 + 0.2 * d;
          const k6 = b.k6;
          const k7 = k6 + 0.7;
          let px: number;
          let py: number;
          let alpha = 1;
          let size = bit;

          const [sxp, syp] = at(R[0], b.sx, b.sy);
          const [mxp, myp] = at(R[1], b.mx, b.my);

          if (T < k0) {
            /* the trace EMANATES from the product: out of the mock, into
               the endpoint, out of its underside, down into the traces
               stage — then it waits its turn */
            const u = (T - appear) / 1.5;
            if (u < 1) {
              if (narrow) continue; /* no cross-layout ride on mobile */
              if (u < 0.42) {
                [px, py] = alongPath(
                  [
                    [mock.x + mock.w, fcy],
                    [field.x - 4, fcy],
                  ],
                  u / 0.42,
                );
                alpha = 0.55 * clamp01(u * 10);
              } else if (u < 0.52) {
                continue; /* inside the endpoint */
              } else {
                [px, py] = alongPath(
                  [
                    [fcx, field.y + field.h],
                    [fcx, R[0].y + 10],
                    [sxp, syp],
                  ],
                  (u - 0.52) / 0.48,
                );
                alpha = 0.55;
              }
            } else {
              px = sxp;
              py = syp;
              alpha = 0.4;
            }
          } else if (T < k1) {
            const u = (T - k0) / 1.6;
            const e = easeIO(u);
            [px, py] = bez2(
              sxp,
              syp,
              sxp,
              syp + (myp - syp) * 0.4,
              mxp,
              myp - (myp - syp) * 0.3,
              mxp,
              myp,
              e,
            );
            alpha = Math.min(1, 0.4 + u * 3);
          } else if (T < k2) {
            px = mxp;
            py =
              myp -
              Math.max(0, Math.sin(clamp01((T - k1) / 0.35) * Math.PI)) * 3;
          } else if (T < k3) {
            const e = easeIO((T - k2) / (k3 - k2));
            const [exp_, eyp] = at(R[2], b.ex, b.ey);
            px = lerp(mxp, exp_, e);
            py = lerp(myp, eyp, e);
          } else if (!b.pass && T > b.tv) {
            const u = clamp01((T - b.tv) / 0.6);
            if (u >= 1) continue;
            const [exp_, eyp] = at(R[2], b.ex, b.ey);
            px = exp_;
            py = eyp + u * 14;
            alpha = 1 - u;
          } else if (T < k4) {
            const [exp_, eyp] = at(R[2], b.ex, b.ey);
            px = exp_;
            py = eyp;
            if (T > b.tv)
              py -= Math.sin(clamp01((T - b.tv) / 0.5) * Math.PI) * 4;
          } else if (!b.pass) {
            continue;
          } else if (T < k5) {
            const e = easeIO((T - k4) / (k5 - k4));
            const [exp_, eyp] = at(R[2], b.ex, b.ey);
            px = lerp(exp_, dieC[0] + b.du * DP, e);
            py = lerp(eyp, dieC[1] + b.dv * DP, e);
            /* shrink toward the die bit on the way in, so the packed square
               keeps daylight between its chips instead of fusing to a blob */
            size = lerp(bit, dieBit, e);
          } else if (T < k6) {
            px = dieC[0] + b.du * DP;
            py = dieC[1] + b.dv * DP;
            const ramp = clamp01((T - k5) / 0.4);
            const w = Math.sin(T * 7 - b.dist * 9);
            py += w * dieBit * 0.45 * ramp;
            size = dieBit * (1 + 0.12 * Math.max(0, w) * ramp);
          } else if (T < k7) {
            /* the formed square crosses the divider and condenses into
               the model icon — the same formation as ever */
            const u = (T - k6) / 0.7;
            if (u >= 1) continue;
            const e = u * u;
            px = lerp(dieC[0] + b.du * DP, outPt[0] + b.du * DP * 0.14, e);
            py = lerp(dieC[1] + b.dv * DP, outPt[1] + b.dv * DP * 0.14, e);
            size = dieBit * (1 - e * 0.6);
            alpha = 1 - e * 0.35;
          } else {
            continue;
          }

          ctx.globalAlpha = alpha;
          ctx.fillRect(px - size / 2, py - size / 2, size, size);
        }

        /* the rollout, left to right through the environment */
        const au = (T - 2.3) / 1.4;
        const trailA =
          au > 0 && au < 1.5 ? Math.min(1, au < 1 ? 1 : (1.5 - au) / 0.5) : 0;
        if (trailA > 0 && ENGINE.path.length > 1) {
          const f = clamp01(au) * (ENGINE.path.length - 1);
          const i0 = Math.floor(f);
          ctx.globalAlpha = trailA * 0.45;
          ctx.beginPath();
          for (let i = 0; i <= Math.min(i0 + 1, ENGINE.path.length - 1); i++) {
            const [x, y] = at(R[1], ENGINE.path[i][0], ENGINE.path[i][1]);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
          if (au > 0 && au < 1) {
            const i1 = Math.min(i0 + 1, ENGINE.path.length - 1);
            const [x0, y0] = at(R[1], ENGINE.path[i0][0], ENGINE.path[i0][1]);
            const [x1, y1] = at(R[1], ENGINE.path[i1][0], ENGINE.path[i1][1]);
            const ax = lerp(x0, x1, f - i0);
            const ay = lerp(y0, y1, f - i0);
            const asz = bit * 1.5;
            ctx.globalAlpha = 1;
            ctx.fillRect(ax - asz / 2, ay - asz / 2, asz, asz);
            ctx.strokeRect(ax - asz, ay - asz, asz * 2, asz * 2);
          }
        }

        /* the scan, sweeping across the evals row */
        const bu = (T - 4.8) / 1.0;
        const bo =
          bu > -0.1 && bu < 1.1
            ? Math.min(1, (bu + 0.1) * 5, (1.1 - bu) * 5)
            : 0;
        if (bo > 0) {
          const scanX = R[2].x + R[2].w * clamp01(bu);
          ctx.globalAlpha = bo * 0.08;
          ctx.fillRect(scanX - 10, R[2].y - 6, 20, R[2].h + 12);
          ctx.globalAlpha = bo;
          ctx.fillRect(scanX, R[2].y - 6, 1, R[2].h + 12);
        }
      }
      ctx.globalAlpha = 1;
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      resize.disconnect();
      seen.disconnect();
      themed.disconnect();
      startEl.removeEventListener("click", onStart);
      selBtn.removeEventListener("click", onSelToggle);
      document.removeEventListener("click", onDocClick);
    };
  }, []);

  return (
    <section className="gr-loop" ref={hostRef}>
      <canvas className="gr-loop-canvas" ref={canvasRef} />
      <div className="gr-loop-grid">
        <div className="gr-loop-left">
          <div
            className="gr-loop-mock gr-enter"
            ref={mockRef}
            style={{ "--enter-delay": "0.1s" } as CSSProperties}
          >
            <div className="gr-loop-selector" ref={selectorRef}>
              <button
                className="gr-loop-selector-btn"
                ref={selBtnRef}
                type="button"
              >
                <span className="gr-loop-livedot" />
                <span ref={selLabelRef}>gpt-4o</span>
                <span className="gr-loop-selector-chev">&#9662;</span>
              </button>
              <div className="gr-loop-selector-menu" ref={selMenuRef} />
            </div>
            <PhoneFlow />
          </div>
          <div
            className="gr-loop-copy gr-enter"
            style={{ "--enter-delay": "0.3s" } as CSSProperties}
          >
            <p>
              We rebuild your production traces as an RL environment, derive
              evals from what actually succeeded in production, and post-train
              an open model against them.
            </p>
            <p>
              Post-training a model on your own workload is normally a staffing
              problem. You need people who do RL for a living, and a cluster you
              pay for whether or not it&apos;s busy. Gradiated completely
              removes the need for that part. It&apos;s just an API endpoint,
              and your production traffic.
            </p>
          </div>
        </div>

        <div className="gr-loop-right">
          <h2 className="gr-heading gr-loop-title gr-enter">
            Trained on your production traffic
          </h2>
          <div
            className="gr-loop-controls gr-enter"
            style={{ "--enter-delay": "0.2s" } as CSSProperties}
          >
            <div className="gr-loop-field" ref={fieldRef}>
              <span ref={urlRef}>{OLD_URL}</span>
              <span className="gr-loop-caret" />
            </div>
            <button className="gr-loop-start" ref={startRef} type="button">
              Start
            </button>
          </div>
          <div
            className="gr-loop-stack gr-enter"
            style={{ "--enter-delay": "0.35s" } as CSSProperties}
          >
            {STAGE_LABELS.map((label, i) => (
              <div
                className="gr-loop-row"
                key={label}
                ref={(el) => {
                  rowRefs.current[i] = el;
                }}
              >
                <span className="gr-loop-rowlabel">{label}</span>
                {i === 3 && (
                  <div className="gr-loop-modelzone" ref={modelZoneRef}>
                    <div className="gr-loop-slots" ref={slotsWrapRef} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};
