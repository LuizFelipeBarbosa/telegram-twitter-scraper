import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders label as ink by default", () => {
    render(<Button>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("bg-ink");
    expect(button).toHaveClass("text-paper");
  });

  it("renders ghost variant with a ruled border and transparent background", () => {
    render(<Button variant="ghost">Cancel</Button>);
    const button = screen.getByRole("button", { name: "Cancel" });
    expect(button).toHaveClass("border");
    expect(button).toHaveClass("bg-transparent");
  });

  it("applies active styling when active prop is true on ghost variant", () => {
    render(
      <Button variant="ghost" active>
        7D
      </Button>,
    );
    const button = screen.getByRole("button", { name: "7D" });
    expect(button).toHaveClass("bg-ink");
  });

  it("fires onClick", async () => {
    const handler = vi.fn();
    render(<Button onClick={handler}>Go</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
