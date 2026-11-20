import { createContext, useContext } from "react";

import type { EvalIndex } from "@/lib/eval-data";

export type EvalDataset =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; index: EvalIndex };

export type EvalView = { models: string[]; metric: string };

export type EvalPanel = {
  open: (
    file: string,
    caseId: string,
    order: readonly string[],
    view: EvalView,
  ) => void;
};

export const EvalDataContext = createContext<ReadonlyMap<string, EvalDataset>>(
  new Map(),
);

export const EvalPanelContext = createContext<EvalPanel>({ open: () => {} });

export const useEvalDataset = (name: unknown): EvalDataset =>
  useContext(EvalDataContext).get(String(name)) ?? { status: "loading" };

export const useEvalPanel = () => useContext(EvalPanelContext);
