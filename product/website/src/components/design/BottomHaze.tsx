import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The bottom haze (Figma 509:645): a fixed backdrop-blur wash over the
 * viewport's bottom edge, so content dissolves off the page instead of
 * being cut by it.
 *
 * It holds back on the hero — the first fold owns its own atmosphere —
 * and fades in once the reader has scrolled past most of it.
 */

export const BottomHaze = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let raf = 0;
    const check = (): void => {
      raf = 0;
      host.classList.toggle("gr-bottom-haze--on", scrollY > innerHeight * 0.8);
    };
    const onScroll = (): void => {
      if (!raf) raf = requestAnimationFrame(check);
    };
    check();
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return <div aria-hidden="true" className="gr-bottom-haze" ref={hostRef} />;
};
