import { useContext, useId } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { FigureSlot } from "./FigureSlot";

export const WorldLayer = ({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) => {
  const slot = useContext(FigureSlot);
  const id = useId();
  if (!slot?.target) return null;

  return createPortal(
    <g
      className={`fpga-world-layer ${className}`}
      role="img"
      aria-labelledby={id}
    >
      <title id={id}>{title}</title>
      {children}
    </g>,
    slot.target,
  );
};
