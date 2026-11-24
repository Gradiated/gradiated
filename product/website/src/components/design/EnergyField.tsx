import { type ReactElement, useEffect, useRef } from "react";

export type EnergyFieldProps = {
  angle?: number;
  /** Blur, in px, reached at the bottom edge; it grows down the field. */
  blur?: number;
  className?: string;
  density?: number;
  ground: string;
  ink: string;
  /** The bars' and spiral dashes' length in px. */
  length?: number;
  /** False holds the swarm where it is. */
  moving?: boolean;
  /** Riso grain over the field, 0 to 1. */
  noise?: number;
  noiseColor?: string;
  /** Bars and bits drift along `angle`; a spiral turns about a point, its
      way set by `angle`. */
  shape?: "bars" | "bits" | "spiral";
  /** A bar's or dash's thickness, or a bit's side, in px. */
  size?: number;
  speed?: number;
};

/** 128px of monochrome speckle, half of it transparent. */
const noiseTile = (): HTMLCanvasElement => {
  const tile = document.createElement("canvas");
  tile.width = 128;
  tile.height = 128;
  const context = tile.getContext("2d");
  if (!context) return tile;

  const image = context.createImageData(128, 128);
  for (let i = 0; i < image.data.length; i += 4) {
    const value = Math.random() * 255;
    image.data[i] = image.data[i + 1] = image.data[i + 2] = value;
    image.data[i + 3] = Math.random() < 0.5 ? 255 : 0;
  }
  context.putImageData(image, 0, 0);

  return tile;
};

