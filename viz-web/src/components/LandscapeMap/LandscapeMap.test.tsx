import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeMap } from "./LandscapeMap";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";

const nodes: GraphNodeRow[] = [
  {
    node_id: "1",
    kind: "theme",
    slug: "election",
    display_name: "US election narratives",
    summary: "Election coverage",
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

function setup(overrides: Partial<Parameters<typeof LandscapeMap>[0]> = {}) {
  const onHover = vi.fn();
  const onNodeClick = vi.fn();
  return {
    onHover,
    onNodeClick,
    ...render(
      <LandscapeMap
        nodes={nodes}
        relations={relations}
        hoveredNodeId={null}
        onHover={onHover}
        onNodeClick={onNodeClick}
        {...overrides}
      />,
    ),
  };
}

describe("LandscapeMap", () => {
  it("renders one button per node", () => {
    setup();
    const buttons = screen.getAllByRole("button").filter((b) => b.getAttribute("data-node-id"));
    expect(buttons).toHaveLength(2);
  });

  it("each bubble button has an aria-label including display name and kind", () => {
    setup();
    expect(screen.getByRole("button", { name: /US election narratives.*theme.*84\.00/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /April 8 Hormuz.*event.*72\.00/ })).toBeInTheDocument();
  });

  it("plain click calls onNodeClick", async () => {
    const user = userEvent.setup();
    const { onNodeClick } = setup();
    await user.click(screen.getByRole("button", { name: /US election narratives/ }));
    expect(onNodeClick).toHaveBeenCalledWith(expect.objectContaining({ node_id: "1" }));
  });

  it("shift-click opens the preview popover instead of navigating", async () => {
    const user = userEvent.setup();
    const { onNodeClick } = setup();
    await user.keyboard("{Shift>}");
    await user.click(screen.getByRole("button", { name: /US election narratives/ }));
    await user.keyboard("{/Shift}");
    expect(onNodeClick).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: /node preview/i })).toBeInTheDocument();
    expect(screen.getAllByText(/US election narratives/).length).toBeGreaterThanOrEqual(2);
  });

  it("renders caption legend", () => {
    setup();
    expect(screen.getByText("Heat map")).toBeInTheDocument();
    expect(screen.getByText(/ring = kind/i)).toBeInTheDocument();
  });
});
