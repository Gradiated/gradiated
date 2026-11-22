import { CircuitBoard, Cpu, Gpu, Microchip } from "lucide-react";

export const chipChoiceIcons = {
  FPGA: CircuitBoard,
  CPU: Cpu,
  GPU: Gpu,
  ASIC: Microchip,
} as const;
