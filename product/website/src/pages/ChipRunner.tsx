import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/* "Get your own model running", literally: a little chip with arms and
   legs running along a ground line and hopping over bugs and stray
   components, in a one-colour 8-bit side-scroller. Original pixel art,
   drawn on a 240x64 canvas scaled up with hard pixels, in the page's ink.

   It plays itself (the chip jumps on its own), and a tap, click or the
   space bar makes it jump too. It only runs while on screen, and holds a
   single still frame for reduced motion. Decorative: hidden from assistive
   tech; the heading beside it carries the meaning. */

const W = 240;
const H = 64;
const GROUND = 52;
/* The chip's top when standing: body (10 rows) and legs (3) end on the
   ground line. */
const STAND = GROUND - 13;

type Sprite = readonly string[];

/* The chip: pins on top, a hollow body with eyes and a die, arms out. */
const BODY: Sprite = [
  "   # # # # #   ",
  "  ###########  ",
  "  #.........#  ",
  "  #..#...#..#  ",
  "  #.........#  ",
  "  #..#####..#  ",
  "  #..#...#..#  ",
  "  #..#####..#  ",
  "  #.........#  ",
  "  ###########  ",
];

/* Arms, by frame: swinging as it runs, up when it jumps. */
const ARMS: Record<string, Sprite> = {
  a: ["", "", "", "", "#             #", " #           # "],
  b: ["", "", "", "", "", " #           # ", "#             #"],
  up: ["", "#             #", " #           # ", "", "", ""],
};

/* Legs, by frame, under the body. */
const LEGS: Record<string, Sprite> = {
  a: ["    #     #    ", "   #       #   ", "   #        #  "],
  b: ["     #   #     ", "     #   #     ", "    #     #    "],
  up: ["    ##   ##    ", "               "],
};

const OBSTACLES: Sprite[] = [
  /* A bug. */
  [" #   # ", "  ###  ", "#######", " ##### ", "# # # #"],
  /* A capacitor. */
  [" ### ", "#   #", "#   #", "#   #", " ### ", " # # ", " # # "],
  /* A stray resistor, standing. */
  ["  #  ", " ### ", " # # ", " ### ", " # # ", " ### ", "  #  ", "  #  "],
];

const CLOUD: Sprite = [
  "    ####    ",
  "  ##    ##  ",
  " #        ##",
  "############",
];

const draw = (
  context: CanvasRenderingContext2D,
  sprite: Sprite,
  x: number,
  y: number,
) => {
  sprite.forEach((row, dy) => {
    for (let dx = 0; dx < row.length; dx += 1)
      if (row[dx] === "#")
        context.fillRect(Math.round(x) + dx, Math.round(y) + dy, 1, 1);
  });
};

