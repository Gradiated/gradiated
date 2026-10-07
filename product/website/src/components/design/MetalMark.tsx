import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { Logo } from "./Logo";

/**
 * The Gradiated mark in liquid metal.
 *
 * metal-fx's components draw rings around hosts or fill font glyphs —
 * neither fits a drawn logotype — so this goes under the hood: the
 * low-level instance paints a SOLID metal tile (a "ring" as thick as the
 * tile itself) into our canvas, and the mark's own alpha (the exported
 * PNG) masks it, so the metal lives exactly in the logo's silhouette.
 *
 * The plain ink mark renders first and stays for anyone without WebGL2
 * or with reduced motion; the metal cross-fades over it on the first
 * painted frame. Dynamically imported — client-only, prerender-safe.
 */

export const MetalMark = (): ReactElement => {
  const hostRef = useRef<HTMLSpanElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let cancelled = false;
    let mod: typeof import("metal-fx") | null = null;
    let inst: ReturnType<typeof import("metal-fx").createInstance> | null =
      null;

    void import("metal-fx").then((m) => {
      if (cancelled || !m.isMetalFxSupported()) return;
      mod = m;
      const box = host.getBoundingClientRect();
      if (box.width < 4) return;
      inst = m.createInstance({
        hostCanvas: canvas,
        cssWidth: box.width,
        cssHeight: box.height,
        /* a ring as thick as the tile: the "ring" becomes a solid fill */
        cornerRadius: box.width * 0.22,
        kind: "pill",
        ringCssPx: Math.ceil(Math.max(box.width, box.height)),
        onFirstCopy: () => host.classList.add("gr-metal-mark--on"),
      });
    });

    return () => {
      cancelled = true;
      if (mod && inst) mod.destroyInstance(inst);
    };
  }, []);

  return (
    <span className="gr-metal-mark" ref={hostRef}>
      <Logo mark />
      <canvas aria-hidden ref={canvasRef} />
    </span>
  );
};
