/**
 * wafer-field.js
 * ---------------------------------------------------------------------------
 * A tiny, dependency-free particle-assembly engine: a fixed grid of "chip"
 * squares (like dies on a silicon wafer), where any icon/shape is just a
 * bitmap toggling which grid slots are active. Chips animate in/out of their
 * slot using pluggable scatter patterns.
 *
 * Core idea: the grid never moves. Only which chips are "on", and where each
 * chip starts from before assembling into its slot, changes. That's what
 * makes it trivially extensible to any shape and any entrance style.
 * ---------------------------------------------------------------------------
 */

export const Easing = {
  linear: (t) => t,
  easeOutQuad: (t) => 1 - (1 - t) * (1 - t),
  easeInOutQuad: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
  easeOutCubic: (t) => 1 - Math.pow(1 - t, 3),
  easeInOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  easeOutQuart: (t) => 1 - Math.pow(1 - t, 4),
  easeOutQuint: (t) => 1 - Math.pow(1 - t, 5),
  easeOutExpo: (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  easeOutBack: (t) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
  easeOutElastic: (t) => {
    const c4 = (2 * Math.PI) / 3;
    return t === 0 ? 0 : t === 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
  },
};

function lerp(a, b, t) {
  return a + (b - a) * t;
}

// Quadratic Bezier: bows the path through a control point instead of a
// straight line — this is what makes assembly read as organic drift rather
// than mechanical convergence.
function quadBezier(p0, p1, p2, t) {
  const mt = 1 - t;
  return mt * mt * p0 + 2 * mt * t * p1 + t * t * p2;
}

// ---------------------------------------------------------------------------
// Built-in scatter patterns.
// Each receives (chip, ctx) and must return { x, y, delay } — the position a
// chip starts from before assembling into its fixed grid slot, and an
// additional per-chip delay (ms) layered on top of the global stagger.
// `ctx` = { cols, rows, chipStep, canvasWidth, canvasHeight, index, total }
// ---------------------------------------------------------------------------
const builtinPatterns = {
  random(chip, ctx) {
    return {
      x: Math.random() * ctx.canvasWidth * 1.3 - ctx.canvasWidth * 0.15,
      y: Math.random() * ctx.canvasHeight * 1.3 - ctx.canvasHeight * 0.15,
      delay: Math.random() * 1,
    };
  },

  "radial-burst"(chip, ctx) {
    const cx = ctx.canvasWidth / 2;
    const cy = ctx.canvasHeight / 2;
    const dx = chip.targetX - cx;
    const dy = chip.targetY - cy;
    const dist = Math.hypot(dx, dy) || 1;
    const nx = dx / dist;
    const ny = dy / dist;
    const burst = Math.max(ctx.canvasWidth, ctx.canvasHeight) * (1.1 + Math.random() * 0.6);
    return {
      x: cx + nx * burst,
      y: cy + ny * burst,
      // ripple outward: farther-from-center chips settle slightly later
      delay: dist / Math.max(ctx.canvasWidth, ctx.canvasHeight),
    };
  },

  "gravity-drop"(chip, ctx) {
    return {
      x: chip.targetX,
      y: -ctx.chipStep - Math.random() * ctx.canvasHeight * 0.6,
      // gentle left-to-right wave as chips land
      delay: chip.col / Math.max(1, ctx.cols - 1),
    };
  },

  "spiral-in"(chip, ctx) {
    const cx = ctx.canvasWidth / 2;
    const cy = ctx.canvasHeight / 2;
    const t = ctx.index / Math.max(1, ctx.total - 1);
    const angle = t * Math.PI * 10; // ~5 full rotations across the set
    const radius = Math.max(ctx.canvasWidth, ctx.canvasHeight) * (0.15 + t * 0.9);
    return {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      delay: t,
    };
  },

  "wave-rise"(chip, ctx) {
    return {
      x: chip.targetX,
      y: ctx.canvasHeight + ctx.chipStep + Math.random() * ctx.chipStep * 4,
      delay: 0.15 * Math.sin(chip.col / Math.max(1, ctx.cols - 1) * Math.PI) +
             (chip.row / Math.max(1, ctx.rows - 1)) * 0.3,
    };
  },

  // Each chip orbits its OWN target at a randomized radius/angle (unlike
  // spiral-in, which sweeps every chip around one shared global spiral) —
  // reads as loose, independent drift converging into place rather than a
  // single mechanical swirl.
  "orbit-in"(chip, ctx) {
    const angle = Math.random() * Math.PI * 2;
    const radius = Math.max(ctx.canvasWidth, ctx.canvasHeight) * (0.35 + Math.random() * 0.55);
    return {
      x: chip.targetX + Math.cos(angle) * radius,
      y: chip.targetY + Math.sin(angle) * radius,
      delay: Math.random(),
    };
  },
};

export class WaferField {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {object} options
   * @param {number} [options.chipSize=10]   Visual size of each chip square, px.
   * @param {number} [options.gap=3]         Gap between chips, px.
   * @param {number} [options.cornerRadius=2] Corner radius of each chip, px.
   * @param {string} [options.chipColor='#e9e9e2']
   * @param {string} [options.bgColor='transparent']
   * @param {number} [options.curveAmount=0.3] 0-1+. How much each chip's
   *   path bows away from a straight line (as a fraction of travel
   *   distance) — 0 is mechanical/straight, ~0.3 reads as organic drift,
   *   higher gets swirlier. Direction/magnitude is randomized per chip.
   * @param {number} [options.durationJitter=0.18] 0-1. Per-chip random
   *   variance in travel duration (fraction of base duration) so chips
   *   don't all arrive in lockstep — set to 0 for uniform timing.
   * @param {string} [options.chipShape='square'] Default shape for chips
   *   without an individual override: 'square' | 'circle' | 'diamond' |
   *   'triangle' | 'hexagon' | 'ascii'.
   * @param {string[]} [options.asciiChars] Character pool used in 'ascii'
   *   shape mode (and by randomizeShapes({mode:'ascii'})). Defaults to a
   *   binary/hex-ish set fitting the wafer theme.
   * @param {number} [options.depthAmount=0.5] 0-1+. How far chips travel
   *   along a simulated Z axis during entrance/exit (scaled + shaded to
   *   read as depth) — 0 disables the 3D effect entirely.
   * @param {number} [options.reliefAmount=0] 0-1. Static per-chip elevation
   *   variance for an "embossed" resting look — 0 (default) means chips
   *   sit flush; call randomizeRelief() to populate it.
   * @param {number} [options.lightAngle=-45] Degrees. Direction the
   *   simulated light comes from, used to shade elevated/moving chips.
   * @param {number} [options.lightIntensity=0.35] 0-1. Strength of the
   *   light/shade effect from depth + relief.
   * @param {number} [options.motionGlow=0.5] 0-1. Strength of the
   *   brightness boost applied to chips while they're actively moving —
   *   0 disables it.
   * @param {string} [options.shading='gradient'] 'gradient' (directional
   *   bevel + elevation/motion brightness — the full light/shade look),
   *   'flat' (solid brightness shift only, cheaper), or 'off' (flat
   *   chipColor, fastest — use for very large grids if needed).
   * @param {number} [options.pixelRatio] Canvas backing-store resolution
   *   multiplier, independent of on-screen CSS size — defaults to
   *   `window.devicePixelRatio` so the canvas is crisp on Retina/HiDPI
   *   screens (and, not incidentally, in video/GIF exports, which capture
   *   the backing store's actual pixels). Call setPixelRatio() to bump it
   *   further just for a high-res export.
   * @param {object} [options.shimmer] Idle shimmer sweep, on by default
   *   once assemble() completes — see startShimmer() for fields.
   * @param {boolean} [options.autoShimmer=true] Start the shimmer sweep
   *   automatically when assemble() finishes. Set false to control it
   *   manually via startShimmer()/stopShimmer().
   */
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.chipSize = options.chipSize ?? 10;
    this.gap = options.gap ?? 3;
    this.cornerRadius = options.cornerRadius ?? 2;
    this.chipColor = options.chipColor ?? "#e9e9e2";
    this.bgColor = options.bgColor ?? "transparent";
    this.curveAmount = options.curveAmount ?? 0.3;
    this.durationJitter = options.durationJitter ?? 0.18;

    this.chipShape = options.chipShape ?? "square";
    this.asciiChars = options.asciiChars ?? ["0", "1", "•", "+", "×", "/", "="];
    this.depthAmount = options.depthAmount ?? 0.5;
    this.reliefAmount = options.reliefAmount ?? 0;
    this.lightAngle = options.lightAngle ?? -45;
    this.lightIntensity = options.lightIntensity ?? 0.35;
    this.motionGlow = options.motionGlow ?? 0.5;
    this.shading = options.shading ?? "gradient"; // 'gradient' | 'flat' | 'off'

    this.pixelRatio =
      options.pixelRatio ?? (typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1);

    this.autoShimmer = options.autoShimmer ?? true;
    this.shimmerOptions = {
      speed: 0.6,
      width: 0.28,
      intensity: 0.28,
      angle: -45,
      ...(options.shimmer || {}),
    };
    this._shimmerRafId = null;

    this.cols = 0;
    this.rows = 0;
    this.chips = []; // flat array, index = row * cols + col

    this.patterns = { ...builtinPatterns };
    this._rafId = null;
  }

  registerScatterPattern(name, fn) {
    this.patterns[name] = fn;
  }

  get chipStep() {
    return this.chipSize + this.gap;
  }

  /**
   * Sets the canvas's backing-store resolution (device pixels) independent
   * of its on-screen CSS size, and its 2D-context transform, WITHOUT
   * touching chip data — safe to call any time, including mid-animation.
   * Chip coordinates (chip.x, targetX, etc.) stay in logical/CSS pixels;
   * this is what makes those coordinates map to sharp output regardless of
   * pixelRatio.
   */
  _applyCanvasSize() {
    const step = this.chipStep;
    const logicalWidth = Math.max(1, this.cols * step - this.gap);
    const logicalHeight = Math.max(1, this.rows * step - this.gap);
    this.canvas.style.width = logicalWidth + "px";
    this.canvas.style.height = logicalHeight + "px";
    this.canvas.width = Math.max(1, Math.round(logicalWidth * this.pixelRatio));
    this.canvas.height = Math.max(1, Math.round(logicalHeight * this.pixelRatio));
  }

  /**
   * Change the canvas's backing-store resolution on the fly — e.g. bump it
   * up before a video/GIF export for a sharper result, then set it back
   * afterward. Preserves all chip state (unlike resize()).
   */
  setPixelRatio(ratio) {
    this.pixelRatio = Math.max(0.1, ratio);
    this._applyCanvasSize();
    this.render();
    return this;
  }

  /** (Re)build the fixed grid at cols x rows. Existing active-state is lost. */
  resize(cols, rows) {
    this.cols = cols;
    this.rows = rows;
    this._applyCanvasSize();

    const step = this.chipStep;
    this.chips = [];
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const targetX = col * step;
        const targetY = row * step;
        this.chips.push({
          col,
          row,
          targetX,
          targetY,
          x: targetX,
          y: targetY,
          startX: targetX,
          startY: targetY,
          delay: 0,
          active: false,
          alpha: 0,
          shape: null, // null = use this.chipShape
          char: null, // null = use a char from this.asciiChars (stable per chip)
          z: 0,
          startZ: 0,
          relief: 0,
          prevX: targetX,
          prevY: targetY,
        });
      }
    }
  }

  /**
   * Randomly assign each active chip a shape (and/or ASCII char) from a
   * pool, so the assembled icon reads as a mix of forms rather than
   * uniform squares. Call again any time to reshuffle.
   *
   * @param {object} opts
   * @param {string[]} [opts.shapes] Pool to pick from, e.g.
   *   ['square','circle','diamond','triangle','hexagon']. Omit to leave
   *   shapes untouched (useful if you only want to randomize chars).
   * @param {string[]} [opts.chars] Character pool for chips assigned the
   *   'ascii' shape (or omit `shapes` and pass this with mode:'ascii' to
   *   force every active chip to ascii with random chars).
   * @param {'shape'|'ascii'|'mixed'} [opts.mode='shape'] 'shape' picks from
   *   `shapes` only; 'ascii' forces every chip to the ascii shape with a
   *   random char from `chars`; 'mixed' picks randomly between `shapes`
   *   and ascii-with-random-char for real per-chip variety.
   */
  randomizeShapes({ shapes, chars, mode = "shape" } = {}) {
    const shapePool = shapes ?? ["square", "circle", "diamond", "triangle", "hexagon"];
    const charPool = chars ?? this.asciiChars;
    for (const chip of this.chips) {
      if (!chip.active) continue;
      if (mode === "ascii") {
        chip.shape = "ascii";
        chip.char = charPool[(Math.random() * charPool.length) | 0];
      } else if (mode === "mixed") {
        if (Math.random() < 0.5) {
          chip.shape = "ascii";
          chip.char = charPool[(Math.random() * charPool.length) | 0];
        } else {
          chip.shape = shapePool[(Math.random() * shapePool.length) | 0];
        }
      } else {
        chip.shape = shapePool[(Math.random() * shapePool.length) | 0];
      }
    }
    this.render();
    return this;
  }

  /** Reset all active chips back to the default shape (this.chipShape). */
  resetShapes() {
    for (const chip of this.chips) {
      chip.shape = null;
      chip.char = null;
    }
    this.render();
    return this;
  }

  /**
   * Randomly assign each active chip a static elevation (relief), used
   * purely for light/shade — an "embossed wafer" look even at rest.
   * @param {number} [amount] Overrides this.reliefAmount for this call.
   */
  randomizeRelief(amount = this.reliefAmount || 0.35) {
    this.reliefAmount = amount;
    for (const chip of this.chips) {
      if (!chip.active) continue;
      chip.relief = (Math.random() * 2 - 1) * amount;
    }
    this.render();
    return this;
  }

  /** Flatten all chips back to zero relief. */
  resetRelief() {
    for (const chip of this.chips) chip.relief = 0;
    this.render();
    return this;
  }

  _randomZ() {
    return (Math.random() * 2 - 1) * this.depthAmount;
  }

  /**
   * Toggle which grid slots are active/visible from a 2D boolean (or 0/1)
   * bitmap. If the bitmap is smaller than the current grid, it's centered.
   * If no grid exists yet, one is created to exactly fit the bitmap.
   */
  setShapeFromBitmap(bitmap) {
    const bRows = bitmap.length;
    const bCols = bitmap[0]?.length ?? 0;

    if (this.cols === 0 || this.rows === 0) {
      this.resize(bCols, bRows);
    }

    const offCol = Math.floor((this.cols - bCols) / 2);
    const offRow = Math.floor((this.rows - bRows) / 2);

    for (const chip of this.chips) {
      const bc = chip.col - offCol;
      const br = chip.row - offRow;
      const on =
        bc >= 0 && bc < bCols && br >= 0 && br < bRows && !!bitmap[br][bc];
      chip.active = on;
      if (!on) chip.alpha = 0;
    }
  }

  /**
   * Sample an image into a bitmap and apply it via setShapeFromBitmap.
   * Grid resolution is derived from the current canvas chip grid — if none
   * exists yet, pass {cols, rows} (or {maxWidth} + image aspect ratio).
   *
   * @param {string|HTMLImageElement} src
   * @param {object} opts
   * @param {number} [opts.threshold=128]  0-255 cutoff.
   * @param {boolean} [opts.invert=false]  Flip which side of threshold counts as "on".
   * @param {boolean} [opts.fill=false] Keep every sampled cell active.
   * @param {'contain'|'cover'} [opts.fit='contain'] Image fit inside the sample grid.
   * @param {string[]} [opts.palette] Assign chip colours from image luminance.
   * @param {'luminance'|'alpha'} [opts.mode='luminance']
   * @param {number} [opts.cols]  Grid columns to sample at (required if no grid yet).
   * @param {number} [opts.rows]  Grid rows (computed from image aspect if omitted).
   */
  async setShapeFromImage(src, opts = {}) {
    const {
      threshold = 128,
      invert = false,
      mode = "luminance",
      fill = false,
      fit = "contain",
      palette = null,
    } = opts;

    const img = typeof src === "string" ? await loadImage(src) : src;

    // SVGs (and some programmatically-built images) can report 0 for
    // naturalWidth/Height if they have no explicit width/height attributes,
    // even though they render fine — fall back to a square aspect rather
    // than silently producing NaN grid dimensions.
    const iw = img.naturalWidth || img.width || 512;
    const ih = img.naturalHeight || img.height || iw;

    let cols = opts.cols ?? this.cols;
    let rows = opts.rows ?? this.rows;
    if (!cols) {
      throw new Error("setShapeFromImage: no grid exists yet — pass {cols} (and optionally {rows}).");
    }
    if (!rows) {
      rows = Math.max(1, Math.round(cols * (ih / iw)));
    }

    const off = document.createElement("canvas");
    off.width = cols;
    off.height = rows;
    const offCtx = off.getContext("2d");
    offCtx.imageSmoothingEnabled = true;

    const scale = fit === "cover" ? Math.max(cols / iw, rows / ih) : Math.min(cols / iw, rows / ih);
    const w = iw * scale;
    const h = ih * scale;
    offCtx.drawImage(img, (cols - w) / 2, (rows - h) / 2, w, h);

    const { data } = offCtx.getImageData(0, 0, cols, rows);
    const bitmap = [];
    const colours = [];
    for (let r = 0; r < rows; r++) {
      const row = [];
      const colourRow = [];
      for (let c = 0; c < cols; c++) {
        const i = (r * cols + c) * 4;
        const [red, green, blue, alpha] = [data[i], data[i + 1], data[i + 2], data[i + 3]];
        let value;
        if (mode === "alpha") {
          value = alpha;
        } else {
          value = 0.299 * red + 0.587 * green + 0.114 * blue;
          if (alpha < 10) value = invert ? 255 : 0; // fully transparent -> treat as background
        }
        let on = value > threshold;
        if (invert) on = !on;
        row.push(fill && alpha >= 10 ? 1 : on ? 1 : 0);

        if (palette?.length && alpha >= 10) {
          // In palette mode threshold becomes a tonal midpoint rather than
          // an on/off gate, so the field stays full while the user can move
          // more of the photograph toward either end of the colour range.
          let normalized = (value - threshold + 128) / 255;
          if (invert) normalized = 1 - normalized;
          // Small deterministic dither prevents broad tonal regions from
          // collapsing into hard bands while keeping neighbouring pixels
          // recognisably grouped by the photograph.
          const hash = Math.sin((c + 1) * 127.1 + (r + 1) * 311.7) * 43758.5453;
          const dither = (hash - Math.floor(hash) - 0.5) / palette.length;
          normalized = Math.max(0, Math.min(1, normalized + dither));
          colourRow.push(palette[Math.round(normalized * (palette.length - 1))]);
        } else {
          colourRow.push(null);
        }
      }
      bitmap.push(row);
      colours.push(colourRow);
    }

    if (this.cols === 0) this.resize(cols, rows);
    this.setShapeFromBitmap(bitmap);
    for (const chip of this.chips) {
      chip.color = colours[chip.row]?.[chip.col] || null;
    }
  }

  /**
   * Compute + assign start positions (and per-chip delay) for all currently
   * active chips, using a named or custom scatter pattern, and immediately
   * jump chips to that start position (pre-assemble state).
   */
  scatterIn(pattern = "random") {
    this.stopShimmer();
    const fn = typeof pattern === "function" ? pattern : this.patterns[pattern];
    if (!fn) throw new Error(`Unknown scatter pattern: ${pattern}`);

    const active = this.chips.filter((c) => c.active);
    const patternCtx = {
      cols: this.cols,
      rows: this.rows,
      chipStep: this.chipStep,
      canvasWidth: this.canvas.width,
      canvasHeight: this.canvas.height,
      total: active.length,
    };

    active.forEach((chip, index) => {
      const { x, y, delay } = fn(chip, { ...patternCtx, index });
      chip.startX = x;
      chip.startY = y;
      chip.delay = delay;
      chip.x = x;
      chip.y = y;
      chip.alpha = 1;
      chip.startZ = this._randomZ();
      chip.z = chip.startZ;
      chip.prevX = x;
      chip.prevY = y;
      this._assignCurveAndJitter(chip, x, y, chip.targetX, chip.targetY);
    });

    this.render();
    return this;
  }

  /**
   * Computes and stores a per-chip bezier control point (for organic curved
   * paths) and a per-chip duration multiplier (for non-lockstep timing),
   * based on this.curveAmount / this.durationJitter. Shared by scatterIn()
   * (entrance) and disperse() (exit).
   */
  _assignCurveAndJitter(chip, fromX, fromY, toX, toY) {
    const dx = toX - fromX;
    const dy = toY - fromY;
    const dist = Math.hypot(dx, dy) || 1;

    if (this.curveAmount > 0) {
      const nx = -dy / dist;
      const ny = dx / dist;
      const sign = Math.random() < 0.5 ? -1 : 1;
      const magnitude = dist * this.curveAmount * (0.5 + Math.random() * 0.9);
      chip.curveCx = (fromX + toX) / 2 + nx * magnitude * sign;
      chip.curveCy = (fromY + toY) / 2 + ny * magnitude * sign;
    } else {
      chip.curveCx = null;
      chip.curveCy = null;
    }

    chip.durationScale =
      this.durationJitter > 0
        ? 1 - this.durationJitter / 2 + Math.random() * this.durationJitter
        : 1;
  }

  /**
   * Drive the assemble/disperse animation directly from an external progress
   * value (0 = fully scattered, 1 = fully assembled) instead of an internal
   * timer — the building block for scroll-scrubbed animation. Call
   * `scatterIn(pattern)` once first to establish start positions, then call
   * `setProgress(t)` repeatedly (e.g. from a scroll or IntersectionObserver
   * handler) with t derived from however much of the element is in view.
   *
   * @param {number} progress  0-1.
   * @param {object} opts
   * @param {string} [opts.easing='easeOutCubic']
   * @param {number} [opts.staggerSpread=0.5]  Fraction of the 0-1 range used
   *   to spread chip arrival times (per-chip `delay` from the scatter
   *   pattern); the remainder is each chip's individual travel time.
   */
  setProgress(progress, { easing = "easeOutCubic", staggerSpread = 0.5 } = {}) {
    const easeFn = Easing[easing] ?? Easing.easeOutCubic;
    const clamped = Math.min(1, Math.max(0, progress));
    const spread = Math.min(0.95, Math.max(0, staggerSpread));

    for (const chip of this.chips) {
      if (!chip.active) continue;
      const d = Math.min(1, Math.max(0, chip.delay ?? 0)) * spread;
      const local = Math.min(1, Math.max(0, (clamped - d) / (1 - spread)));
      const e = easeFn(local);
      if (chip.curveCx != null) {
        chip.x = quadBezier(chip.startX, chip.curveCx, chip.targetX, e);
        chip.y = quadBezier(chip.startY, chip.curveCy, chip.targetY, e);
      } else {
        chip.x = lerp(chip.startX, chip.targetX, e);
        chip.y = lerp(chip.startY, chip.targetY, e);
      }
      chip.z = lerp(chip.startZ ?? 0, 0, e);
      chip.alpha = e > 0.02 ? 1 : lerp(0, 1, e / 0.02);
    }

    this.render();
    return this;
  }

  /**
   * Animate active chips from their current (start) position into their
   * fixed grid slot. Inactive chips stay hidden.
   */
  assemble({ duration = 900, stagger = 350, easing = "easeOutCubic", onComplete } = {}) {
    this.stopShimmer();
    return this._tween({
      duration,
      stagger,
      easing,
      onComplete: () => {
        onComplete?.();
        if (this.autoShimmer) this.startShimmer();
      },
      getFrom: (c) => ({ x: c.startX, y: c.startY, z: c.startZ ?? 0, alpha: c.alpha || 1 }),
      getTo: () => ({ z: 0, alpha: 1 }),
      useTarget: true,
    });
  }

  /**
   * Animate active chips from their grid slot back out to scatter positions
   * (computed fresh from the given pattern), then mark them inactive.
   */
  disperse({ pattern = "random", duration = 700, stagger = 250, easing = "easeOutCubic", onComplete } = {}) {
    this.stopShimmer();
    const fn = typeof pattern === "function" ? pattern : this.patterns[pattern];
    const active = this.chips.filter((c) => c.active);
    const patternCtx = {
      cols: this.cols,
      rows: this.rows,
      chipStep: this.chipStep,
      canvasWidth: this.canvas.width,
      canvasHeight: this.canvas.height,
      total: active.length,
    };

    const exitTargets = new Map();
    active.forEach((chip, index) => {
      const t = fn(chip, { ...patternCtx, index });
      this._assignCurveAndJitter(chip, chip.x, chip.y, t.x, t.y);
      exitTargets.set(chip, { ...t, z: this._randomZ() });
    });

    return this._tween({
      duration,
      stagger,
      easing,
      getFrom: (c) => ({ x: c.x, y: c.y, z: c.z ?? 0, alpha: 1 }),
      getTo: (c) => {
        const t = exitTargets.get(c);
        return { x: t.x, y: t.y, z: t.z, alpha: 0, delay: t.delay };
      },
      useTarget: false,
      onComplete: () => {
        active.forEach((c) => (c.active = false));
        onComplete?.();
      },
    });
  }

  _tween({ duration, stagger, easing, getFrom, getTo, useTarget, onComplete }) {
    if (this._rafId) cancelAnimationFrame(this._rafId);

    const active = this.chips.filter((c) => c.active);
    const easeFn = Easing[easing] ?? Easing.easeOutCubic;
    const start = performance.now();

    const frames = active.map((chip) => {
      const from = getFrom(chip);
      const to = getTo(chip);
      const delayFrac = to.delay ?? chip.delay ?? 0;
      return {
        chip,
        from,
        toX: useTarget ? chip.targetX : to.x,
        toY: useTarget ? chip.targetY : to.y,
        toZ: to.z ?? 0,
        toAlpha: to.alpha ?? 1,
        localDelay: delayFrac * stagger,
      };
    });

    const totalDuration = duration + stagger;

    const step = (now) => {
      const elapsed = now - start;
      let allDone = true;

      for (const f of frames) {
        const localElapsed = elapsed - f.localDelay;
        if (localElapsed < 0) {
          allDone = false;
          continue;
        }
        const localDuration = duration * (f.chip.durationScale || 1);
        const t = Math.min(1, localElapsed / localDuration);
        if (t < 1) allDone = false;
        const e = easeFn(t);
        if (f.chip.curveCx != null) {
          f.chip.x = quadBezier(f.from.x, f.chip.curveCx, f.toX, e);
          f.chip.y = quadBezier(f.from.y, f.chip.curveCy, f.toY, e);
        } else {
          f.chip.x = lerp(f.from.x, f.toX, e);
          f.chip.y = lerp(f.from.y, f.toY, e);
        }
        f.chip.z = lerp(f.from.z ?? 0, f.toZ, e);
        f.chip.alpha = lerp(f.from.alpha, f.toAlpha, e);
      }

      this.render();

      if (!allDone && elapsed < totalDuration + 500) {
        this._rafId = requestAnimationFrame(step);
      } else {
        this._rafId = null;
        onComplete?.();
      }
    };

    this._rafId = requestAnimationFrame(step);
    return this;
  }

  stop() {
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = null;
    this.stopShimmer();
  }

  /**
   * Starts a continuous, looping light-sweep across assembled chips — a
   * subtle "still alive" motion cue for once everything has settled. Runs
   * independently of assemble()/disperse()'s own animation loop and keeps
   * going until stopShimmer() is called or a new scatterIn()/assemble()/
   * disperse() takes over.
   *
   * By default this starts automatically when assemble() completes (see
   * the `autoShimmer` constructor option) — call it directly only if you
   * want to (re)start it manually, e.g. after setProgress() settles.
   *
   * @param {object} opts
   * @param {number} [opts.speed=0.6] Sweeps per second across the diagonal.
   * @param {number} [opts.width=0.28] 0-1. Width of the bright band as a
   *   fraction of the sweep's travel distance.
   * @param {number} [opts.intensity=0.28] 0-1+. Peak brightness boost at
   *   the center of the sweep.
   * @param {number} [opts.angle=-45] Degrees. Direction the sweep travels.
   */
  startShimmer(opts = {}) {
    this.stopShimmer();
    const { speed, width, intensity, angle } = { ...this.shimmerOptions, ...opts };
    const angleRad = (angle * Math.PI) / 180;
    const dirX = Math.cos(angleRad);
    const dirY = Math.sin(angleRad);
    const logicalWidth = Math.max(1, this.cols * this.chipStep - this.gap);
    const logicalHeight = Math.max(1, this.rows * this.chipStep - this.gap);
    const span = Math.abs(logicalWidth * dirX) + Math.abs(logicalHeight * dirY) || 1;
    const halfWidth = Math.max(0.001, width) / 2;
    const start = performance.now();

    const step = (now) => {
      const t = (((now - start) / 1000) * speed) % 1;
      for (const chip of this.chips) {
        if (!chip.active) continue;
        const proj = (chip.targetX * dirX + chip.targetY * dirY) / span; // ~0-1 across the sweep
        let delta = proj - t;
        delta = delta - Math.round(delta); // shortest signed distance, wrapping
        const band = Math.max(0, 1 - Math.abs(delta) / halfWidth);
        chip.shimmer = band * band * intensity; // squared falloff = tighter, brighter peak
      }
      this.render();
      this._shimmerRafId = requestAnimationFrame(step);
    };
    this._shimmerRafId = requestAnimationFrame(step);
    return this;
  }

  /** Stops any running shimmer sweep and clears its per-chip brightness. */
  stopShimmer() {
    if (this._shimmerRafId) cancelAnimationFrame(this._shimmerRafId);
    this._shimmerRafId = null;
    for (const chip of this.chips) chip.shimmer = 0;
  }

  render() {
    const { ctx, canvas } = this;
    ctx.setTransform(1, 0, 0, 1, 0, 0); // clear/fill in actual device pixels
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (this.bgColor !== "transparent") {
      ctx.fillStyle = this.bgColor;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    // Everything below is drawn in logical/CSS pixel coordinates (chip.x,
    // chipSize, etc.) — this transform maps them onto the (possibly denser)
    // backing store, which is what keeps output sharp at any pixelRatio.
    ctx.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);

    const active = this.chips.filter((c) => c.active && c.alpha > 0.01);
    // Painter's algorithm: draw back-to-front by simulated depth so nearer
    // chips (higher z + relief) correctly overlap farther ones.
    if (this.depthAmount > 0 || this.reliefAmount > 0) {
      active.sort((a, b) => a.z + a.relief - (b.z + b.relief));
    }

    const angleRad = (this.lightAngle * Math.PI) / 180;
    const lightDx = Math.cos(angleRad);
    const lightDy = Math.sin(angleRad);

    for (const chip of active) {
      const elevation = chip.relief + chip.z * 0.6;
      const speed = Math.hypot(chip.x - chip.prevX, chip.y - chip.prevY);
      const glow = this.motionGlow > 0 ? Math.min(1, speed / (this.chipSize * 0.6)) * this.motionGlow : 0;
      chip.prevX = chip.x;
      chip.prevY = chip.y;

      const scale = 1 + elevation * 0.5;
      const size = Math.max(1, this.chipSize * scale);
      const cx = chip.x + this.chipSize / 2;
      const cy = chip.y + this.chipSize / 2;
      const dx = cx - size / 2;
      const dy = cy - size / 2;
      const brightness = Math.max(
        -0.6,
        Math.min(0.85, elevation * this.lightIntensity + glow + (chip.shimmer || 0))
      );

      ctx.globalAlpha = chip.alpha;

      const shape = chip.shape || this.chipShape;
      const chipColor = chip.color || this.chipColor;

      if (shape === "ascii") {
        const char = chip.char || this.asciiChars[(chip.col + chip.row) % this.asciiChars.length];
        ctx.fillStyle =
          this.shading === "off"
            ? chip.shimmer
              ? shadeColor(chipColor, chip.shimmer)
              : chipColor
            : shadeColor(chipColor, brightness);
        ctx.font = `${Math.round(size * 1.05)}px ui-monospace, "SF Mono", Menlo, Consolas, monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(char, cx, cy + size * 0.02);
        continue;
      }

      if (this.shading === "gradient") {
        const bevel = this.lightIntensity * 0.5;
        const grad = ctx.createLinearGradient(
          dx - lightDx * size * 0.5, dy - lightDy * size * 0.5,
          dx + lightDx * size * 0.5, dy + lightDy * size * 0.5
        );
        grad.addColorStop(0, shadeColor(chipColor, brightness + bevel));
        grad.addColorStop(1, shadeColor(chipColor, brightness - bevel));
        ctx.fillStyle = grad;
      } else if (this.shading === "flat") {
        ctx.fillStyle = shadeColor(chipColor, brightness);
      } else {
        ctx.fillStyle = chip.shimmer ? shadeColor(chipColor, chip.shimmer) : chipColor;
      }

      ctx.beginPath();
      switch (shape) {
        case "circle":
          ctx.arc(cx, cy, size / 2, 0, Math.PI * 2);
          break;
        case "diamond":
          ctx.moveTo(cx, dy);
          ctx.lineTo(dx + size, cy);
          ctx.lineTo(cx, dy + size);
          ctx.lineTo(dx, cy);
          ctx.closePath();
          break;
        case "triangle":
          ctx.moveTo(cx, dy);
          ctx.lineTo(dx + size, dy + size);
          ctx.lineTo(dx, dy + size);
          ctx.closePath();
          break;
        case "hexagon":
          for (let i = 0; i < 6; i++) {
            const a = (Math.PI / 3) * i - Math.PI / 2;
            const px = cx + (size / 2) * Math.cos(a);
            const py = cy + (size / 2) * Math.sin(a);
            i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
          }
          ctx.closePath();
          break;
        case "square":
        default: {
          const r = Math.min(this.cornerRadius, size / 2);
          roundRect(ctx, dx, dy, size, size, r);
          break;
        }
      }
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0); // leave the context in a neutral state
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function hexToRgb(hex) {
  let h = String(hex).trim().replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  const num = parseInt(h, 16);
  return { r: (num >> 16) & 255, g: (num >> 8) & 255, b: num & 255 };
}

/** Lighten (amt > 0) or darken (amt < 0) a hex color; amt is -1..1. */
function shadeColor(hex, amt) {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex; // non-hex input (e.g. named color) — no-op fallback
  const target = amt >= 0 ? 255 : 0;
  const p = Math.min(1, Math.abs(amt));
  const nr = Math.round(rgb.r + (target - rgb.r) * p);
  const ng = Math.round(rgb.g + (target - rgb.g) * p);
  const nb = Math.round(rgb.b + (target - rgb.b) * p);
  return `rgb(${nr}, ${ng}, ${nb})`;
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/**
 * Record a canvas's animation to a video Blob using MediaRecorder, trying
 * each mimeType in `mimeTypeCandidates` in order until one is supported.
 *
 * `videoBitsPerSecond` matters more than it might seem: MediaRecorder's
 * default bitrate on a canvas-capture stream is tuned conservatively, and
 * with a mostly-static/geometric source like a chip grid it can produce
 * visibly blocky, soft output (especially once uploaded/re-encoded on a
 * website). This defaults to a considerably higher bitrate for crisp
 * output; raise it further (and/or pair with a higher `pixelRatio` via
 * `field.setPixelRatio()`) if you still see compression artifacts.
 *
 * A `timeslice` is passed to `recorder.start()` so data is flushed
 * periodically rather than only on stop — on some canvas-capture streams,
 * omitting this produces an empty (or near-empty) recording.
 *
 * If `onRecordingStarted` is given, it's called right after the recorder
 * actually starts (not before) — use it to kick off the animation you want
 * captured, so the very first frames of motion aren't missed or raced.
 */
function recordCanvasToVideo(
  canvas,
  {
    durationMs = 2000,
    fps = 30,
    videoBitsPerSecond = 12_000_000,
    mimeTypeCandidates,
    fileExt,
    onRecordingStarted,
  } = {}
) {
  if (!canvas.captureStream) {
    return Promise.reject(new Error("canvas.captureStream() isn't supported in this browser."));
  }
  if (!window.MediaRecorder) {
    return Promise.reject(new Error("MediaRecorder isn't supported in this browser."));
  }
  const mimeType = mimeTypeCandidates.find((t) => MediaRecorder.isTypeSupported(t));
  if (!mimeType) {
    return Promise.reject(
      new Error(`No supported codec found for .${fileExt} in this browser (tried: ${mimeTypeCandidates.join(", ")}).`)
    );
  }

  const stream = canvas.captureStream(fps);
  const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond });
  const chunks = [];
  recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);

  return new Promise((resolve, reject) => {
    recorder.onerror = (e) => reject(e.error || new Error("MediaRecorder error"));
    recorder.onstop = () => {
      if (chunks.length === 0) {
        reject(new Error("No frames were captured."));
        return;
      }
      resolve(new Blob(chunks, { type: mimeType }));
    };
    recorder.start(100); // 100ms timeslice: periodic flush, avoids empty output
    onRecordingStarted?.();
    setTimeout(() => recorder.stop(), durationMs);
  });
}

/** Record to WebM (widely supported; convert to MP4/GIF with ffmpeg if needed). */
export function recordCanvasToWebM(canvas, opts = {}) {
  return recordCanvasToVideo(canvas, {
    ...opts,
    fileExt: "webm",
    mimeTypeCandidates: ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"],
  });
}

/**
 * Record to MP4 directly (supported in Safari and recent Chromium/Edge
 * versions via MediaRecorder; falls back with a clear error if the browser
 * can't produce MP4 — record WebM and convert with ffmpeg in that case).
 */
export function recordCanvasToMP4(canvas, opts = {}) {
  return recordCanvasToVideo(canvas, {
    ...opts,
    fileExt: "mp4",
    mimeTypeCandidates: [
      "video/mp4;codecs=avc1.42E01E",
      "video/mp4;codecs=h264",
      "video/mp4",
    ],
  });
}
