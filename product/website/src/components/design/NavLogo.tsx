import { useId } from "react";
import type { CSSProperties, ReactElement } from "react";

/**
 * The nav's logo: the final angular wordmark plate (from
 * gradiated-wordmark-final.svg), inlined so the plate paints with
 * `currentColor` and the theme restyles it with no asset changes. The
 * letterforms are filled with the substrate token, so they read as
 * knockouts on any ground.
 *
 * The gradient def mirrors Logo.tsx's hover affordance: nav.css points
 * the PLATE's fill at var(--logo-gradient) on hover (the letters stay
 * substrate), and the stops read the theme's own tokens.
 */

export const NAV_LOGO_ASPECT = 147 / 30;

const LETTERS = [
  "M94.4348 6.2124H87.6506L83.6372 10.5219V21.1629H88.1646V16.85H93.0153V21.1629H97.5461V10.5015H94.4348V6.2124ZM93.0153 13.5039H88.1646V10.5049H93.0153V13.5039Z",
  "M63.6961 6.20898H53.7529V21.1629H63.6961L67.6789 16.8738V10.5015L63.6961 6.21239V6.20898ZM63.1447 16.8636H58.2973V10.4981H63.1447V16.8636Z",
  "M77.9046 10.5253H81.918V6.2124H76.8221L75.6375 7.3936L74.4529 6.2124H69.3877V10.5253H73.3738V16.85H69.3877V21.1629H74.4529L75.6375 20.0022L76.8221 21.1629H81.918V16.85H77.9046V10.5253Z",
  "M48.7288 6.2124H41.9445L37.9312 10.5219V21.1629H42.4585V16.85H47.3093V21.1629H51.8401V10.5015H48.7288V6.2124ZM47.3093 13.5039H42.4585V10.5049H47.3093V13.5039Z",
  "M22.1465 6.2124V10.5015H22.1499V13.5345H22.1465L22.1499 16.8739V21.1629H26.6807V16.8739H29.472L33.2368 21.1629H36.1337V16.8739L32.7603 13.5345H26.6807V10.5015H30.0813L32.7671 13.5345H36.1337V10.5117L32.4948 6.2124H22.1465Z",
  "M5.96729 10.5015V16.8739H9.62663V21.1664H15.713L20.3017 16.8739V13.5243L17.1836 13.5175L13.5481 16.8739H10.1577L10.5015 10.5015H20.3017V6.21582H10.2836L5.96729 10.5015Z",
  "M137.258 6.20898H127.314V21.1629H137.258L141.24 16.8738V10.5015L137.258 6.21239V6.20898ZM136.703 16.8636H131.855V10.4981H136.703V16.8636Z",
  "M112.582 10.5045V12.0737H116.125L112.582 15.8522V17.3874L116.595 21.1659H125.554V17.3874H116.186L117.667 15.8522H124.257V12.0737H117.296L118.777 10.5045H125.554V6.22559H116.598L112.582 10.5045Z",
  "M106.379 6.21582L105.215 7.38L104.051 6.21582H102.686H98.7373V10.5015H102.914V21.163H105.161H107.445V10.5015H111.696V6.21582H107.642H106.379Z",
] as const;

export const NavLogo = (): ReactElement => {
  const gradientId = `gr-navlogo-${useId()}`;
  return (
    <svg
      aria-label="Gradiated"
      fill="none"
      height={24}
      role="img"
      style={{ "--logo-gradient": `url(#${gradientId})` } as CSSProperties}
      viewBox="0 0 147 30"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient
          gradientUnits="userSpaceOnUse"
          id={gradientId}
          x1="0"
          x2="147"
          y1="0"
          y2="0"
        >
          <stop offset="0" stopColor="var(--gradient-from)" />
          <stop offset="1" stopColor="var(--gradient-to)" />
        </linearGradient>
      </defs>
      <path
        className="gr-navlogo-plate"
        d="M138.762 29.3939H0V8.14246L8.30245 0H147V20.9995L138.762 29.3939Z"
        fill="currentColor"
      />
      {LETTERS.map((d) => (
        <path d={d} fill="var(--color-substrate)" key={d.slice(0, 16)} />
      ))}
    </svg>
  );
};
