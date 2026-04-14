import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ConnectedNodesRail } from "./ConnectedNodesRail";
import type { NodeDetail } from "../lib/types";

const detail: NodeDetail = {
  node_id: "1",
  kind: "event",
  slug: "april-8",
  display_name: "April 8 Hormuz",
  article_count: 20,
  parent_event: null,
  child_events: [],
  events: [],
  people: [
    {
      node_id: "p-1",
      kind: "person",
      slug: "jane-doe",
      display_name: "Jane Doe",
      article_count: 7,
      score: 0.82,
      shared_message_count: 4,
    },
  ],
  nations: [],
  orgs: [],
  places: [],
  themes: [],
  messages: [],
};

describe("ConnectedNodesRail", () => {
  it("renders six section headers regardless of content", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    ["Events", "People", "Nations", "Organizations", "Places", "Themes"].forEach((label) => {
      expect(screen.getByText(new RegExp(label, "i"))).toBeInTheDocument();
    });
  });

  it("shows related rows for non-empty sections", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText(/4 shared messages/)).toBeInTheDocument();
  });

  it("shows a muted empty copy for empty sections", () => {
    render(
      <MemoryRouter>
        <ConnectedNodesRail detail={detail} />
      </MemoryRouter>,
    );
    expect(screen.getAllByText(/no related/i).length).toBeGreaterThanOrEqual(5);
  });
});
