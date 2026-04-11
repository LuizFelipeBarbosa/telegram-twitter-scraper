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
});
