/**
 * Types for the vendored `wafer-field.js` particle-assembly engine.
 *
 * The engine is authored in plain JS and vendored verbatim from the
 * wafer-field project — do not edit `wafer-field.js` here; change it upstream
 * and re-copy, or the two drift. This file is hand-written and covers only the
 * surface the site actually uses.
 */

export type ScatterPattern =
  | "gravity-drop"
  | "orbit-in"
  | "radial-burst"
  | "random"
  | "spiral-in"
  | "wave-rise";

export type EasingName =
  | "easeInOutCubic"
  | "easeInOutQuad"
  | "easeOutBack"
  | "easeOutCubic"
  | "easeOutElastic"
  | "easeOutExpo"
  | "easeOutQuad"
  | "easeOutQuart"
  | "easeOutQuint"
  | "linear";

export type WaferFieldOptions = {
  autoShimmer?: boolean;
  /** Fills the canvas behind the chips. Leave unset for a transparent field. */
  bgColor?: string | null;
  chipColor?: string;
  /** Chip edge length in CSS px; `chipStep` is this plus `gap`. */
  chipSize?: number;
  /** 0 = square. The design system has no rounded corners. */
  cornerRadius?: number;
  /** Bows each chip's path; 0 is perfectly mechanical. */
  curveAmount?: number;
  durationJitter?: number;
  gap?: number;
  depthAmount?: number;
  chipShape?: "ascii" | "circle" | "diamond" | "hexagon" | "square" | "triangle";
  pixelRatio?: number;
  shading?: "flat" | "gradient" | "off";
  shimmer?: ShimmerOptions;
};

export type ShimmerOptions = {
  /** Sweep direction in degrees. */
  angle?: number;
  /** Peak brightness boost at the band's centre, 0-1+. */
  intensity?: number;
  /** Sweeps per second. */
  speed?: number;
  /** Band width as a fraction of the sweep's travel. */
  width?: number;
};

export type SampleOptions = {
  cols?: number;
  fill?: boolean;
  fit?: "contain" | "cover";
  invert?: boolean;
  /** "alpha" suits flat-filled SVG marks; "luminance" suits photographs. */
  mode?: "alpha" | "luminance";
  rows?: number;
  palette?: string[];
  threshold?: number;
};

export type Chip = {
  active: boolean;
  color?: string | null;
  col: number;
  row: number;
  targetX: number;
  targetY: number;
};

export type PatternContext = {
  canvasHeight: number;
  canvasWidth: number;
  chipStep: number;
  cols: number;
  index: number;
  rows: number;
  total: number;
};

export declare class WaferField {
  constructor(canvas: HTMLCanvasElement, options?: WaferFieldOptions);

  /** Writable: re-assign and call render() to recolour without rebuilding. */
  chipColor: string;
  /** Writable, like chipColor — chipStep reads from these two, so assigning
   *  them and calling resize() rebuilds the grid at a new chip scale. They
   *  were declared on the options only, which is why setting them was a type
   *  error even though the engine has always carried them as properties. */
  chipSize: number;
  gap: number;
  readonly chipStep: number;
  chips: Chip[];
  cols: number;
  rows: number;

  /** Rebuilds the chip grid. Clears any shape already applied. */
  resize(cols: number, rows: number): this;
  setPixelRatio(ratio: number): this;

  /** 1 = an active chip, 0 = empty. Outer array is rows. */
  setShapeFromBitmap(bitmap: number[][]): this;

  setShapeFromImage(
    src: HTMLImageElement | string,
    opts?: SampleOptions,
  ): Promise<this>;

  /**
   * Adds a named scatter pattern. The function returns each chip's entrance
   * position and its 0-1 stagger order.
   */
  registerScatterPattern(
    name: string,
    fn: (chip: Chip, ctx: PatternContext) => { delay: number; x: number; y: number },
  ): void;

  /** Moves chips to their entrance positions and fixes their stagger order. */
  scatterIn(pattern?: ScatterPattern | string): this;

  /**
   * Positions every chip from a 0-1 value, bypassing the internal timer —
   * this is the scroll-scrubbing entry point.
   */
  setProgress(
    progress: number,
    opts?: { easing?: EasingName; staggerSpread?: number },
  ): this;

  /** Loops a brightness band across the assembled shape until stopped. */
  startShimmer(opts?: ShimmerOptions): this;
  stopShimmer(): void;

  render(): void;
  stop(): void;
  assemble(opts?: {
    duration?: number;
    easing?: EasingName;
    onComplete?: () => void;
    stagger?: number;
  }): this;
  disperse(opts?: {
    duration?: number;
    easing?: EasingName;
    onComplete?: () => void;
    pattern?: ScatterPattern | string;
    stagger?: number;
  }): this;
}

export function recordCanvasToWebM(
  canvas: HTMLCanvasElement,
  opts?: {
    durationMs?: number;
    fps?: number;
    onRecordingStarted?: () => void;
    videoBitsPerSecond?: number;
  },
): Promise<Blob>;

export function recordCanvasToMP4(
  canvas: HTMLCanvasElement,
  opts?: {
    durationMs?: number;
    fps?: number;
    onRecordingStarted?: () => void;
    videoBitsPerSecond?: number;
  },
): Promise<Blob>;
