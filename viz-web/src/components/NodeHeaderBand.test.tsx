import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
  parent_event: null,
  child_events: [],
  events: [],
  people: [],
  nations: [],
  orgs: [],
  places: [],
  themes: [],
  messages: [],
};

const event: NodeDetail = {
  ...theme,
  kind: "event",
  slug: "april-8",
  display_name: "April 8 Hormuz Reclosure",
};

describe("NodeHeaderBand", () => {
  it("renders eyebrow, display name, slug, and messages count", () => {
    render(<NodeHeaderBand detail={theme} />);
    expect(screen.getByText(/NODE DETAIL · THEME/)).toBeInTheDocument();
    expect(screen.getByText("US election narratives")).toBeInTheDocument();
    expect(screen.getByText("election")).toBeInTheDocument();
    expect(screen.getByText(/142 messages/)).toBeInTheDocument();
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

  it("shows parent linkage and child counts for event hierarchy nodes", () => {
    render(
      <MemoryRouter>
        <NodeHeaderBand
          detail={{
            ...event,
            parent_event: {
              node_id: "event-parent",
              slug: "operation-roaring-lion",
              display_name: "Operation Roaring Lion",
              article_count: 3,
              child_count: 1,
            },
            child_events: [
              {
                node_id: "event-child",
                slug: "day-2",
                display_name: "Day 2",
                article_count: 1,
                child_count: 0,
                location_labels: [],
                organization_labels: [],
              },
            ],
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText(/1 sub-events/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Operation Roaring Lion" })).toHaveAttribute(
      "href",
      "/node/event/operation-roaring-lion",
    );
  });
});
