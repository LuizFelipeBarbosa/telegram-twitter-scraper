import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NodeHeaderBand } from "./NodeHeaderBand";
import type { NodeDetail } from "../lib/types";

const theme: NodeDetail = {
  node_id: "1",
  kind: "theme",
  slug: "election",
  display_name: "US election narratives",
  summary: "Election coverage across the RT feed",
  article_count: 142,
  events: [],
  people: [],
  nations: [],
  orgs: [],
  places: [],
  themes: [],
  stories: [],
};

const event: NodeDetail = {
  ...theme,
  kind: "event",
  slug: "april-8",
  display_name: "April 8 Hormuz Reclosure",
};

describe("NodeHeaderBand", () => {
  it("renders eyebrow, display name, slug, and stories count", () => {
    render(<NodeHeaderBand detail={theme} />);
    expect(screen.getByText(/NODE DETAIL · THEME/)).toBeInTheDocument();
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText("election")).toBeInTheDocument();
    expect(screen.getByText(/142 stories/)).toBeInTheDocument();
  });

  it("shows a phase badge for theme nodes when provided", () => {
    render(<NodeHeaderBand detail={{ ...theme, summary: null }} phase="emerging" />);
    expect(screen.getByText("Emerging")).toBeInTheDocument();
  });

  it("does not show phase badge for non-theme nodes", () => {
    render(<NodeHeaderBand detail={event} phase="emerging" />);
    expect(screen.queryByText("Emerging")).toBeNull();
  });

  it("renders summary paragraph when present", () => {
    render(<NodeHeaderBand detail={theme} />);
    expect(screen.getByText("Election coverage across the RT feed")).toBeInTheDocument();
  });
});
