import { useEffect, useRef } from "react";
import type { ReactElement } from "react";

/**
 * The bottom haze (Figma 509:645): a fixed backdrop-blur wash over the
 * viewport's bottom edge, so content dissolves off the page instead of
 * being cut by it.
 *
 * It holds back on the hero — the first fold owns its own atmosphere —
 * fades in once the reader has scrolled past most of it, and steps aside
 * again when the footer rises underneath (a fixed veil over the footer
 * would blur links the reader is about to click).
 *
 * The five <i> layers are the progressive blur: backdrop-filter cannot
 * ramp within one element, so successive bands double the radius.
 */

export const BottomHaze = (): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let raf = 0;
    const footer = document.querySelector(".gr-footer");
    const check = (): void => {
      raf = 0;
      const pastHero = scrollY > innerHeight * 0.8;
      /* off once the footer's top clears the haze's own top edge */
      const footerUnder =
        footer !== null &&
        footer.getBoundingClientRect().top < innerHeight * 0.9;
      host.classList.toggle("gr-bottom-haze--on", pastHero && !footerUnder);
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

  return (
    <div aria-hidden="true" className="gr-bottom-haze" ref={hostRef}>
      <i />
      <i />
      <i />
      <i />
      <i />
    </div>
  );
};
