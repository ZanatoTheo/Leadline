import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AppMode = "founder" | "investor";

interface ModeStore {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
}

export const useModeStore = create<ModeStore>()(
  persist(
    (set) => ({
      mode: "founder",
      setMode: (mode) => set({ mode }),
    }),
    { name: "leadline-mode" }
  )
);
