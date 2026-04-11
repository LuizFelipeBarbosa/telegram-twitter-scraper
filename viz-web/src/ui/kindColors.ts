import type { NodeKind } from "../lib/types";

export const KIND_STROKE: Record<NodeKind, string> = {
  event: "#B45309",
  theme: "#2F4858",
  person: "#115E59",
  nation: "#1D4ED8",
  org: "#7C2D12",
  place: "#4D7C0F",
};

export const KIND_LABEL: Record<NodeKind, string> = {
  event: "Event",
  theme: "Theme",
  person: "Person",
  nation: "Nation",
  org: "Organization",
  place: "Place",
};

export const NODE_KINDS: readonly NodeKind[] = ["event", "theme", "person", "nation", "org", "place"] as const;
