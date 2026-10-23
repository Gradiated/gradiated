import type { ReactElement } from "react";
import { ReflectiveCard } from "./ReflectiveCard";

/**
 * The employee badge: a portrait metal ID card (React Bits' reflective
 * plate under our face) that tilts under the pointer. The surface's
 * light is synthetic — no camera, nothing asked of the reader. Its
 * entrance is choreographed by the section around it.
 */

export const BadgeCard = (): ReactElement => (
  <div className="gr-idcard">
    <ReflectiveCard height={430} radius={16} theme="dark" width={276}>
      <div className="gr-idcard-face">
        {/* The G alone, no tile — top left. */}
        <img alt="" className="gr-idcard-mark" src="/brand/mark-glyph.svg" />
        <div className="gr-idcard-id">
          <span className="gr-idcard-label">Employee</span>
          <span className="gr-idcard-number"># YOU-2026</span>
        </div>
      </div>
    </ReflectiveCard>
  </div>
);
