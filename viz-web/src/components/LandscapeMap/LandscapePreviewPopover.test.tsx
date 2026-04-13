import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapePreviewPopover } from "./LandscapePreviewPopover";
import type { GraphNodeRow } from "../../lib/types";

const node: GraphNodeRow = {
  node_id: "1",
  kind: "theme",
  slug: "election",
  display_name: "US election narratives",
  summary: "Election coverage across the RT feed",
  article_count: 142,
  score: 84,
  phase: "emerging",
  child_count: 0,
  parent_event: null,
};

describe("LandscapePreviewPopover", () => {
  it("renders display name, kind, and score", () => {
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={() => undefined} onNavigate={() => undefined} />,
    );
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText(/theme/i)).toBeInTheDocument();
    expect(screen.getByText(/84\.00/)).toBeInTheDocument();
  });

  it("clicking 'Open detail' calls onNavigate with the node", async () => {
    const handler = vi.fn();
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={() => undefined} onNavigate={handler} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /open detail/i }));
    expect(handler).toHaveBeenCalledWith(node);
  });

  it("pressing Escape calls onClose", () => {
    const handler = vi.fn();
    render(
      <LandscapePreviewPopover node={node} x={100} y={200} onClose={handler} onNavigate={() => undefined} />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
