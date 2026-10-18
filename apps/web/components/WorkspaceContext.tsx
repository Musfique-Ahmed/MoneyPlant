"use client";

import { create } from "zustand";

interface WorkspaceState {
  businessId: string | null;
  setBusinessId: (id: string | null) => void;
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  businessId: null,
  setBusinessId: (id) => set({ businessId: id }),
}));
