import { create } from "zustand";

type AppStoreState = {
  sidebarCollapsed: boolean;
  statusMessage: string;
  operatorName: string;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setStatusMessage: (message: string) => void;
};

export const useAppStore = create<AppStoreState>((set) => ({
  sidebarCollapsed: false,
  statusMessage: "Ready",
  operatorName: "System Operator",
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setStatusMessage: (message) => set({ statusMessage: message })
}));
