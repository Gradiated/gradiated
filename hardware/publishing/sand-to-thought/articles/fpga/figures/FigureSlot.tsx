import { createContext } from "react";

export const FigureSlot = createContext<{
  target: SVGGElement | null;
  chipTarget?: SVGGElement | null;
  active?: boolean;
} | null>(null);
