import { create } from "zustand";

interface ConnectFlowState {
  taskSlug: string;
  setTaskSlug: (taskSlug: string) => void;
}

export const useConnectFlow = create<ConnectFlowState>()((set) => ({
  taskSlug: "support-triage",
  setTaskSlug: (taskSlug) => set({ taskSlug }),
}));
