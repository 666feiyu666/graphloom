import { create } from "zustand";
import type { GraphObject, Kind } from "../api/types";
import { defaultValues, valuesFromObject } from "../api/draft";

export type Mode = "model" | "instance";
export type View = "graph" | "table";
export type Drawer = "history" | "changes" | "read" | null;

export interface Draft {
  mode: "create" | "edit";
  kind: Kind;
  id?: string;
  values: Record<string, unknown>;
  original: Record<string, unknown> | null;
  baseRevision: number;
  dirty: boolean;
}

interface UIState {
  mode: Mode;
  view: View;
  selectedId: string | null;
  selectedClassId: string | null;
  drawer: Drawer;
  draft: Draft | null;
  linkMode: boolean;
  linkSource: string | null;
  notice: string | null;
  setMode: (mode: Mode) => void;
  setView: (view: View) => void;
  setDrawer: (drawer: Drawer) => void;
  select: (id: string | null) => boolean;
  selectClass: (id: string | null) => void;
  startCreate: (kind: Kind, baseRevision: number, initial?: Record<string, unknown>) => void;
  startEdit: (object: GraphObject, baseRevision: number) => void;
  updateDraft: (field: string, value: unknown) => void;
  setDraftBaseRevision: (revision: number) => void;
  clearDraft: () => void;
  setLinkMode: (enabled: boolean) => void;
  setLinkSource: (id: string | null) => void;
  setNotice: (notice: string | null) => void;
  reset: () => void;
}

export const useUI = create<UIState>((set, get) => ({
  mode: "model",
  view: "graph",
  selectedId: null,
  selectedClassId: null,
  drawer: null,
  draft: null,
  linkMode: false,
  linkSource: null,
  notice: null,

  setMode: (mode) => set({ mode, selectedClassId: mode === "model" ? null : get().selectedClassId }),
  setView: (view) => set({ view }),
  setDrawer: (drawer) => set({ drawer }),

  select: (id) => {
    const state = get();
    if (state.draft?.dirty) {
      set({ notice: "当前有未保存草稿；请先保存或放弃草稿，再切换对象。" });
      return false;
    }
    set({ selectedId: id, draft: null, notice: null });
    return true;
  },

  selectClass: (id) => set({ selectedClassId: id, selectedId: null, draft: null }),

  startCreate: (kind, baseRevision, initial = {}) =>
    set({
      draft: {
        mode: "create",
        kind,
        values: { ...defaultValues(kind), ...initial },
        original: null,
        baseRevision,
        dirty: true,
      },
      selectedId: null,
      notice: null,
    }),

  startEdit: (object, baseRevision) =>
    set({
      draft: {
        mode: "edit",
        kind: object.kind,
        id: object.id,
        values: valuesFromObject(object),
        original: valuesFromObject(object),
        baseRevision,
        dirty: false,
      },
      selectedId: object.id,
      notice: null,
    }),

  updateDraft: (field, value) =>
    set((state) =>
      state.draft
        ? { draft: { ...state.draft, values: { ...state.draft.values, [field]: value }, dirty: true } }
        : {},
    ),

  setDraftBaseRevision: (revision) =>
    set((state) =>
      state.draft ? { draft: { ...state.draft, baseRevision: revision } } : {},
    ),

  clearDraft: () => set({ draft: null, notice: null }),
  setLinkMode: (enabled) => set({ linkMode: enabled, linkSource: null }),
  setLinkSource: (id) => set({ linkSource: id }),
  setNotice: (notice) => set({ notice }),

  reset: () =>
    set({
      mode: "model",
      view: "graph",
      selectedId: null,
      selectedClassId: null,
      drawer: null,
      draft: null,
      linkMode: false,
      linkSource: null,
      notice: null,
    }),
}));
