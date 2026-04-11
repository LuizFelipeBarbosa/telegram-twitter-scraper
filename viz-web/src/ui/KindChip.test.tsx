import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { KindChip } from "./KindChip";

describe("KindChip", () => {
  it("renders label and a colored dot", () => {
    const { container } = render(<KindChip kind="event" />);
    expect(screen.getByText("Event")).toBeInTheDocument();
    const dot = container.querySelector("[data-dot=\"true\"]");
    expect(dot).not.toBeNull();
    expect(dot).toHaveStyle({ backgroundColor: "#B45309" });
  });

  it("is a button and fires onClick", async () => {
    const handler = vi.fn();
    render(<KindChip kind="theme" onClick={handler} />);
    await userEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("applies active styling when active prop is true", () => {
    render(<KindChip kind="theme" active />);
    expect(screen.getByRole("button", { name: /theme/i })).toHaveClass("bg-ink");
  });
});
