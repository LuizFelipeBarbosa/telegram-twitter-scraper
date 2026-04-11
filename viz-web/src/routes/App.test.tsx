import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App";

vi.stubGlobal(
  "fetch",
  vi.fn((input: string) => {
    if (input.startsWith("/api/graph/snapshot")) {
      return Promise.resolve(
        new Response(JSON.stringify({ window: "7d", nodes: [], relations: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }),
);

describe("App", () => {
  it("renders phase-1 tabs and disabled upcoming views", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Landscape")).toBeInTheDocument();
    expect(screen.getByText("Node Detail")).toBeInTheDocument();
    expect(screen.getByText("Trends")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Propagation")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("Evolution")).toHaveAttribute("aria-disabled", "true");
  });
});
