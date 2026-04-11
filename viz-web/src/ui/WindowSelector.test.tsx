import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WindowSelector } from "./WindowSelector";

describe("WindowSelector", () => {
  it("renders all six window keys as buttons", () => {
    render(<WindowSelector value="7d" onChange={() => undefined} />);
    ["1d", "3d", "5d", "7d", "14d", "31d"].forEach((key) => {
      expect(screen.getByRole("button", { name: key })).toBeInTheDocument();
    });
  });

  it("marks the active window with aria-pressed and ink fill", () => {
    render(<WindowSelector value="7d" onChange={() => undefined} />);
    const active = screen.getByRole("button", { name: "7d" });
    expect(active).toHaveAttribute("aria-pressed", "true");
    expect(active).toHaveClass("bg-ink");
  });

  it("fires onChange with the new key when another button is clicked", async () => {
    const handler = vi.fn();
    render(<WindowSelector value="7d" onChange={handler} />);
    await userEvent.click(screen.getByRole("button", { name: "14d" }));
    expect(handler).toHaveBeenCalledWith("14d");
  });
});
