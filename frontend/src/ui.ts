import type { Kind } from "./api/types";

export type Mode = "model" | "instance";
export type View = "graph" | "table";

export interface Draft {
  mode: "create" | "edit";
  kind: Kind;
  id?: string;
  values: Record<string, unknown>;
  original: Record<string, unknown> | null;
}
