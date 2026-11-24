import { useEffect, useState } from "react";

/* For canvases, which cannot read CSS variables: the probe resolves var()
   chains and the canvas turns any color syntax into sRGB bytes. */
export const resolveColor = (host: HTMLElement, property: string): number => {
  const probe = document.createElement("span");
  probe.style.color = `var(${property})`;
  host.append(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();

  const context = document.createElement("canvas").getContext("2d");
  if (!context) return 0;

  context.fillStyle = color;
  context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;

  return (r << 16) | (g << 8) | b;
};

/** Changes whenever the theme does, so a canvas can redraw in the new colors. */
export const useThemeVersion = (): number => {
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setVersion((value) => value + 1),
    );
    observer.observe(document.documentElement, {
      attributeFilter: ["data-theme"],
      subtree: true,
    });

    return () => observer.disconnect();
  }, []);

  return version;
};
