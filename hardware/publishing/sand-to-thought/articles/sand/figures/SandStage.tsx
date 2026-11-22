import { memo } from "react";

// The animation owns the SVG descendants after mounting.
export const SandStage = memo(() => (
  <div className="stage">
    <svg id="stage-svg" viewBox="0 0 440 440" aria-hidden="true">
      <defs>
        <clipPath id="crop">
          <rect id="crop-rect" x="0" y="0" width="440" height="440" />
        </clipPath>
      </defs>
      <g id="art">
        <ellipse id="shadow" />
        <path id="mesh" />
        <g id="parts" clipPath="url(#crop)" />
        <g id="d2" />
      </g>
    </svg>
  </div>
));