export const EnergyField = ({
  angle = 24,
  blur = 6,
  className,
  density = 0.6,
  ground,
  ink,
  length = 14,
  moving = true,
  noise = 0.35,
  noiseColor = "#ffffff",
  shape = "bars",
  size = 1,
  speed = 1,
}: EnergyFieldProps): ReactElement => {
  const ref = useRef<HTMLCanvasElement>(null);
  const settings = {
    angle,
    blur,
    density,
    ground,
    ink,
    length,
    moving,
    noise,
    noiseColor,
    shape,
    size,
    speed,
  };
  const current = useRef(settings);
  current.current = settings;
  const resume = useRef<() => void>(undefined);

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    const ink = document.createElement("canvas");
    const inkContext = ink.getContext("2d");
    if (!canvas || !context || !inkContext) return;

    const tile = noiseTile();
    const grain = document.createElement("canvas");
    grain.width = 128;
    grain.height = 128;
    const grainContext = grain.getContext("2d");
    let grainColor = "";
    const tint = (color: string) => {
      if (!grainContext || grainColor === color) return;
      grainContext.globalCompositeOperation = "source-over";
      grainContext.clearRect(0, 0, 128, 128);
      grainContext.drawImage(tile, 0, 0);
      grainContext.globalCompositeOperation = "source-in";
      grainContext.fillStyle = color;
      grainContext.fillRect(0, 0, 128, 128);
      grainColor = color;
    };

    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ratio = Math.min(2, devicePixelRatio || 1);
    let width = 0;
    let height = 0;
    let diagonal = 0;
    let particles: Array<{ a: number; v: number; x: number; y: number }> = [];
    let seeded = "";
    let centre = { x: 0, y: 0 };
    let turn = 0;
    let frame = 0;
    let visible = false;

    const SPIRAL_GAP = 22;
    const SPIRAL_ARMS = 2;

    const seed = () => {
      const field = current.current;
      seeded = field.shape;

      const count = Math.max(
        220,
        Math.round(((width * height) / 700) * field.density),
      );

      if (field.shape === "spiral") {
        // Spread evenly along the arms: x is the radius, y the arm's angle.
        centre = {
          x: width * (0.2 + Math.random() * 0.6),
          y: height * (0.2 + Math.random() * 0.6),
        };
        particles = Array.from({ length: count }, () => {
          const radius = diagonal * Math.sqrt(Math.random());
          const arm = Math.floor(Math.random() * SPIRAL_ARMS);
          return {
            a: 0.55 + Math.random() * 0.45,
            v: 0,
            x: radius,
            y:
              (2 * Math.PI * radius) / SPIRAL_GAP +
              (arm * 2 * Math.PI) / SPIRAL_ARMS,
          };
        });
        return;
      }

      particles = Array.from({ length: count }, () => ({
        a: 0.55 + Math.random() * 0.45,
        v: 0.4 + Math.random() * 1.2,
        x: Math.random() * diagonal,
        y: Math.random() * diagonal,
      }));
    };

    const resize = () => {
      // Its layout size: a scaled or tilted parent leaves this untouched.
      width = Math.max(1, canvas.clientWidth);
      height = Math.max(1, canvas.clientHeight);
      canvas.width = ink.width = Math.round(width * ratio);
      canvas.height = ink.height = Math.round(height * ratio);
      diagonal = Math.ceil(Math.hypot(width, height));
      seed();
    };

    const draw = () => {
      frame = 0;
      const field = current.current;
      if (seeded !== field.shape) seed();
      const flowing = !still && field.moving;

      inkContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      inkContext.clearRect(0, 0, width, height);

      if (field.shape === "spiral") {
        const way = ((field.angle % 360) + 360) % 360 < 180 ? 1 : -1;
        if (flowing) turn += way * field.speed * 0.004;

        inkContext.strokeStyle = field.ink;
        inkContext.lineWidth = field.size;
        inkContext.globalAlpha = 0.85;
        inkContext.beginPath();
        for (const { x: radius, y: arm } of particles) {
          const theta = arm + turn;
          const [cos, sin] = [Math.cos(theta), Math.sin(theta)];
          const px = centre.x + radius * cos;
          const py = centre.y + radius * sin;
          if (px < -field.length || px > width + field.length) continue;
          if (py < -field.length || py > height + field.length) continue;
          inkContext.moveTo(px, py);
          inkContext.lineTo(px - sin * field.length, py + cos * field.length);
        }
        inkContext.stroke();
        inkContext.globalAlpha = 1;
      } else {
        const run = field.shape === "bars" ? field.length : field.size;

        // The swarm, drawn in rotated space so it all flows one way.
        inkContext.translate(width / 2, height / 2);
        inkContext.rotate((field.angle * Math.PI) / 180);
        inkContext.translate(-diagonal / 2, -diagonal / 2);
        inkContext.fillStyle = field.ink;
        for (const particle of particles) {
          if (flowing) particle.x += particle.v * field.speed;
          if (particle.x > diagonal + run) particle.x -= diagonal + run * 2;
          inkContext.globalAlpha = particle.a;
          inkContext.fillRect(particle.x - run, particle.y, run, field.size);
        }
        inkContext.globalAlpha = 1;
      }

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.filter = "none";
      context.fillStyle = field.ground;
      context.fillRect(0, 0, width, height);

      // Drawn in fourteen strips, each blurred more than the one above.
      const strips = field.blur > 0.01 ? 14 : 1;
      const strip = height / strips;
      for (let i = 0; i < strips; i++) {
        const amount = (field.blur * i * i) / (strips * strips);
        const pad = Math.ceil(amount) + 1;
        context.filter =
          amount > 0.05 ? `blur(${amount.toFixed(2)}px)` : "none";
        context.drawImage(
          ink,
          0,
          Math.max(0, (i * strip - pad) * ratio),
          width * ratio,
          (strip + pad * 2) * ratio,
          0,
          i * strip - pad,
          width,
          strip + pad * 2,
        );
      }
      context.filter = "none";

      // Grain over the top, and a sparse dropout through to the page.
      if (field.noise > 0.01) {
        tint(field.noiseColor);
        const pattern = context.createPattern(grain, "repeat");
        if (pattern) {
          context.fillStyle = pattern;
          context.globalAlpha = field.noise * 0.3;
          context.fillRect(0, 0, width, height);
          context.globalAlpha = field.noise * 0.08;
          context.globalCompositeOperation = "destination-out";
          context.fillRect(0, 0, width, height);
          context.globalCompositeOperation = "source-over";
          context.globalAlpha = 1;
        }
      }

      if (flowing && visible) frame = requestAnimationFrame(draw);
    };

    const start = () => {
      if (!frame) frame = requestAnimationFrame(draw);
    };
    resume.current = start;

    const resized = new ResizeObserver(() => {
      resize();
      start();
    });
    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
    });
    resized.observe(canvas);
    seen.observe(canvas);

    return () => {
      cancelAnimationFrame(frame);
      resized.disconnect();
      seen.disconnect();
      resume.current = undefined;
    };
  }, []);

  useEffect(() => {
    if (moving) resume.current?.();
  }, [moving]);

  return (
    <canvas
      aria-hidden="true"
      className={`gr-energy-field${className ? ` ${className}` : ""}`}
      ref={ref}
    />
  );
};
