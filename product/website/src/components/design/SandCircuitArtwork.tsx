import { useEffect, useId, useRef } from "react";
import type { ReactElement } from "react";
import { mountSandCircuit } from "./sand-circuit-animation";
import "./sand-circuit.css";

export const SandCircuitArtwork = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pattern = useId().replace(/:/g, "");

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    return mountSandCircuit(host, canvas);
  }, []);

  return (
    <div aria-hidden className="gr-sand-artwork" ref={hostRef}>
      <svg
        className="gr-sand-poster"
        viewBox="0 0 960 600"
        preserveAspectRatio="none"
      >
        <defs>
          <pattern
            id={pattern}
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="2" cy="2" r="1.3" fill="#a17e4c" />
          </pattern>
        </defs>
        <path
          d="M0 310 Q240 150 410 175 Q600 170 960 350 V600 H0Z"
          fill={`url(#${pattern})`}
        />
      </svg>
      <canvas ref={canvasRef} />
    </div>
  );
};
