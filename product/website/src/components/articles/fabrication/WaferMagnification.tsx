import { useLayoutEffect, useRef, useState } from "react";
import { waferDetailRegion } from "./process";

type Point = [number, number];
type Transform = Pick<DOMMatrix, "a" | "b" | "c" | "d" | "e" | "f">;
type Layout = { wafer: Transform; detail: Transform };

const transformPoint = ([x, y]: Point, matrix: Transform): Point => [
  matrix.a * x + matrix.c * y + matrix.e,
  matrix.b * x + matrix.d * y + matrix.f,
];

export const WaferMagnification = ({
  corners,
  opacity = 1,
  progress = 1,
}: {
  opacity?: number;
  progress?: number;
  corners: [Point, Point];
}) => {
  const overlay = useRef<SVGSVGElement>(null);
  const [layout, setLayout] = useState<Layout>();

  useLayoutEffect(() => {
    const host = overlay.current?.parentElement;
    const wafer = host?.querySelector<SVGSVGElement>(".fab-whole-wafer");
    const detail = host?.querySelector<SVGSVGElement>(
      ".fab-pattern-model > svg",
    );
    if (!host || !wafer || !detail) return;

    const measure = () => {
      const waferMatrix = wafer.getScreenCTM();
      const detailMatrix = detail.getScreenCTM();
      if (!waferMatrix || !detailMatrix) return;

      const bounds = host.getBoundingClientRect();
      const relative = (matrix: DOMMatrix): Transform => ({
        a: matrix.a,
        b: matrix.b,
        c: matrix.c,
        d: matrix.d,
        e: matrix.e - bounds.left,
        f: matrix.f - bounds.top,
      });
      setLayout({
        wafer: relative(waferMatrix),
        detail: relative(detailMatrix),
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    observer.observe(wafer);
    observer.observe(detail);
    measure();

    return () => observer.disconnect();
  }, [opacity > 0]);

  const { x, y, size } = waferDetailRegion;
  const sources: [Point, Point] = [
    [x + size, y],
    [x + size, y + size],
  ];

  return (
    <svg
      className="fab-magnification-links"
      style={{ opacity }}
      ref={overlay}
      aria-hidden="true"
    >
      {layout
        ? corners.map((corner, index) => {
            const [x1, y1] = transformPoint(sources[index], layout.wafer);
            const [x2, y2] = transformPoint(corner, layout.detail);

            return (
              <line
                key={index}
                x1={x1}
                y1={y1}
                x2={x1 + (x2 - x1) * progress}
                y2={y1 + (y2 - y1) * progress}
              />
            );
          })
        : null}
    </svg>
  );
};
