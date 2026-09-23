import { create } from "zustand";

interface ConnectFlowState {
  taskSlug: string;
  status: "waiting" | "connected";
  setTaskSlug: (taskSlug: string) => void;
  markConnected: () => void;
}

export const useConnectFlow = create<ConnectFlowState>()((set) => ({
  taskSlug: "support-triage",
  status: "waiting",
  setTaskSlug: (taskSlug) => set({ taskSlug }),
  markConnected: () => set({ status: "connected" }),
}));
