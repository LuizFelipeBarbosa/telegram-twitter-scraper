import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LandscapeMap } from "./LandscapeMap";
import type { GraphNodeRow, SnapshotRelation } from "../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
    article_count: 140,
    score: 84,
    phase: "emerging",
  },
  {
    node_id: "2",
    kind: "event",
    slug: "april-8",
    display_name: "April 8 Hormuz",
    article_count: 89,
    score: 72,
  },
];
const relations: SnapshotRelation[] = [];

describe("LandscapeMap", () => {
  it("renders an svg with one circle per node", () => {
    const { container } = render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={() => undefined}
        onNodeClick={() => undefined}
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(container.querySelectorAll("circle").length).toBe(2);
  });

  it("calls onHover with a node id on mouseenter", async () => {
    const handler = vi.fn();
    const { container } = render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={handler}
        onNodeClick={() => undefined}
      />,
    );
    const circle = container.querySelector("circle")!;
    circle.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
    expect(handler).toHaveBeenCalled();
  });

  it("renders caption legend", () => {
    render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={() => undefined}
        onNodeClick={() => undefined}
      />,
    );
    expect(screen.getByText(/ring = kind/i)).toBeInTheDocument();
    expect(screen.getByText("Heat map")).toBeInTheDocument();
  });
});
