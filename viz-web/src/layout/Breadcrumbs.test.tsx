import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Breadcrumbs } from "./Breadcrumbs";

describe("Breadcrumbs", () => {
  it("renders a Landscape link followed by kind and display name", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs kind="event" displayName="April 8 Hormuz Reclosure" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Landscape" })).toHaveAttribute("href", "/");
    expect(screen.getByText("event")).toBeInTheDocument();
    expect(screen.getByText("April 8 Hormuz Reclosure")).toBeInTheDocument();
  });

  it("renders a parent event breadcrumb when provided", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs
          kind="event"
          displayName="April 9 Follow-up Talks"
          parentEvent={{
            node_id: "event-1",
            slug: "operation-roaring-lion",
            display_name: "Operation Roaring Lion",
            article_count: 3,
            child_count: 1,
          }}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Operation Roaring Lion" })).toHaveAttribute(
      "href",
      "/node/event/operation-roaring-lion",
    );
  });
});
