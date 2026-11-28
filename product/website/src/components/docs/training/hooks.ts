import { useEffect, useState } from "react";
import type { RefObject } from "react";

export const usePrefersReducedMotion = (): boolean => {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
};

/** True once the element comes within a screen of the viewport. */
export const useNearViewport = (ref: RefObject<Element | null>): boolean => {
  const [near, setNear] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element || near) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setNear(true);
      },
      { rootMargin: "100% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, near]);

  return near;
};
