import { processCategories, processCategoryFor } from "./processCategories";
import type { FabricationStep } from "./sequence";

const point = (radius: number, degrees: number) => {
  const angle = (degrees * Math.PI) / 180;

  return [90 + radius * Math.cos(angle), 90 + radius * Math.sin(angle)];
};

const sector = (index: number) => {
  const start = index * 60 - 90;
  const end = start + 60;
  const halfGap = 1.75;
  const outerInset = (Math.asin(halfGap / 82) * 180) / Math.PI;
  const innerInset = (Math.asin(halfGap / 40) * 180) / Math.PI;
  const outerStart = point(82, start + outerInset);
  const outerEnd = point(82, end - outerInset);
  const innerEnd = point(40, end - innerInset);
  const innerStart = point(40, start + innerInset);

  return `M${outerStart} A82 82 0 0 1 ${outerEnd} L${innerEnd} A40 40 0 0 0 ${innerStart} Z`;
};

export const FabricationProcessIndicator = ({
  step,
}: {
  step: FabricationStep;
}) => {
  const current = processCategoryFor(step);
  const selected = processCategories.find(
    (category) => category.id === current,
  );

  return (
    <figure
      className="fab-process-indicator"
      aria-label="Fabrication process category"
    >
      <svg
        viewBox="0 0 180 180"
        role="img"
        aria-label={selected?.label ?? "Overview: no fabrication operation"}
      >
        {processCategories.map((category, index) => {
          const label = point(61, index * 60 - 60);

          return (
            <g
              key={category.id}
              data-category={category.id}
              data-active={category.id === current}
            >
              <title>{category.label}</title>
              <path d={sector(index)} />
              <text x={label[0]} y={label[1]} dominantBaseline="middle">
                {category.short}
              </text>
            </g>
          );
        })}
        <text className="fab-process-centre-label" x="90" y="83">
          Process
        </text>
        <text className="fab-process-centre-value" x="90" y="103">
          {selected?.short ?? "Overview"}
        </text>
      </svg>
      <figcaption aria-live="polite" aria-atomic="true">
        {selected?.label ?? "Overview"}
      </figcaption>
    </figure>
  );
};
