import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeTable } from "./LandscapeTable";
import type { GraphNodeRow } from "../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
    summary: "Election coverage",
    article_count: 142,
    score: 84,
    phase: "emerging",
    child_count: 0,
    parent_event: null,
  },
  {
    node_id: "2",
    kind: "event",
    slug: "april-8-hormuz",
    display_name: "April 8 Hormuz Reclosure",
    article_count: 89,
    score: 72,
    child_count: 3,
    parent_event: null,
  },
];

describe("LandscapeTable", () => {
  it("renders a row per node with display_name and score", () => {
    render(
      <LandscapeTable
        nodes={nodes}
        hoveredNodeId={null}
        onHover={() => undefined}
        onRowClick={() => undefined}
      />,
    );
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText("April 8 Hormuz Reclosure")).toBeInTheDocument();
    expect(screen.getByText("84.00")).toBeInTheDocument();
    expect(screen.getByText("72.00")).toBeInTheDocument();
    expect(screen.getByText(/3 sub-events/)).toBeInTheDocument();
  });

  it("fires onRowClick with the clicked node", async () => {
    const handler = vi.fn();
    render(
      <LandscapeTable
        nodes={nodes}
        hoveredNodeId={null}
        onHover={() => undefined}
        onRowClick={handler}
      />,
    );
    await userEvent.click(screen.getByText("April 8 Hormuz Reclosure"));
    expect(handler).toHaveBeenCalledWith(nodes[1]);
  });
});
