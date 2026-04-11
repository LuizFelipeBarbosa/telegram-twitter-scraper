import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { TopNav } from "./TopNav";

describe("TopNav", () => {
  it("renders brand mark and all five routes", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Telegram Knowledge Graph")).toBeInTheDocument();
    expect(screen.getByText("Landscape")).toBeInTheDocument();
    expect(screen.getByText("Node Detail")).toBeInTheDocument();
    expect(screen.getByText("Trends")).toBeInTheDocument();
    expect(screen.getByText("Propagation")).toBeInTheDocument();
    expect(screen.getByText("Evolution")).toBeInTheDocument();
  });

  it("marks Landscape as active on /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Landscape").closest("a")).toHaveAttribute("data-active", "true");
  });

  it("marks Node Detail as active when on /node/:kind/:slug", () => {
    render(
      <MemoryRouter initialEntries={["/node/event/demo"]}>
        <TopNav />
      </MemoryRouter>,
    );
    expect(screen.getByText("Node Detail").closest("a")).toHaveAttribute("data-active", "true");
  });

  it("renders disabled routes as aria-disabled and not clickable", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <TopNav />
      </MemoryRouter>,
    );
    ["Trends", "Propagation", "Evolution"].forEach((label) => {
      const el = screen.getByText(label);
      expect(el).toHaveAttribute("aria-disabled", "true");
    });
  });
});