export const ChipRunner = (): ReactElement => {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    let ink = getComputedStyle(element).color;
    let frame = 0;
    let visible = false;
    let last = 0;

    /* The world, in canvas pixels. */
    const chip = { x: 28, y: STAND, vy: 0, step: 0 };
    let speed = 1.5;
    let groundShift = 0;
    let obstacles: { x: number; sprite: Sprite }[] = [
      { x: 170, sprite: OBSTACLES[0] },
    ];
    const clouds = [
      { x: 40, y: 10 },
      { x: 150, y: 18 },
    ];
    const pebbles = Array.from({ length: 14 }, (_, n) => ({
      x: (n * 37) % W,
      y: GROUND + 3 + ((n * 7) % 7),
      w: 1 + (n % 3),
    }));

    const onGround = () => chip.y >= STAND && chip.vy === 0;
    const jump = () => {
      if (onGround()) chip.vy = -3.1;
    };

    const update = (dt: number) => {
      const k = dt / (1000 / 60);
      speed = Math.min(2.6, speed + 0.0004 * k);
      groundShift = (groundShift + speed * k) % W;

      /* Gravity. */
      if (chip.vy !== 0 || chip.y < STAND) {
        chip.vy += 0.16 * k;
        chip.y += chip.vy * k;
        if (chip.y >= STAND) {
          chip.y = STAND;
          chip.vy = 0;
        }
      }
      chip.step += speed * k * 0.12;

      /* Obstacles scroll in; the chip clears them on its own. */
      for (const obstacle of obstacles) obstacle.x -= speed * k;
      obstacles = obstacles.filter((obstacle) => obstacle.x > -12);
      const lastObstacle = obstacles[obstacles.length - 1];
      if (!lastObstacle || lastObstacle.x < W - 70 - Math.random() * 90)
        if (Math.random() < 0.02 * k)
          obstacles.push({
            x: W + 4,
            sprite: OBSTACLES[Math.floor(Math.random() * OBSTACLES.length)],
          });
      const next = obstacles.find((obstacle) => obstacle.x + 7 > chip.x + 2);
      if (next && next.x - (chip.x + 14) < 10 + speed * 4) jump();

      for (const cloud of clouds) {
        cloud.x -= speed * 0.25 * k;
        if (cloud.x < -14) {
          cloud.x = W + Math.random() * 40;
          cloud.y = 6 + Math.round(Math.random() * 14);
        }
      }
    };

    const render = () => {
      context.clearRect(0, 0, W, H);
      context.fillStyle = ink;

      for (const cloud of clouds) {
        context.globalAlpha = 0.35;
        draw(context, CLOUD, cloud.x, cloud.y);
      }
      context.globalAlpha = 1;

      /* The ground: a line, and pebbles scrolling past under it. */
      context.fillRect(0, GROUND, W, 1);
      for (const pebble of pebbles) {
        const x = (((pebble.x - groundShift) % W) + W) % W;
        context.globalAlpha = 0.6;
        context.fillRect(Math.round(x), pebble.y, pebble.w, 1);
      }
      context.globalAlpha = 1;

      for (const obstacle of obstacles)
        draw(
          context,
          obstacle.sprite,
          obstacle.x,
          GROUND - obstacle.sprite.length,
        );

      const airborne = chip.y < STAND;
      const pose = airborne ? "up" : Math.floor(chip.step) % 2 ? "a" : "b";
      draw(context, BODY, chip.x, chip.y);
      draw(context, ARMS[pose], chip.x, chip.y);
      draw(context, LEGS[pose], chip.x, chip.y + BODY.length);
    };

    const loop = (time: number) => {
      const dt = last ? Math.min(50, time - last) : 1000 / 60;
      last = time;
      update(dt);
      render();
      frame = requestAnimationFrame(loop);
    };

    const sync = () => {
      cancelAnimationFrame(frame);
      last = 0;
      ink = getComputedStyle(element).color;
      if (still.matches || !visible) render();
      else frame = requestAnimationFrame(loop);
    };

    const seen = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    seen.observe(element);
    /* The ink follows the theme. */
    const themed = new MutationObserver(sync);
    themed.observe(document.documentElement, {
      attributeFilter: ["data-theme"],
      attributes: true,
      subtree: true,
    });

    const press = (event: KeyboardEvent) => {
      if (event.code !== "Space" || !visible) return;
      if (
        event.target instanceof HTMLElement &&
        event.target.closest("input, textarea, button, a")
      )
        return;
      jump();
    };
    element.addEventListener("pointerdown", jump);
    window.addEventListener("keydown", press);
    still.addEventListener("change", sync);
    render();

    return () => {
      cancelAnimationFrame(frame);
      seen.disconnect();
      themed.disconnect();
      element.removeEventListener("pointerdown", jump);
      window.removeEventListener("keydown", press);
      still.removeEventListener("change", sync);
    };
  }, []);

  return (
    <canvas
      aria-hidden="true"
      className="gr-chip-runner"
      height={H}
      ref={canvas}
      width={W}
    />
  );
};
